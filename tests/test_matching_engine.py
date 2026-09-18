from __future__ import annotations

from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.resume_analysis import CandidateProfile
from backend.services.matching.matcher import match_resume_to_job


def _build_resume_profile(
    *,
    skills: list[str],
    certs: list[str] | None = None,
    education: list[dict[str, str | None]] | None = None,
    experience: list[dict[str, object]] | None = None,
) -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "name": "Test User",
            "skills": [{"name": skill} for skill in skills],
            "certifications": [{"name": cert} for cert in (certs or [])],
            "education": education or [],
            "experience": experience
            or [
                {
                    "title": "Engineer",
                    "company": "Example",
                    "start_date": "2018-01",
                    "end_date": None,
                    "is_current": True,
                    "responsibilities": ["Build backend systems"],
                }
            ],
            "projects": [],
            "achievements": [],
            "languages": [],
        }
    )


def _build_job_analysis(
    *,
    required_skills: list[str],
    preferred_skills: list[str] | None = None,
    min_years: float | None = None,
    education_requirements: list[str] | None = None,
    required_certifications: list[str] | None = None,
    preferred_certifications: list[str] | None = None,
    domain_requirements: list[str] | None = None,
) -> JobAnalysis:
    return JobAnalysis.model_validate(
        {
            "required_skills": [
                {"name": skill, "category": "language"} for skill in required_skills
            ],
            "preferred_skills": [
                {"name": skill, "category": "other"}
                for skill in (preferred_skills or [])
            ],
            "minimum_years_experience": min_years,
            "preferred_years_experience": None,
            "experience_requirements": [],
            "education_requirements": education_requirements or [],
            "required_certifications": required_certifications or [],
            "preferred_certifications": preferred_certifications or [],
            "responsibilities": [],
            "domain_requirements": domain_requirements or [],
            "communication_requirements": [],
            "leadership_requirements": [],
            "work_authorization_requirements": [],
            "travel_requirements": [],
            "other_requirements": [],
        }
    )


def test_perfect_match_scores_100() -> None:
    profile = _build_resume_profile(
        skills=["Python", "FastAPI", "PostgreSQL", "AWS", "Kubernetes"],
        certs=["AWS Certified Solutions Architect"],
        education=[{"degree": "Bachelor of Computer Science"}],
        experience=[
            {
                "start_date": "2015-01",
                "end_date": None,
                "is_current": True,
                "responsibilities": ["Fintech backend"],
            }
        ],
    )
    job = _build_job_analysis(
        required_skills=["Python", "FastAPI", "PostgreSQL"],
        preferred_skills=["AWS", "Kubernetes"],
        min_years=5,
        education_requirements=["bachelor"],
        required_certifications=["AWS Certified Solutions Architect"],
        domain_requirements=["fintech"],
    )

    result = match_resume_to_job(
        profile_id=1,
        resume_id=2,
        job_id=3,
        resume_analysis=profile,
        job_analysis=job,
    )

    assert result.score == 100
    assert result.missing_required_skills == []
    assert result.experience_result == "MATCHED"


def test_missing_required_skill_penalizes_more_than_missing_preferred() -> None:
    base_resume = _build_resume_profile(skills=["Python", "FastAPI", "AWS"])

    missing_required_job = _build_job_analysis(
        required_skills=["Python", "FastAPI", "PostgreSQL"],
        preferred_skills=["AWS"],
    )
    missing_preferred_job = _build_job_analysis(
        required_skills=["Python", "FastAPI"],
        preferred_skills=["AWS", "Kubernetes"],
    )

    required_result = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=base_resume,
        job_analysis=missing_required_job,
    )
    preferred_result = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=base_resume,
        job_analysis=missing_preferred_job,
    )

    assert "PostgreSQL" in required_result.missing_required_skills
    assert "Kubernetes" in preferred_result.missing_preferred_skills
    assert required_result.score < preferred_result.score


def test_experience_match_states() -> None:
    job = _build_job_analysis(required_skills=["Python"], min_years=5)

    matched = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=_build_resume_profile(
            skills=["Python"],
            experience=[{"start_date": "2010", "end_date": None, "is_current": True}],
        ),
        job_analysis=job,
    )
    not_matched = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=_build_resume_profile(
            skills=["Python"],
            experience=[{"start_date": "2024", "end_date": None, "is_current": True}],
        ),
        job_analysis=job,
    )
    unknown = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=_build_resume_profile(
            skills=["Python"],
            experience=[{"title": "Engineer"}],
        ),
        job_analysis=job,
    )

    assert matched.experience_result == "MATCHED"
    assert not_matched.experience_result == "NOT_MATCHED"
    assert unknown.experience_result == "UNKNOWN"


def test_no_education_or_cert_requirement_does_not_penalize() -> None:
    profile = _build_resume_profile(skills=["Python", "FastAPI"])
    job = _build_job_analysis(
        required_skills=["Python", "FastAPI"],
        education_requirements=[],
        required_certifications=[],
        preferred_certifications=[],
    )

    result = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=profile,
        job_analysis=job,
    )

    assert result.education_result == "NOT_REQUIRED"
    assert result.certification_result == "NOT_REQUIRED"
    assert result.score == 100


def test_skill_normalization_and_dedupe() -> None:
    profile = _build_resume_profile(
        skills=["python3", "Fast API", "Amazon Web Services"]
    )
    job = _build_job_analysis(
        required_skills=["Python", "FastAPI", "Postgres", "PostgreSQL"],
        preferred_skills=["AWS"],
    )

    result = match_resume_to_job(
        1,
        1,
        1,
        resume_analysis=profile,
        job_analysis=job,
    )

    assert "Python" in result.matched_required_skills
    assert "FastAPI" in result.matched_required_skills
    assert (
        "Postgres" in result.missing_required_skills
        or "PostgreSQL" in result.missing_required_skills
    )
    assert result.matched_preferred_skills == ["AWS"]


def test_determinism_same_input_same_result() -> None:
    profile = _build_resume_profile(skills=["Python", "FastAPI"])
    job = _build_job_analysis(
        required_skills=["Python", "FastAPI", "PostgreSQL"],
        preferred_skills=["AWS"],
    )

    first = match_resume_to_job(1, 1, 1, profile, job)
    second = match_resume_to_job(1, 1, 1, profile, job)

    assert first.model_dump(exclude={"matched_at"}) == second.model_dump(
        exclude={"matched_at"}
    )
