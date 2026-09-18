from __future__ import annotations

from sqlalchemy.orm import Session

from backend.browser.mapping import BrowserField, map_fields
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

    mapped, unknown = map_fields(
        profile=profile,
        application=application,
        fields=fields,
    )

    details = (
        application.preparation_details
        if isinstance(application.preparation_details, dict)
        else {}
    )
    details["fields_to_submit"] = mapped
    details["unknown_fields"] = unknown
    details["application_url"] = application_url
    details["browser_assistant_last_mode"] = "dry_run" if dry_run else "playwright"
    application.preparation_details = details
    db.add(application)

    settings = get_settings()
    mode = settings.browser_assistant_mode.strip().lower()
    if dry_run or mode in {"dry_run", "mock", "test"}:
        message = "Dry-run mapping completed. Review fields and submit manually."
    else:
        message = _run_playwright_fill(
            application_url=application_url,
            fields=mapped,
            headless=settings.browser_headless,
        )

    event = ApplicationEvent(
        application_id=application.id,
        event_type=ApplicationStatus.READY_FOR_REVIEW.value,
        description=(
            "Browser assistant prepared field mappings. " "Manual submit required."
        ),
    )
    db.add(event)
    db.commit()
    return mapped, unknown, message


def _run_playwright_fill(
    application_url: str,
    fields: list[dict[str, str]],
    headless: bool,
) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return (
            "Playwright is unavailable in this environment. "
            "Install browsers and use dry-run/manual flow."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(application_url, wait_until="domcontentloaded")

        for field in fields:
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
                # File upload and unknown widgets require explicit user action.
            except Exception:
                continue

        browser.close()

    return (
        "Form fields were filled where safely mapped. "
        "Manual review and submission required."
    )
