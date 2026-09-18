from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.ai.resume_analyzer import ResumeAnalysisError, analyze_resume_text
from backend.database.models import Resume
from backend.schemas.resume_analysis import CandidateProfile


class ResumeAnalysisServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def analyze_resume(
    db: Session,
    resume_id: int,
    force: bool = False,
) -> tuple[Resume, CandidateProfile]:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise ResumeAnalysisServiceError("Resume not found", status_code=404)

    if not resume.normalized_text or not resume.normalized_text.strip():
        raise ResumeAnalysisServiceError(
            "Resume has no parsed text. Upload and parse the resume first.",
            status_code=422,
        )

    if (
        not force
        and resume.analysis_status == "COMPLETED"
        and isinstance(resume.analysis_result, dict)
    ):
        try:
            profile = CandidateProfile.model_validate(resume.analysis_result)
        except ValidationError:
            force = True
        else:
            return resume, profile

    resume.analysis_status = "ANALYZING"
    resume.analysis_result = None
    resume.analyzed_at = None
    db.add(resume)
    db.commit()
    db.refresh(resume)

    try:
        profile = analyze_resume_text(resume.normalized_text)
    except ResumeAnalysisError as exc:
        resume.analysis_status = "FAILED"
        resume.analysis_result = None
        resume.analyzed_at = datetime.now(timezone.utc)
        db.add(resume)
        db.commit()
        db.refresh(resume)
        raise ResumeAnalysisServiceError(str(exc), status_code=exc.status_code) from exc

    resume.analysis_status = "COMPLETED"
    resume.analysis_result = profile.model_dump()
    resume.analyzed_at = datetime.now(timezone.utc)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume, profile


def get_resume_analysis(
    db: Session,
    resume_id: int,
) -> tuple[Resume, CandidateProfile | None]:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise ResumeAnalysisServiceError("Resume not found", status_code=404)

    profile: CandidateProfile | None = None
    if isinstance(resume.analysis_result, dict):
        try:
            profile = CandidateProfile.model_validate(resume.analysis_result)
        except ValidationError:
            profile = None
    return resume, profile
