from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.ai.job_analyzer import JobAnalysisError, analyze_job_description
from backend.database.models import Job
from backend.schemas.job_analysis import JobAnalysis


class JobAnalysisServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def analyze_job(
    db: Session,
    job_id: int,
    force: bool = False,
) -> tuple[Job, JobAnalysis]:
    job = db.get(Job, job_id)
    if job is None:
        raise JobAnalysisServiceError("Job not found", status_code=404)

    if not job.description or not job.description.strip():
        raise JobAnalysisServiceError(
            "Job has no description. Add a job description first.",
            status_code=422,
        )

    if (
        not force
        and job.analysis_status == "COMPLETED"
        and isinstance(job.analysis_result, dict)
    ):
        try:
            analysis = JobAnalysis.model_validate(job.analysis_result)
        except ValidationError:
            force = True
        else:
            return job, analysis

    job.analysis_status = "ANALYZING"
    job.analysis_result = None
    job.analyzed_at = None
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        analysis = analyze_job_description(job.description)
    except JobAnalysisError as exc:
        job.analysis_status = "FAILED"
        job.analysis_result = None
        job.analyzed_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        raise JobAnalysisServiceError(str(exc), status_code=exc.status_code) from exc

    job.analysis_status = "COMPLETED"
    job.analysis_result = analysis.model_dump()
    job.analyzed_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job, analysis


def get_job_analysis(
    db: Session,
    job_id: int,
) -> tuple[Job, JobAnalysis | None]:
    job = db.get(Job, job_id)
    if job is None:
        raise JobAnalysisServiceError("Job not found", status_code=404)

    analysis: JobAnalysis | None = None
    if isinstance(job.analysis_result, dict):
        try:
            analysis = JobAnalysis.model_validate(job.analysis_result)
        except ValidationError:
            analysis = None

    return job, analysis
