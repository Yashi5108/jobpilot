from __future__ import annotations

from sqlalchemy.orm import Session

from backend.browser.mapping import BrowserField, map_field_results, map_fields
from backend.core.config import get_settings
from backend.database.models import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    UserProfile,
)


class BrowserAssistantServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def run_browser_assistant(
    *,
    db: Session,
    application_id: int,
    application_url: str,
    fields: list[BrowserField],
    dry_run: bool,
) -> tuple[list[dict[str, str]], list[str], str]:
    field_results, message = run_browser_assistant_detailed(
        db=db,
        application_id=application_id,
        application_url=application_url,
        fields=fields,
        dry_run=dry_run,
    )
    mapped = [
        {
            "field": item["field"],
            "label": item["label"],
            "type": item["type"],
            "value": item["value"],
        }
        for item in field_results
        if item["status"] == "FILLED" and item.get("value")
    ]
    unknown = [
        item["label"] for item in field_results if item["status"] == "NEEDS_USER_INPUT"
    ]
    return mapped, unknown, message


def run_browser_assistant_detailed(
    *,
    db: Session,
    application_id: int,
    application_url: str,
    fields: list[BrowserField],
    dry_run: bool,
) -> tuple[list[dict[str, str]], str]:
    application = db.get(Application, application_id)
    if application is None:
        raise BrowserAssistantServiceError("Application not found", status_code=404)

    if application.status != ApplicationStatus.READY_FOR_REVIEW:
        raise BrowserAssistantServiceError(
            "Application must be READY_FOR_REVIEW before browser assistance.",
            status_code=409,
        )

    profile = db.get(UserProfile, application.profile_id)
    if profile is None:
        raise BrowserAssistantServiceError("Profile not found", status_code=404)

    mapping_results = map_field_results(
        profile=profile,
        application=application,
        fields=fields,
    )
    mapped, unknown = map_fields(
        profile=profile,
        application=application,
        fields=fields,
    )
    field_results = [
        {
            "field": item.field,
            "label": item.label,
            "type": item.field_type,
            "required": item.required,
            "value": item.value or "",
            "status": ("FILLED" if item.status == "READY" and dry_run else item.status),
            "message": (
                "Dry run only. Value available for assisted fill."
                if item.status == "READY" and dry_run
                else item.message
            ),
        }
        for item in mapping_results
    ]

    details = (
        application.preparation_details
        if isinstance(application.preparation_details, dict)
        else {}
    )
    details["fields_to_submit"] = mapped
    details["unknown_fields"] = unknown
    details["field_results"] = field_results
    details["application_url"] = application_url
    details["browser_assistant_last_mode"] = "dry_run" if dry_run else "playwright"
    application.preparation_details = details
    db.add(application)

    settings = get_settings()
    mode = settings.browser_assistant_mode.strip().lower()
    if dry_run or mode in {"dry_run", "mock", "test"}:
        message = "Dry-run mapping completed. Review fields and submit manually."
    else:
        field_results, message = _run_playwright_fill(
            application_url=application_url,
            fields=field_results,
            headless=settings.browser_headless,
        )
        details["field_results"] = field_results
        application.preparation_details = details
        db.add(application)

    event = ApplicationEvent(
        application_id=application.id,
        event_type=ApplicationStatus.READY_FOR_REVIEW.value,
        description=(
            "Browser assistant prepared field mappings. " "Manual submit required."
        ),
    )
    db.add(event)
    db.commit()
    return field_results, message


def discover_browser_fields(
    application_url: str,
    *,
    headless: bool,
) -> list[BrowserField]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(application_url, wait_until="domcontentloaded")
        raw_fields = page.evaluate("""
            () => Array.from(document.querySelectorAll('input, textarea, select'))
              .map((element) => {
                const tag = element.tagName.toLowerCase();
                const inputType = element.getAttribute('type') || tag;
                if (['hidden', 'submit', 'button', 'reset'].includes(inputType)) {
                  return null;
                }
                const labels = element.labels ? Array.from(element.labels) : [];
                                const labelText = labels
                                    .map((item) => item.innerText || '')
                                    .join(' ')
                                    .trim();
                                const name = element.getAttribute('name')
                                    || element.getAttribute('id')
                                    || '';
                return {
                  name,
                  label: labelText,
                  field_type: tag === 'select' ? 'select' : inputType,
                  required: element.required === true,
                };
              })
              .filter(Boolean)
            """)
        browser.close()

    if not isinstance(raw_fields, list):
        return []

    fields: list[BrowserField] = []
    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        label = str(item.get("label") or name).strip()
        if not name:
            continue
        fields.append(
            BrowserField(
                name=name,
                label=label,
                field_type=str(item.get("field_type") or "text").strip() or "text",
                required=bool(item.get("required")),
            )
        )
    return fields


def _run_playwright_fill(
    application_url: str,
    fields: list[dict[str, str]],
    headless: bool,
) -> tuple[list[dict[str, str]], str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return fields, (
            "Playwright is unavailable in this environment. "
            "Install browsers and use dry-run/manual flow."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(application_url, wait_until="domcontentloaded")

        for field in fields:
            if field["status"] in {"NEEDS_USER_INPUT", "SKIPPED"}:
                continue
            selector = f"[name='{field['field']}']"
            try:
                locator = page.locator(selector).first
                field_type = (field.get("type") or "text").lower()
                value = field.get("value") or ""
                if field_type in {"text", "email", "tel", "textarea"}:
                    locator.fill(value)
                elif field_type == "select":
                    locator.select_option(label=value)
                elif field_type in {"checkbox", "radio"}:
                    if value.lower() in {"yes", "true", "1", "checked"}:
                        locator.check()
                elif field_type == "file":
                    locator.set_input_files(value)
                else:
                    field["status"] = "SKIPPED"
                    field["message"] = "Unsupported widget type for safe automation."
                    continue
                field["status"] = "FILLED"
                field["message"] = "Filled successfully."
            except Exception:
                field["status"] = "FAILED"
                field["message"] = "Failed to fill field safely."

        browser.close()

    return fields, (
        "Form fields were filled where safely mapped. "
        "Manual review and submission required."
    )
