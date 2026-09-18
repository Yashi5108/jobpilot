from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import Job, JobMatch, Resume
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.job_match import JobMatchResult
from backend.schemas.resume_analysis import CandidateProfile
from backend.services.matching.matcher import match_resume_to_job


class MatchingServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def match_job_with_resume(
    db: Session,
    job_id: int,
    resume_id: int,
) -> JobMatchResult:
    job = db.get(Job, job_id)
    if job is None:
        raise MatchingServiceError("Job not found", status_code=404)

    resume = db.get(Resume, resume_id)
    if resume is None:
        raise MatchingServiceError("Resume not found", status_code=404)

    if resume.analysis_status != "COMPLETED" or not isinstance(
        resume.analysis_result, dict
    ):
        raise MatchingServiceError(
            "Resume analysis is required before matching.",
            status_code=422,
        )

    if job.analysis_status != "COMPLETED" or not isinstance(job.analysis_result, dict):
        raise MatchingServiceError(
            "Job analysis is required before matching.",
            status_code=422,
        )

    try:
        job_analysis = JobAnalysis.model_validate(job.analysis_result)
    except ValidationError as exc:
        raise MatchingServiceError(
            "Stored job analysis is invalid. Re-run job analysis.",
            status_code=422,
        ) from exc

    try:
        resume_analysis = CandidateProfile.model_validate(resume.analysis_result)
    except ValidationError as exc:
        raise MatchingServiceError(
            "Stored resume analysis is invalid. Re-run resume analysis.",
            status_code=422,
        ) from exc

    result = match_resume_to_job(
        profile_id=resume.profile_id,
        resume_id=resume.id,
        job_id=job.id,
        resume_analysis=resume_analysis,
        job_analysis=job_analysis,
    )

    existing = db.scalar(
        select(JobMatch).where(
            JobMatch.job_id == job.id,
            JobMatch.resume_id == resume.id,
        )
    )

    explanation = _build_explanation(result)
    if existing is None:
        match_row = JobMatch(
            job_id=job.id,
            profile_id=resume.profile_id,
            resume_id=resume.id,
            match_score=float(result.score),
            matching_skills=(
                result.matched_required_skills + result.matched_preferred_skills
            ),
            missing_skills=(
                result.missing_required_skills + result.missing_preferred_skills
            ),
            experience_match=_status_to_bool(result.experience_result),
            preference_match=_status_to_bool(
                "MATCHED"
                if not result.missing_preferred_skills and result.preferred_skill_score
                else (
                    "NOT_MATCHED"
                    if result.preferred_skill_score is not None
                    else "UNKNOWN"
                )
            ),
            location_match=None,
            explanation=explanation,
            match_details=result.model_dump(mode="json"),
        )
        db.add(match_row)
    else:
        existing.profile_id = resume.profile_id
        existing.match_score = float(result.score)
        existing.matching_skills = (
            result.matched_required_skills + result.matched_preferred_skills
        )
        existing.missing_skills = (
            result.missing_required_skills + result.missing_preferred_skills
        )
        existing.experience_match = _status_to_bool(result.experience_result)
        existing.preference_match = _status_to_bool(
            "MATCHED"
            if not result.missing_preferred_skills and result.preferred_skill_score
            else (
                "NOT_MATCHED" if result.preferred_skill_score is not None else "UNKNOWN"
            )
        )
        existing.location_match = None
        existing.explanation = explanation
        existing.match_details = result.model_dump(mode="json")
        db.add(existing)

    db.commit()
    return get_job_match_for_resume(db, job.id, resume.id)


def get_job_matches(
    db: Session,
    job_id: int,
) -> list[JobMatchResult]:
    job = db.get(Job, job_id)
    if job is None:
        raise MatchingServiceError("Job not found", status_code=404)

    rows = list(
        db.scalars(
            select(JobMatch)
            .where(JobMatch.job_id == job_id)
            .order_by(JobMatch.updated_at.desc(), JobMatch.id.desc())
        ).all()
    )
    results: list[JobMatchResult] = []
    for row in rows:
        validated = _row_to_result(row)
        if validated is not None:
            results.append(validated)
    return results


def get_job_match_for_resume(
    db: Session,
    job_id: int,
    resume_id: int,
) -> JobMatchResult:
    row = db.scalar(
        select(JobMatch).where(
            JobMatch.job_id == job_id,
            JobMatch.resume_id == resume_id,
        )
    )
    if row is None:
        raise MatchingServiceError("Match not found", status_code=404)

    validated = _row_to_result(row)
    if validated is None:
        raise MatchingServiceError(
            "Stored match details are invalid. Re-run matching.",
            status_code=422,
        )
    return validated


def _row_to_result(row: JobMatch) -> JobMatchResult | None:
    if not isinstance(row.match_details, dict):
        return None

    try:
        return JobMatchResult.model_validate(row.match_details)
    except ValidationError:
        return None


def _build_explanation(result: JobMatchResult) -> str:
    required_total = len(result.matched_required_skills) + len(
        result.missing_required_skills
    )
    summary = [
        f"Score: {result.score}/100",
        (
            "Required skills matched: "
            f"{len(result.matched_required_skills)} / "
            f"{required_total}"
        ),
    ]
    if result.gaps:
        summary.append(f"Top gap: {result.gaps[0]}")
    return " | ".join(summary)


def _status_to_bool(status: str) -> bool | None:
    if status == "MATCHED":
        return True
    if status == "NOT_MATCHED":
        return False
    return None
