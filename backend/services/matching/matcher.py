from __future__ import annotations

from datetime import UTC, datetime

from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.job_match import JobMatchResult, MatchStatus
from backend.schemas.resume_analysis import CandidateExperience, CandidateProfile
from backend.services.matching.normalization import (
    normalize_free_text,
    normalize_skill_name,
    normalize_text,
)
from backend.services.matching.scoring import UNKNOWN_SCORE, compute_final_score


def match_resume_to_job(
    profile_id: int,
    resume_id: int,
    job_id: int,
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
) -> JobMatchResult:
    resume_skill_map = _build_resume_skill_map(resume_analysis)

    required_job_skill_names = [item.name for item in job_analysis.required_skills]
    preferred_job_skill_names = [item.name for item in job_analysis.preferred_skills]

    required_matched, required_missing = _match_skills(
        required_job_skill_names,
        resume_skill_map,
    )
    preferred_matched, preferred_missing = _match_skills(
        preferred_job_skill_names,
        resume_skill_map,
    )

    required_score = _score_ratio(required_matched, required_job_skill_names)
    preferred_score = _score_ratio(preferred_matched, preferred_job_skill_names)

    experience_result, experience_score = _match_experience(
        resume_analysis,
        job_analysis,
    )

    education_result, education_score = _match_education(
        resume_analysis,
        job_analysis,
    )

    (
        certification_result,
        certification_score,
        matched_required_certs,
        missing_required_certs,
        matched_preferred_certs,
        missing_preferred_certs,
    ) = _match_certifications(resume_analysis, job_analysis)

    domain_result, domain_score = _match_domain_requirements(
        resume_analysis,
        job_analysis,
    )

    score_breakdown = compute_final_score(
        {
            "required_skills": required_score,
            "preferred_skills": preferred_score,
            "experience": experience_score,
            "education": education_score,
            "certification": certification_score,
            "domain": domain_score,
        }
    )

    strengths, gaps = _build_strengths_and_gaps(
        required_matched=required_matched,
        required_missing=required_missing,
        preferred_matched=preferred_matched,
        preferred_missing=preferred_missing,
        experience_result=experience_result,
        education_result=education_result,
        certification_result=certification_result,
        domain_result=domain_result,
        missing_required_certifications=missing_required_certs,
    )

    return JobMatchResult(
        job_id=job_id,
        resume_id=resume_id,
        profile_id=profile_id,
        score=score_breakdown.final_score,
        required_skill_score=score_breakdown.normalized_dimension_scores[
            "required_skills"
        ],
        preferred_skill_score=score_breakdown.normalized_dimension_scores[
            "preferred_skills"
        ],
        experience_score=score_breakdown.normalized_dimension_scores["experience"],
        education_score=score_breakdown.normalized_dimension_scores["education"],
        certification_score=score_breakdown.normalized_dimension_scores[
            "certification"
        ],
        domain_score=score_breakdown.normalized_dimension_scores["domain"],
        matched_required_skills=required_matched,
        missing_required_skills=required_missing,
        matched_preferred_skills=preferred_matched,
        missing_preferred_skills=preferred_missing,
        matched_required_certifications=matched_required_certs,
        missing_required_certifications=missing_required_certs,
        matched_preferred_certifications=matched_preferred_certs,
        missing_preferred_certifications=missing_preferred_certs,
        experience_result=experience_result,
        education_result=education_result,
        certification_result=certification_result,
        domain_result=domain_result,
        strengths=strengths,
        gaps=gaps,
        matched_at=datetime.now(UTC),
    )


def _build_resume_skill_map(resume_analysis: CandidateProfile) -> dict[str, str]:
    result: dict[str, str] = {}
    for skill in resume_analysis.skills:
        normalized = normalize_skill_name(skill.name)
        if not normalized:
            continue
        if normalized not in result:
            result[normalized] = skill.name.strip()

    # Include project technologies as supporting deterministic skill signals.
    for project in resume_analysis.projects:
        for tech in project.technologies:
            normalized = normalize_skill_name(tech)
            if normalized and normalized not in result:
                result[normalized] = tech.strip()

    return result


def _match_skills(
    job_skill_names: list[str],
    resume_skill_map: dict[str, str],
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    for raw_skill in job_skill_names:
        normalized = normalize_skill_name(raw_skill)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        if normalized in resume_skill_map:
            matched.append(raw_skill)
        else:
            missing.append(raw_skill)

    return matched, missing


def _score_ratio(matched: list[str], total_items: list[str]) -> float | None:
    unique_total = len(
        {normalize_skill_name(item) for item in total_items if item.strip()}
    )
    if unique_total == 0:
        return None
    return len(matched) / unique_total


def _match_experience(
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
) -> tuple[MatchStatus, float | None]:
    required_years = _resolve_required_experience_years(job_analysis)
    if required_years is None:
        return "NOT_REQUIRED", None

    resume_years = _estimate_resume_years(resume_analysis.experience)
    if resume_years is None:
        return "UNKNOWN", UNKNOWN_SCORE

    if resume_years >= required_years:
        return "MATCHED", 1.0

    return "NOT_MATCHED", 0.0


def _resolve_required_experience_years(job_analysis: JobAnalysis) -> float | None:
    candidates: list[float] = []
    if job_analysis.minimum_years_experience is not None:
        candidates.append(job_analysis.minimum_years_experience)

    for requirement in job_analysis.experience_requirements:
        if requirement.minimum_years is not None:
            candidates.append(requirement.minimum_years)

    if not candidates:
        return None
    return max(candidates)


def _estimate_resume_years(experience: list[CandidateExperience]) -> float | None:
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

    delta_days = (latest - earliest).days
    return round(delta_days / 365.25, 1)


def _parse_partial_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None

    if len(text) == 4 and text.isdigit():
        return datetime(int(text), 1, 1, tzinfo=UTC)

    if len(text) == 7 and text[4] == "-":
        year, month = text.split("-")
        if year.isdigit() and month.isdigit():
            m = int(month)
            if 1 <= m <= 12:
                return datetime(int(year), m, 1, tzinfo=UTC)

    return None


def _match_education(
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
) -> tuple[MatchStatus, float | None]:
    requirements = [
        normalize_free_text(item) for item in job_analysis.education_requirements
    ]
    requirements = [item for item in requirements if item]
    if not requirements:
        return "NOT_REQUIRED", None

    resume_education_text = " ".join(
        normalize_free_text(
            " ".join(
                filter(None, [entry.degree, entry.field_of_study, entry.institution])
            )
        )
        for entry in resume_analysis.education
    ).strip()

    if not resume_education_text:
        return "UNKNOWN", UNKNOWN_SCORE

    matched_all = all(
        requirement in resume_education_text for requirement in requirements
    )
    if matched_all:
        return "MATCHED", 1.0

    return "NOT_MATCHED", 0.0


def _match_certifications(
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
) -> tuple[MatchStatus, float | None, list[str], list[str], list[str], list[str]]:
    required = _normalize_with_original(job_analysis.required_certifications)
    preferred = _normalize_with_original(job_analysis.preferred_certifications)

    if not required and not preferred:
        return "NOT_REQUIRED", None, [], [], [], []

    resume_cert_map: dict[str, str] = {}
    for cert in resume_analysis.certifications:
        normalized = normalize_free_text(cert.name)
        if normalized and normalized not in resume_cert_map:
            resume_cert_map[normalized] = cert.name.strip()

    if not resume_cert_map:
        return (
            "UNKNOWN",
            UNKNOWN_SCORE,
            [],
            [item[1] for item in required],
            [],
            [item[1] for item in preferred],
        )

    matched_required, missing_required = _match_text_requirements(
        required,
        resume_cert_map,
    )
    matched_preferred, missing_preferred = _match_text_requirements(
        preferred,
        resume_cert_map,
    )

    if required:
        required_ratio = len(matched_required) / len(required)
        preferred_ratio = len(matched_preferred) / len(preferred) if preferred else 1.0
        score = (required_ratio * 0.8) + (preferred_ratio * 0.2)
        status: MatchStatus = "MATCHED" if not missing_required else "NOT_MATCHED"
    else:
        score = len(matched_preferred) / len(preferred) if preferred else 1.0
        status = "MATCHED" if not missing_preferred else "NOT_MATCHED"

    return (
        status,
        round(score, 4),
        matched_required,
        missing_required,
        matched_preferred,
        missing_preferred,
    )


def _match_domain_requirements(
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
) -> tuple[MatchStatus, float | None]:
    requirements = _dedupe_text(job_analysis.domain_requirements)
    if not requirements:
        return "NOT_REQUIRED", None

    corpus_parts: list[str] = []
    for text in [resume_analysis.headline, resume_analysis.summary]:
        if text:
            corpus_parts.append(normalize_free_text(text))

    for exp in resume_analysis.experience:
        for text in [exp.title, exp.company, exp.location, *exp.responsibilities]:
            if text:
                corpus_parts.append(normalize_free_text(text))

    for project in resume_analysis.projects:
        for text in [project.name, project.description, *project.technologies]:
            if text:
                corpus_parts.append(normalize_free_text(text))

    corpus = " ".join(corpus_parts).strip()
    if not corpus:
        return "UNKNOWN", UNKNOWN_SCORE

    matched_count = sum(1 for req in requirements if req in corpus)
    if matched_count == len(requirements):
        return "MATCHED", 1.0

    return "NOT_MATCHED", round(matched_count / len(requirements), 4)


def _build_strengths_and_gaps(
    required_matched: list[str],
    required_missing: list[str],
    preferred_matched: list[str],
    preferred_missing: list[str],
    experience_result: MatchStatus,
    education_result: MatchStatus,
    certification_result: MatchStatus,
    domain_result: MatchStatus,
    missing_required_certifications: list[str],
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    gaps: list[str] = []

    for skill in required_matched:
        strengths.append(f"Required skill matched: {skill}")
    for skill in preferred_matched:
        strengths.append(f"Preferred skill matched: {skill}")

    for skill in required_missing:
        gaps.append(f"Missing required skill: {skill}")
    for skill in preferred_missing:
        gaps.append(f"Missing preferred skill: {skill}")

    if experience_result == "MATCHED":
        strengths.append("Experience requirement satisfied")
    elif experience_result == "NOT_MATCHED":
        gaps.append("Experience requirement not satisfied")

    if education_result == "MATCHED":
        strengths.append("Education requirement satisfied")
    elif education_result == "NOT_MATCHED":
        gaps.append("Education requirement not satisfied")

    if certification_result == "MATCHED":
        strengths.append("Certification requirements satisfied")
    elif certification_result == "NOT_MATCHED":
        for cert in missing_required_certifications:
            gaps.append(f"Missing required certification: {cert}")

    if domain_result == "MATCHED":
        strengths.append("Domain requirements matched")
    elif domain_result == "NOT_MATCHED":
        gaps.append("Domain requirements partially or fully unmatched")

    return _dedupe_text(strengths), _dedupe_text(gaps)


def _dedupe_text(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _match_text_requirements(
    requirements: list[tuple[str, str]],
    resume_text_map: dict[str, str],
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    missing: list[str] = []
    resume_keys = list(resume_text_map.keys())

    for requirement_norm, requirement_label in requirements:
        if any(requirement_norm in candidate for candidate in resume_keys):
            matched.append(requirement_label)
        else:
            missing.append(requirement_label)

    return matched, missing


def _normalize_with_original(values: list[str]) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in values:
        label = raw.strip()
        if not label:
            continue
        key = normalize_free_text(label)
        if key in seen:
            continue
        seen.add(key)
        normalized.append((key, label))
    return normalized
