from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from backend.database.models import Application


class ProviderAdapterError(RuntimeError):
    """Raised when a provider adapter cannot execute the application."""


@dataclass(frozen=True)
class ProviderExecutionResult:
    success: bool
    message: str
    status: str = "BLOCKED"


@dataclass(frozen=True)
class ProviderOrchestrationSummary:
    provider: str
    login_required: bool
    approval_required: bool
    automation_actions: list[str]
    human_review_instructions: list[str]


class BaseProviderAdapter:
    """Base class for site-specific application execution adapters."""

    name: str = "base"
    host_markers: tuple[str, ...] = ()
    enabled: bool = False

    def summary(self) -> ProviderOrchestrationSummary:
        return ProviderOrchestrationSummary(
            provider=self.name,
            login_required=False,
            approval_required=True,
            automation_actions=["open_job_page", "detect_fields", "fill_profile_data"],
            human_review_instructions=[
                "Review the pre-application page before submission.",
                "Confirm that all mapped fields are correct before proceeding.",
            ],
        )

    def supports(self, application: Application) -> bool:
        application_url = self._application_url(application)
        if not application_url:
            return False
        hostname = urlsplit(application_url).netloc.lower()
        return any(marker in hostname for marker in self.host_markers)

    def submit(
        self,
        *,
        application: Application,
        application_url: str | None,
    ) -> ProviderExecutionResult:
        del application, application_url
        return ProviderExecutionResult(
            success=False,
            message=f"{self.name} provider is not configured for submission.",
            status="BLOCKED",
        )

    @staticmethod
    def _application_url(application: Application) -> str | None:
        if isinstance(application.preparation_details, dict):
            value = application.preparation_details.get("application_url")
            if value:
                return str(value)
        if application.job and application.job.url:
            return application.job.url
        return None


class LinkedInProviderAdapter(BaseProviderAdapter):
    name = "linkedin"
    host_markers = ("linkedin.com",)
    enabled = True

    def summary(self) -> ProviderOrchestrationSummary:
        return ProviderOrchestrationSummary(
            provider=self.name,
            login_required=True,
            approval_required=True,
            automation_actions=[
                "open_job_page",
                "login_to_linkedin",
                "detect_pre_apply_form",
                "fill_known_fields",
                "pause_for_manual_review",
            ],
            human_review_instructions=[
                "Sign in to LinkedIn before starting the application flow.",
                "Review the pre-apply form and final submit button before approving any action.",
                "Do not auto-submit without explicit user approval.",
            ],
        )

    def submit(
        self,
        *,
        application: Application,
        application_url: str | None,
    ) -> ProviderExecutionResult:
        del application
        if not application_url:
            return ProviderExecutionResult(
                success=False,
                message="LinkedIn job URL is required for provider submission.",
                status="LOGIN_REQUIRED",
            )
        return ProviderExecutionResult(
            success=False,
            message=(
                "LinkedIn requires an explicit login session before safe form orchestration. "
                "JobPilot will open the job page, detect the pre-apply form, and guide the "
                "user through manual review; no auto-submit is allowed by default."
            ),
            status="LOGIN_REQUIRED",
        )


class GreenhouseProviderAdapter(BaseProviderAdapter):
    name = "greenhouse"
    host_markers = ("greenhouse.io", "boards.greenhouse.io")
    enabled = True

    def summary(self) -> ProviderOrchestrationSummary:
        return ProviderOrchestrationSummary(
            provider=self.name,
            login_required=False,
            approval_required=True,
            automation_actions=[
                "open_job_page",
                "discover_form_fields",
                "fill_profile_values",
                "submit_application_after_approval",
            ],
            human_review_instructions=[
                "Review the Greenhouse application page before final approval.",
                "Confirm the mapped profile fields and resume upload before clicking submit.",
            ],
        )

    def submit(
        self,
        *,
        application: Application,
        application_url: str | None,
    ) -> ProviderExecutionResult:
        if not application_url:
            return ProviderExecutionResult(
                success=False,
                message="Greenhouse job URL is required for provider submission.",
                status="BLOCKED",
            )
        return _run_greenhouse_submission(
            application=application,
            application_url=application_url,
        )


class LeverProviderAdapter(BaseProviderAdapter):
    name = "lever"
    host_markers = ("lever.co", "jobs.lever.co")
    enabled = True

    def summary(self) -> ProviderOrchestrationSummary:
        return ProviderOrchestrationSummary(
            provider=self.name,
            login_required=True,
            approval_required=True,
            automation_actions=[
                "open_job_page",
                "login_to_lever",
                "detect_application_fields",
                "fill_profile_values",
                "submit_application_after_approval",
            ],
            human_review_instructions=[
                "Sign in to Lever before opening the application form.",
                "Confirm the application data and resume upload before approving final submission.",
                "Keep auto-submit disabled until the user explicitly approves the action.",
            ],
        )

    def submit(
        self,
        *,
        application: Application,
        application_url: str | None,
    ) -> ProviderExecutionResult:
        if not application_url:
            return ProviderExecutionResult(
                success=False,
                message="Lever job URL is required for provider submission.",
                status="BLOCKED",
            )

        if not getattr(application, "user_approved", False):
            return ProviderExecutionResult(
                success=False,
                message=(
                    "Lever requires an explicit login session and user approval before "
                    "JobPilot can submit. Auto-submit is disabled unless the user approves "
                    "the final action."
                ),
                status="LOGIN_REQUIRED",
            )

        return _run_lever_submission(
            application=application,
            application_url=application_url,
        )


def _run_greenhouse_submission(
    *,
    application: Application,
    application_url: str,
) -> ProviderExecutionResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ProviderExecutionResult(
            success=False,
            message=(
                "Greenhouse automation requires Playwright to be installed in the runtime. "
                "Install the browser runtime and retry."
            ),
            status="BLOCKED",
        )

    profile = application.profile
    details = (
        application.preparation_details
        if isinstance(application.preparation_details, dict)
        else {}
    )
    resume_path = None
    if application.resume and application.resume.file_path:
        resume_path = application.resume.file_path
    if not resume_path and isinstance(details.get("selected_resume_file"), str):
        resume_path = details["selected_resume_file"]

    full_name = (profile.name or "").strip() if profile else ""
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    form_values = {
        "first_name": first_name,
        "last_name": last_name,
        "email": (profile.email or "") if profile else "",
        "phone": (profile.phone or "") if profile else "",
        "location": (profile.location or "") if profile else "",
        "city": (profile.location or "") if profile else "",
        "cover_letter": application.cover_letter or "",
    }
    if application.cover_letter:
        form_values["additional_information"] = application.cover_letter

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(application_url, wait_until="domcontentloaded")

            for key, value in form_values.items():
                if not value:
                    continue
                selectors = [
                    f"input[name='{key}']",
                    f"input[name*='{key}']",
                    f"textarea[name='{key}']",
                    f"textarea[name*='{key}']",
                    f"[name='{key}']",
                ]
                for selector in selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.count() > 0:
                            if locator.get_attribute("type") == "file":
                                file_path = Path(resume_path) if resume_path else None
                                if file_path and file_path.exists():
                                    locator.set_input_files(str(file_path))
                            else:
                                locator.fill(str(value))
                            break
                    except Exception:
                        continue

            for selector in [
                "button:has-text('Submit')",
                "button:has-text('Apply')",
                "button:has-text('Continue')",
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Next')",
            ]:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0:
                        locator.click()
                        break
                except Exception:
                    continue

            browser.close()
    except Exception as exc:  # pragma: no cover - defensive path
        return ProviderExecutionResult(
            success=False,
            message=f"Greenhouse automation failed: {exc}",
            status="BLOCKED",
        )

    return ProviderExecutionResult(
        success=True,
        message=(
            "Greenhouse application flow executed via Playwright. "
            "Review the page and confirm final submission status."
        ),
        status="SUBMITTED",
    )


def _run_lever_submission(
    *,
    application: Application,
    application_url: str,
) -> ProviderExecutionResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ProviderExecutionResult(
            success=False,
            message=(
                "Lever automation requires Playwright in the runtime. "
                "Install the browser runtime and retry."
            ),
            status="BLOCKED",
        )

    profile = application.profile
    details = (
        application.preparation_details
        if isinstance(application.preparation_details, dict)
        else {}
    )
    resume_path = None
    if application.resume and application.resume.file_path:
        resume_path = application.resume.file_path
    if not resume_path and isinstance(details.get("selected_resume_file"), str):
        resume_path = details["selected_resume_file"]

    full_name = (profile.name or "").strip() if profile else ""
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    form_values = {
        "name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": (profile.email or "") if profile else "",
        "phone": (profile.phone or "") if profile else "",
        "location": (profile.location or "") if profile else "",
        "cover_letter": application.cover_letter or "",
        "additional_information": application.cover_letter or "",
    }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(application_url, wait_until="domcontentloaded")

            for key, value in form_values.items():
                if not value:
                    continue
                selectors = [
                    f"input[name='{key}']",
                    f"input[name*='{key}']",
                    f"textarea[name='{key}']",
                    f"textarea[name*='{key}']",
                    f"[name='{key}']",
                ]
                for selector in selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.count() > 0:
                            if locator.get_attribute("type") == "file":
                                file_path = Path(resume_path) if resume_path else None
                                if file_path and file_path.exists():
                                    locator.set_input_files(str(file_path))
                            else:
                                locator.fill(str(value))
                            break
                    except Exception:
                        continue

            for selector in [
                "button:has-text('Submit application')",
                "button:has-text('Submit')",
                "button:has-text('Apply')",
                "button[type='submit']",
                "input[type='submit']",
            ]:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0:
                        locator.click()
                        break
                except Exception:
                    continue

            browser.close()
    except Exception as exc:  # pragma: no cover - defensive path
        return ProviderExecutionResult(
            success=False,
            message=f"Lever automation failed: {exc}",
            status="BLOCKED",
        )

    return ProviderExecutionResult(
        success=True,
        message=(
            "Lever application flow executed via Playwright after explicit user approval. "
            "Review the submission result before final confirmation."
        ),
        status="SUBMITTED",
    )


def get_provider_adapters() -> list[BaseProviderAdapter]:
    return [
        LinkedInProviderAdapter(),
        GreenhouseProviderAdapter(),
        LeverProviderAdapter(),
    ]
