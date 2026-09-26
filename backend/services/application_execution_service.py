from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from backend.browser.assistant import (
    BrowserAssistantServiceError,
    discover_browser_fields,
    run_browser_assistant_detailed,
)
from backend.browser.mapping import BrowserField
from backend.core.config import get_settings
from backend.database.models import Application, ApplicationEvent, ApplicationStatus
from backend.schemas.application_execution import (
    ApplicationExecutionRequest,
    ApplicationExecutionResponse,
    FieldExecutionResult,
)


class ApplicationExecutionServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AuthorizedExecutionResult:
    success: bool
    message: str
    status: str = "BLOCKED"


class AuthorizedApplicationAdapter(Protocol):
    name: str

    def supports(self, application: Application) -> bool: ...

    def submit(
        self,
        *,
        application: Application,
        application_url: str | None,
    ) -> AuthorizedExecutionResult: ...


_RESTRICTED_BROWSER_HOSTS = ("linkedin.com", "naukri.com")


def execute_application(
    db: Session,
    application_id: int,
    payload: ApplicationExecutionRequest,
) -> ApplicationExecutionResponse:
    application = db.get(Application, application_id)
    if application is None:
        raise ApplicationExecutionServiceError("Application not found", status_code=404)

    if application.status != ApplicationStatus.READY_FOR_REVIEW:
        raise ApplicationExecutionServiceError(
            "Application must be READY_FOR_REVIEW before execution.",
            status_code=409,
        )

    details = (
        application.preparation_details
        if isinstance(application.preparation_details, dict)
        else {}
    )
    application_url = (
        payload.application_url
        or details.get("application_url")
        or (application.job.url if application.job else None)
    )

    adapter = _select_authorized_adapter(application)
    if adapter is not None:
        return _execute_authorized_application(
            db=db,
            application=application,
            application_url=application_url,
            adapter=adapter,
            submit=payload.submit,
        )

    if _is_restricted_browser_host(application_url):
        response = ApplicationExecutionResponse(
            application_id=application.id,
            mode="OPEN_AND_APPLY",
            status="OPEN_AND_APPLY",
            submitted=False,
            requires_human_submit=True,
            application_url=application_url,
            field_results=[],
            message=(
                "This site is not automated by JobPilot. Open the legitimate "
                "application page and apply manually."
            ),
        )
        _record_execution(db, application.id, response.message)
        return response

    settings = get_settings()
    fields = [
        BrowserField(
            name=item.name,
            label=item.label,
            field_type=item.field_type,
            required=item.required,
        )
        for item in payload.fields
    ]
    if not fields and payload.detect_fields and application_url:
        fields = discover_browser_fields(
            application_url,
            headless=settings.browser_headless,
        )

    if not application_url or not fields:
        response = ApplicationExecutionResponse(
            application_id=application.id,
            mode="OPEN_AND_APPLY",
            status="OPEN_AND_APPLY",
            submitted=False,
            requires_human_submit=True,
            application_url=application_url,
            field_results=[],
            message=(
                "JobPilot could not safely detect a supported form. Open the "
                "application URL and apply manually."
            ),
        )
        _record_execution(db, application.id, response.message)
        return response

    try:
        field_results, message = run_browser_assistant_detailed(
            db=db,
            application_id=application.id,
            application_url=application_url,
            fields=fields,
            dry_run=payload.dry_run,
        )
    except BrowserAssistantServiceError as exc:
        raise ApplicationExecutionServiceError(
            str(exc),
            status_code=exc.status_code,
        ) from exc

    validated_field_results = [
        FieldExecutionResult.model_validate(item) for item in field_results
    ]

    response = ApplicationExecutionResponse(
        application_id=application.id,
        mode="BROWSER_ASSISTED",
        status="READY",
        submitted=False,
        requires_human_submit=True,
        application_url=application_url,
        field_results=validated_field_results,
        message=message,
    )
    _record_execution(db, application.id, response.message)
    return response


def _execute_authorized_application(
    *,
    db: Session,
    application: Application,
    application_url: str | None,
    adapter: AuthorizedApplicationAdapter,
    submit: bool,
) -> ApplicationExecutionResponse:
    if not submit:
        return ApplicationExecutionResponse(
            application_id=application.id,
            mode="AUTHORIZED_API",
            status="READY",
            submitted=False,
            requires_human_submit=False,
            application_url=application_url,
            field_results=[],
            message="Authorized API is available. Submit with explicit approval.",
        )

    if not application.user_approved:
        raise ApplicationExecutionServiceError(
            "Application requires explicit approval before authorized submission.",
            status_code=409,
        )

    result = adapter.submit(
        application=application,
        application_url=application_url,
    )

    if result.success:
        application.status = ApplicationStatus.APPLIED
        application.submitted_at = datetime.now(UTC)
        db.add(application)
        db.commit()
        db.refresh(application)

    _record_execution(db, application.id, result.message)
    return ApplicationExecutionResponse(
        application_id=application.id,
        mode="AUTHORIZED_API",
        status=("SUBMITTED" if result.success else "BLOCKED"),
        submitted=result.success,
        requires_human_submit=not result.success,
        application_url=application_url,
        field_results=[],
        message=result.message,
    )


def _authorized_adapters() -> list[AuthorizedApplicationAdapter]:
    return []


def _select_authorized_adapter(
    application: Application,
) -> AuthorizedApplicationAdapter | None:
    for adapter in _authorized_adapters():
        if adapter.supports(application):
            return adapter
    return None


def _is_restricted_browser_host(application_url: str | None) -> bool:
    if not application_url:
        return False
    hostname = urlsplit(application_url).netloc.lower()
    return any(host in hostname for host in _RESTRICTED_BROWSER_HOSTS)


def _record_execution(db: Session, application_id: int, description: str) -> None:
    event = ApplicationEvent(
        application_id=application_id,
        event_type=ApplicationStatus.READY_FOR_REVIEW.value,
        description=description,
        created_at=datetime.now(UTC),
    )
    db.add(event)
    db.commit()
