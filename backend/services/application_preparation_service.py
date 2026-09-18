from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.ai.application_drafter import (
    generate_cover_letter,
    generate_screening_answer,
)
from backend.database.models import (
    Application,
    ApplicationEvent,
    ApplicationQuestion,
    ApplicationStatus,
    Job,
    JobMatch,
    QuestionStatus,
    Resume,
    UserProfile,
)
from backend.schemas.application import ApplicationCreate
from backend.schemas.application_preparation import (
    ApplicationPreparationRead,
    ApplicationQuestionRead,
    ApplicationReviewRead,
    PrepareApplicationRequest,
)
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.resume_analysis import CandidateProfile
from backend.services.application_service import create_application
from backend.services.matching_service import match_job_with_resume


class ApplicationPreparationServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def prepare_application(
    db: Session,
    payload: PrepareApplicationRequest,
) -> ApplicationPreparationRead:
    profile = db.get(UserProfile, payload.profile_id)
    if profile is None:
        raise ApplicationPreparationServiceError("Profile not found", status_code=404)

    job = db.get(Job, payload.job_id)
    if job is None:
        raise ApplicationPreparationServiceError("Job not found", status_code=404)

    resume = db.get(Resume, payload.resume_id)
    if resume is None:
        raise ApplicationPreparationServiceError("Resume not found", status_code=404)

    if resume.profile_id != profile.id:
        raise ApplicationPreparationServiceError(
            "Resume does not belong to profile", status_code=422
        )

    if resume.analysis_status != "COMPLETED" or not isinstance(
        resume.analysis_result, dict
    ):
        raise ApplicationPreparationServiceError(
            "Resume analysis is required before preparation.",
            status_code=422,
        )

    if job.analysis_status != "COMPLETED" or not isinstance(job.analysis_result, dict):
        raise ApplicationPreparationServiceError(
            "Job analysis is required before preparation.",
            status_code=422,
        )

    try:
        resume_analysis = CandidateProfile.model_validate(resume.analysis_result)
        job_analysis = JobAnalysis.model_validate(job.analysis_result)
    except ValidationError as exc:
        raise ApplicationPreparationServiceError(
            "Stored analysis data is invalid. Re-run analyses.",
            status_code=422,
        ) from exc

    match_result = match_job_with_resume(db, job_id=job.id, resume_id=resume.id)

    application = _get_or_create_application(
        db,
        job_id=job.id,
        profile_id=profile.id,
        resume_id=resume.id,
    )

    _set_status(
        db,
        application,
        ApplicationStatus.PREPARING,
        "Application preparation started",
    )

    if payload.force_regenerate:
        for question in list(application.questions):
            db.delete(question)
        db.flush()

    cover_letter = generate_cover_letter(
        profile=profile,
        resume_analysis=resume_analysis,
        job_analysis=job_analysis,
        job_title=job.title,
        company=job.company or "the company",
        job_description=job.description or "",
        match_result=match_result,
    )
    application.cover_letter = cover_letter

    existing_questions = {
        item.question.strip().lower(): item
        for item in application.questions
        if item.question
    }

    for raw_question in payload.screening_questions:
        question = raw_question.strip()
        if not question:
            continue

        existing = existing_questions.get(question.lower())
        if existing is not None and existing.status == QuestionStatus.APPROVED:
            continue

        answer, status = generate_screening_answer(
            question=question,
            profile=profile,
            resume_analysis=resume_analysis,
            job_analysis=job_analysis,
            match_result=match_result,
        )

        if existing is None:
            existing = ApplicationQuestion(
                application_id=application.id,
                question=question,
            )

        existing.answer = answer
        existing.status = status
        db.add(existing)

    application.resume_id = resume.id
    application.preparation_details = {
        "selected_resume_id": resume.id,
        "match_score": match_result.score,
        "unknown_fields": [],
        "fields_to_submit": [],
    }
    db.add(application)
    db.commit()
    db.refresh(application)

    _set_status(
        db,
        application,
        ApplicationStatus.READY_FOR_REVIEW,
        "Application preparation completed and ready for review",
    )

    return ApplicationPreparationRead(
        application_id=application.id,
        status=application.status,
        job_id=application.job_id,
        profile_id=application.profile_id,
        resume_id=application.resume_id,
        cover_letter=application.cover_letter,
        questions=[_question_read(item) for item in application.questions],
    )


def get_application_review(db: Session, application_id: int) -> ApplicationReviewRead:
    application = db.get(Application, application_id)
    if application is None:
        raise ApplicationPreparationServiceError(
            "Application not found",
            status_code=404,
        )

    match_score: int | None = None
    unknown_fields: list[str] = []
    fields_to_submit: list[dict[str, str]] = []

    details = application.preparation_details
    if isinstance(details, dict):
        raw_score = details.get("match_score")
        if isinstance(raw_score, int):
            match_score = raw_score
        raw_unknown = details.get("unknown_fields")
        if isinstance(raw_unknown, list):
            unknown_fields = [str(item) for item in raw_unknown]
        raw_fields = details.get("fields_to_submit")
        if isinstance(raw_fields, list):
            normalized_fields: list[dict[str, str]] = []
            for item in raw_fields:
                if isinstance(item, dict):
                    normalized_fields.append(
                        {
                            "field": str(item.get("field") or ""),
                            "value": str(item.get("value") or ""),
                        }
                    )
            fields_to_submit = normalized_fields

    if match_score is None and application.resume_id is not None:
        match_score = _resolve_match_score(
            db,
            application.job_id,
            application.resume_id,
        )

    return ApplicationReviewRead(
        application_id=application.id,
        status=application.status,
        user_approved=application.user_approved,
        job_title=application.job.title if application.job else None,
        company=application.job.company if application.job else None,
        job_url=application.job.url if application.job else None,
        match_score=match_score,
        selected_resume_id=application.resume_id,
        cover_letter=application.cover_letter,
        screening_answers=[_question_read(item) for item in application.questions],
        fields_to_submit=fields_to_submit,
        unknown_fields=unknown_fields,
        approved_at=application.approved_at,
    )


def regenerate_cover_letter(db: Session, application_id: int) -> ApplicationReviewRead:
    application = db.get(Application, application_id)
    if application is None:
        raise ApplicationPreparationServiceError(
            "Application not found",
            status_code=404,
        )

    if application.resume_id is None:
        raise ApplicationPreparationServiceError(
            "Application has no selected resume", status_code=422
        )

    profile = db.get(UserProfile, application.profile_id)
    resume = db.get(Resume, application.resume_id)
    job = db.get(Job, application.job_id)
    if profile is None or resume is None or job is None:
        raise ApplicationPreparationServiceError(
            "Application dependencies are missing", status_code=422
        )

    if not isinstance(resume.analysis_result, dict) or not isinstance(
        job.analysis_result, dict
    ):
        raise ApplicationPreparationServiceError(
            "Resume and job analyses are required before regeneration.",
            status_code=422,
        )

    resume_analysis = CandidateProfile.model_validate(resume.analysis_result)
    job_analysis = JobAnalysis.model_validate(job.analysis_result)
    match_result = match_job_with_resume(db, job_id=job.id, resume_id=resume.id)

    application.cover_letter = generate_cover_letter(
        profile=profile,
        resume_analysis=resume_analysis,
        job_analysis=job_analysis,
        job_title=job.title,
        company=job.company or "the company",
        job_description=job.description or "",
        match_result=match_result,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    _record_event(db, application.id, "PREPARING", "Cover letter regenerated")
    return get_application_review(db, application.id)


def _resolve_match_score(db: Session, job_id: int, resume_id: int) -> int | None:
    row = db.scalar(
        select(JobMatch).where(
            JobMatch.job_id == job_id,
            JobMatch.resume_id == resume_id,
        )
    )
    if row is None or row.match_score is None:
        return None
    return int(round(row.match_score))


def _get_or_create_application(
    db: Session,
    *,
    job_id: int,
    profile_id: int,
    resume_id: int,
) -> Application:
    existing = db.scalar(
        select(Application).where(
            Application.job_id == job_id,
            Application.profile_id == profile_id,
            Application.resume_id == resume_id,
        )
    )
    if existing is not None:
        return existing

    application = create_application(
        db,
        ApplicationCreate(
            job_id=job_id,
            profile_id=profile_id,
            resume_id=resume_id,
            status=ApplicationStatus.DISCOVERED,
        ),
    )
    _record_event(db, application.id, "DISCOVERED", "Application created")
    return application


def _set_status(
    db: Session,
    application: Application,
    status: ApplicationStatus,
    description: str,
) -> None:
    if application.status == status:
        return
    application.status = status
    db.add(application)
    db.commit()
    db.refresh(application)
    _record_event(db, application.id, status.value, description)


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


def _question_read(item: ApplicationQuestion) -> ApplicationQuestionRead:
    return ApplicationQuestionRead(
        id=item.id,
        question=item.question,
        answer=item.answer,
        status=item.status,
        updated_at=item.updated_at,
    )
