from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.database.models import ApplicationStatus, QuestionStatus

DEFAULT_SCREENING_QUESTIONS = [
    "Why are you interested in this role?",
    "How many years of Python experience do you have?",
    "Are you authorized to work in the job location?",
    "Are you willing to relocate if required?",
]


class PrepareApplicationRequest(BaseModel):
    job_id: int = Field(gt=0)
    profile_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    screening_questions: list[str] = Field(
        default_factory=lambda: DEFAULT_SCREENING_QUESTIONS.copy()
    )
    force_regenerate: bool = False


class ApplicationQuestionRead(BaseModel):
    id: int
    question: str
    answer: str | None
    status: QuestionStatus
    updated_at: datetime


class ApplicationQuestionUpdate(BaseModel):
    id: int = Field(gt=0)
    answer: str | None = None
    status: QuestionStatus | None = None


class ApplicationReviewUpdateRequest(BaseModel):
    cover_letter: str | None = None
    cover_letter_status: QuestionStatus | None = None
    screening_answers: list[ApplicationQuestionUpdate] = Field(default_factory=list)


class ApplicationPreparationRead(BaseModel):
    application_id: int
    status: ApplicationStatus
    job_id: int
    profile_id: int
    resume_id: int | None
    cover_letter: str | None
    questions: list[ApplicationQuestionRead]


class ApplicationReviewRead(BaseModel):
    application_id: int
    status: ApplicationStatus
    user_approved: bool
    job_title: str | None
    company: str | None
    job_url: str | None
    match_score: int | None
    selected_resume_id: int | None
    cover_letter: str | None
    cover_letter_status: QuestionStatus | None = None
    screening_answers: list[ApplicationQuestionRead]
    fields_to_submit: list[dict[str, str]] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    approved_at: datetime | None = None
