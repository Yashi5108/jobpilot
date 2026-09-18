from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    Job,
    JobMatch,
    Resume,
    UserProfile,
)
from backend.schemas.application import ApplicationCreate
from backend.schemas.application_tracker import (
    ApplicationEventRead,
    ApplicationTrackerItem,
)


class ApplicationServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DISCOVERED: {
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SHORTLISTED: {
        ApplicationStatus.PREPARING,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.PREPARING: {
        ApplicationStatus.READY_FOR_REVIEW,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.READY_FOR_REVIEW: {
        ApplicationStatus.APPLIED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.APPLIED: {
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.INTERVIEW: {
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.OFFER: {ApplicationStatus.WITHDRAWN},
    ApplicationStatus.REJECTED: set(),
    ApplicationStatus.WITHDRAWN: set(),
}


def list_applications(db: Session) -> list[Application]:
    return list(db.scalars(select(Application).order_by(Application.id.asc())).all())


def list_application_tracker_items(db: Session) -> list[ApplicationTrackerItem]:
    applications = list(
        db.scalars(select(Application).order_by(Application.updated_at.desc())).all()
    )

    results: list[ApplicationTrackerItem] = []
    for app in applications:
        match_score = _resolve_match_score(db, app.job_id, app.resume_id)
        events = list(
            db.scalars(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == app.id)
                .order_by(ApplicationEvent.created_at.asc(), ApplicationEvent.id.asc())
            ).all()
        )

        results.append(
            ApplicationTrackerItem(
                id=app.id,
                job_id=app.job_id,
                job_title=app.job.title if app.job else None,
                company=app.job.company if app.job else None,
                status=app.status,
                resume_id=app.resume_id,
                match_score=match_score,
                submitted_at=app.submitted_at,
                updated_at=app.updated_at,
                events=[
                    ApplicationEventRead(
                        id=item.id,
                        event_type=item.event_type,
                        description=item.description,
                        created_at=item.created_at,
                    )
                    for item in events
                ],
            )
        )

    return results


def get_application(db: Session, application_id: int) -> Application | None:
    return db.get(Application, application_id)


def create_application(db: Session, payload: ApplicationCreate) -> Application:
    if db.get(Job, payload.job_id) is None:
        raise ApplicationServiceError("Job not found", status_code=404)
    if db.get(UserProfile, payload.profile_id) is None:
        raise ApplicationServiceError("Profile not found", status_code=404)

    if payload.resume_id is not None and db.get(Resume, payload.resume_id) is None:
        raise ApplicationServiceError("Resume not found", status_code=404)

    application = Application(**payload.model_dump())
    db.add(application)
    db.commit()
    db.refresh(application)

    _record_event(
        db,
        application.id,
        payload.status.value,
        "Application created",
    )
    return application


def update_application_status(
    db: Session,
    application: Application,
    status: ApplicationStatus,
) -> Application:
    if application.status == status:
        return application

    allowed_next = ALLOWED_TRANSITIONS.get(application.status, set())
    if status not in allowed_next:
        raise ApplicationServiceError(
            f"Invalid status transition: {application.status.value} -> {status.value}",
            status_code=409,
        )

    if status == ApplicationStatus.APPLIED:
        raise ApplicationServiceError(
            "Use explicit submit confirmation endpoint to mark APPLIED.",
            status_code=409,
        )

    application.status = status
    db.add(application)
    db.commit()
    db.refresh(application)

    _record_event(db, application.id, status.value, "Status updated")
    return application


def approve_application_review(db: Session, application: Application) -> Application:
    if application.status != ApplicationStatus.READY_FOR_REVIEW:
        raise ApplicationServiceError(
            "Application must be READY_FOR_REVIEW before approval.",
            status_code=409,
        )

    application.user_approved = True
    application.approved_at = datetime.now(UTC)
    db.add(application)
    db.commit()
    db.refresh(application)

    _record_event(
        db,
        application.id,
        "READY_FOR_REVIEW",
        "Application approved by user for manual submission",
    )
    return application


def confirm_application_submitted(db: Session, application: Application) -> Application:
    if application.status != ApplicationStatus.READY_FOR_REVIEW:
        raise ApplicationServiceError(
            "Application must be READY_FOR_REVIEW before submission.",
            status_code=409,
        )

    if not application.user_approved:
        raise ApplicationServiceError(
            "Application requires explicit user approval before submission.",
            status_code=409,
        )

    application.status = ApplicationStatus.APPLIED
    application.submitted_at = datetime.now(UTC)
    db.add(application)
    db.commit()
    db.refresh(application)

    _record_event(
        db,
        application.id,
        ApplicationStatus.APPLIED.value,
        "Application marked as submitted by explicit user confirmation",
    )
    return application


def _record_event(
    db: Session,
    application_id: int,
    event_type: str,
    description: str,
) -> None:
    event = ApplicationEvent(
        application_id=application_id,
        event_type=event_type,
        description=description,
        created_at=datetime.now(UTC),
    )
    db.add(event)
    db.commit()


def _resolve_match_score(db: Session, job_id: int, resume_id: int | None) -> int | None:
    if resume_id is None:
        return None

    match = db.scalar(
        select(JobMatch).where(
            JobMatch.job_id == job_id,
            JobMatch.resume_id == resume_id,
        )
    )
    if match is None or match.match_score is None:
        return None
    return int(round(match.match_score))
