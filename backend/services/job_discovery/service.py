from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from backend.database.models import Resume, UserProfile
from backend.schemas.job import JobCreate
from backend.schemas.job_discovery import (
    JobDiscoveryErrorRead,
    JobDiscoveryLinkRead,
    JobDiscoveryRequest,
    JobDiscoveryResponse,
    JobDiscoveryResultRead,
    JobSearchCriteriaRead,
)
from backend.schemas.resume_analysis import CandidateExperience, CandidateProfile
from backend.services.job_analysis_service import JobAnalysisServiceError, analyze_job
from backend.services.job_discovery.base import (
    JobDiscoveryConnector,
    JobDiscoveryConnectorError,
)
from backend.services.job_discovery.connectors import (
    RemotiveConnector,
    WebSearchConnector,
)
from backend.services.job_discovery.models import (
    AggregatedDiscoveredJob,
    DiscoveredJob,
    DiscoveredJobAction,
    DiscoveryError,
    DiscoverySearchCriteria,
)
from backend.services.job_service import JobServiceError, upsert_job
from backend.services.matching_service import (
    MatchingServiceError,
    match_job_with_resume,
)


class JobDiscoveryServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def discover_jobs_for_resume(
    db: Session,
    payload: JobDiscoveryRequest,
) -> JobDiscoveryResponse:
    resume = db.get(Resume, payload.resume_id)
    if resume is None:
        raise JobDiscoveryServiceError("Resume not found", status_code=404)

    if resume.analysis_status != "COMPLETED" or not isinstance(
        resume.analysis_result, dict
    ):
        raise JobDiscoveryServiceError(
            "Resume analysis is required before discovering jobs.",
            status_code=422,
        )

    profile = db.get(UserProfile, resume.profile_id)
    if profile is None:
        raise JobDiscoveryServiceError("Profile not found", status_code=404)

    try:
        resume_profile = CandidateProfile.model_validate(resume.analysis_result)
    except Exception as exc:
        raise JobDiscoveryServiceError(
            "Stored resume analysis is invalid. Re-run resume analysis.",
            status_code=422,
        ) from exc

    criteria = build_search_criteria(
        resume_profile,
        profile,
        payload.max_results_per_source,
    )
    connectors = _build_connectors(payload)

    discovered: list[DiscoveredJob] = []
    errors: list[DiscoveryError] = []
    for connector in connectors:
        try:
            discovered.extend(connector.search(criteria))
        except JobDiscoveryConnectorError as exc:
            errors.append(
                DiscoveryError(source=connector.source_name, message=str(exc))
            )

    deduplicated = deduplicate_discovered_jobs(discovered)

    results: list[JobDiscoveryResultRead] = []
    for item in deduplicated:
        job = _persist_discovered_job(db, item.primary)
        try:
            analyze_job(db, job.id, force=False)
            match = match_job_with_resume(db, job.id, resume.id)
        except (JobAnalysisServiceError, MatchingServiceError) as exc:
            errors.append(
                DiscoveryError(
                    source=item.primary.source_name,
                    message=(f"{item.primary.title} at {item.primary.company}: {exc}"),
                )
            )
            continue

        action = _resolve_action(item.primary)
        result = JobDiscoveryResultRead(
            job_id=job.id,
            title=job.title,
            company=job.company or item.primary.company,
            location=job.location,
            job_url=job.url,
            source=item.primary.source_name,
            source_type=item.primary.source_type,
            discovered_sources=item.discovered_sources,
            discovered_links=[
                JobDiscoveryLinkRead.model_validate(
                    {
                        "source": link.source,
                        "source_type": link.source_type,
                        "job_url": link.job_url,
                    }
                )
                for link in item.discovered_links
            ],
            external_id=job.external_id,
            discovered_at=job.discovered_at,
            action=action,
            action_url=job.url,
            match_score=match.score,
            match=match,
        )
        if (
            payload.min_match_score is not None
            and result.match_score < payload.min_match_score
        ):
            continue
        results.append(result)

    results.sort(key=lambda item: item.match_score, reverse=True)
    return JobDiscoveryResponse(
        resume_id=resume.id,
        criteria=JobSearchCriteriaRead(
            queries=criteria.queries,
            skills=criteria.skills,
            location=criteria.location,
            remote_preference=criteria.remote_preference,
            years_of_experience=criteria.years_of_experience,
        ),
        total_discovered=len(discovered),
        total_deduplicated=len(deduplicated),
        total_matched=len(results),
        results=results,
        errors=[
            JobDiscoveryErrorRead(source=item.source, message=item.message)
            for item in errors
        ],
    )


def build_search_criteria(
    resume_profile: CandidateProfile,
    profile: UserProfile,
    limit_per_source: int,
) -> DiscoverySearchCriteria:
    queries: list[str] = []
    if resume_profile.headline:
        queries.append(resume_profile.headline.strip())

    for item in resume_profile.experience:
        if item.title and item.title.strip():
            queries.append(item.title.strip())

    skills = [item.name.strip() for item in resume_profile.skills if item.name.strip()]
    for skill in skills[:3]:
        queries.append(skill)

    deduped_queries = _dedupe_text(queries)[:5]
    if not deduped_queries:
        raise JobDiscoveryServiceError(
            (
                "Resume analysis did not contain enough role or skill "
                "information to search."
            ),
            status_code=422,
        )

    return DiscoverySearchCriteria(
        queries=deduped_queries,
        skills=_dedupe_text(skills)[:8],
        location=(resume_profile.location or profile.location),
        remote_preference=profile.remote_preference,
        years_of_experience=(
            profile.years_of_experience
            if profile.years_of_experience is not None
            else _estimate_years_of_experience(resume_profile.experience)
        ),
        limit_per_source=limit_per_source,
    )


def deduplicate_discovered_jobs(
    jobs: list[DiscoveredJob],
) -> list[AggregatedDiscoveredJob]:
    deduped: dict[tuple[str, ...], AggregatedDiscoveredJob] = {}

    for job in jobs:
        key = _discovery_dedupe_key(job)
        source_label = f"{job.source_name} ({job.source_type})"
        existing = deduped.get(key)
        if existing is None:
            aggregate = AggregatedDiscoveredJob(primary=job)
            aggregate.add_source(source_label, job)
            deduped[key] = aggregate
        else:
            existing.add_source(source_label, job)

    return list(deduped.values())


def _build_connectors(payload: JobDiscoveryRequest) -> list[JobDiscoveryConnector]:
    requested = {item.strip().lower() for item in payload.sources if item.strip()}
    if not requested:
        requested = {"remotive"}

    connectors: list[JobDiscoveryConnector] = []
    if "remotive" in requested:
        connectors.append(
            RemotiveConnector(limit_per_source=payload.max_results_per_source)
        )
    if "web_search" in requested:
        connectors.append(
            WebSearchConnector(limit_per_source=payload.max_results_per_source)
        )
    return connectors


def _persist_discovered_job(db: Session, item: DiscoveredJob):
    payload = JobCreate.model_validate(
        {
            "title": item.title,
            "company": item.company,
            "location": item.location,
            "description": item.description,
            "url": item.job_url,
            "source_name": item.source_name,
            "source_type": item.source_type,
            "source_base_url": item.source_base_url,
            "external_id": item.external_id,
            "discovered_at": item.discovered_at or datetime.now(UTC),
        }
    )

    try:
        job, _ = upsert_job(db, payload)
    except JobServiceError as exc:
        raise JobDiscoveryServiceError(str(exc), status_code=exc.status_code) from exc
    return job


def _resolve_action(item: DiscoveredJob) -> DiscoveredJobAction:
    if item.supports_apply and item.job_url:
        return DiscoveredJobAction.APPLY
    return DiscoveredJobAction.OPEN_AND_APPLY


def _discovery_dedupe_key(job: DiscoveredJob) -> tuple[str, ...]:
    if job.external_id:
        return (
            "external_id",
            job.source_name.strip().lower(),
            job.external_id.strip().lower(),
        )

    normalized_url = _normalize_url(job.job_url)
    if normalized_url:
        return ("url", normalized_url)

    return (
        "identity",
        _normalize_company(job.company),
        _normalize_title(job.title),
        _normalize_location(job.location),
    )


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return None
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _normalize_company(value: str) -> str:
    return _normalize_text_for_identity(value)


def _normalize_location(value: str | None) -> str:
    return _normalize_text_for_identity(value or "")


def _normalize_title(value: str) -> str:
    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"\bsr\.?\b", " senior ", normalized)
    normalized = re.sub(r"\bjr\.?\b", " junior ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _normalize_text_for_identity(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _dedupe_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def _estimate_years_of_experience(
    experience: list[CandidateExperience],
) -> float | None:
    starts: list[datetime] = []
    ends: list[datetime] = []

    for item in experience:
        start = _parse_partial_date(item.start_date)
        if start is None:
            continue
        starts.append(start)

        end = _parse_partial_date(item.end_date)
        if end is None and item.is_current:
            end = datetime.now(UTC)
        if end is not None:
            ends.append(end)

    if not starts:
        return None

    earliest = min(starts)
    latest = max(ends) if ends else datetime.now(UTC)
    if latest < earliest:
        return None

    return round((latest - earliest).days / 365.25, 1)


def _parse_partial_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) == 4 and text.isdigit():
        return datetime(int(text), 1, 1, tzinfo=UTC)
    if len(text) == 7 and text[4] == "-":
        year, month = text.split("-")
        if year.isdigit() and month.isdigit():
            month_value = int(month)
            if 1 <= month_value <= 12:
                return datetime(int(year), month_value, 1, tzinfo=UTC)
    return None
