from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.job_analysis import JobAnalysis


def test_job_analysis_valid_payload() -> None:
    payload = {
        "role_summary": "Build backend APIs for a B2B platform.",
        "seniority_level": "Senior",
        "employment_type": "Full-time",
        "work_arrangement": "Hybrid",
        "location": "Bengaluru",
        "required_skills": [
            {"name": "Python", "category": "language"},
            {"name": "FastAPI", "category": "framework"},
        ],
        "preferred_skills": [{"name": "Kubernetes", "category": "devops"}],
        "minimum_years_experience": 5,
        "preferred_years_experience": 7,
        "experience_requirements": [
            {
                "requirement": "5+ years of backend development",
                "minimum_years": 5,
                "preferred_years": 7,
            }
        ],
        "education_requirements": ["Bachelor's degree in Computer Science"],
        "required_certifications": [],
        "preferred_certifications": ["AWS Certified Developer"],
        "responsibilities": ["Design APIs", "Review code"],
        "domain_requirements": ["Fintech"],
        "communication_requirements": ["Clear written communication"],
        "leadership_requirements": ["Mentor junior engineers"],
        "work_authorization_requirements": ["Must be authorized to work in India"],
        "travel_requirements": ["Up to 10% travel"],
        "other_requirements": [],
    }

    analysis = JobAnalysis.model_validate(payload)

    assert analysis.seniority_level == "Senior"
    assert analysis.required_skills[0].name == "Python"
    assert analysis.minimum_years_experience == 5


def test_job_analysis_allows_nullable_and_empty_values() -> None:
    payload = {
        "role_summary": None,
        "seniority_level": None,
        "employment_type": None,
        "work_arrangement": None,
        "location": None,
        "required_skills": [],
        "preferred_skills": [],
        "minimum_years_experience": None,
        "preferred_years_experience": None,
        "experience_requirements": [],
        "education_requirements": [],
        "required_certifications": [],
        "preferred_certifications": [],
        "responsibilities": [],
        "domain_requirements": [],
        "communication_requirements": [],
        "leadership_requirements": [],
        "work_authorization_requirements": [],
        "travel_requirements": [],
        "other_requirements": [],
    }

    analysis = JobAnalysis.model_validate(payload)

    assert analysis.role_summary is None
    assert analysis.required_skills == []


def test_job_analysis_rejects_invalid_years() -> None:
    with pytest.raises(ValidationError):
        JobAnalysis.model_validate(
            {
                "required_skills": [],
                "preferred_skills": [],
                "minimum_years_experience": -1,
                "experience_requirements": [],
                "education_requirements": [],
                "required_certifications": [],
                "preferred_certifications": [],
                "responsibilities": [],
                "domain_requirements": [],
                "communication_requirements": [],
                "leadership_requirements": [],
                "work_authorization_requirements": [],
                "travel_requirements": [],
                "other_requirements": [],
            }
        )

    with pytest.raises(ValidationError):
        JobAnalysis.model_validate(
            {
                "required_skills": [],
                "preferred_skills": [],
                "minimum_years_experience": 6,
                "preferred_years_experience": 4,
                "experience_requirements": [],
                "education_requirements": [],
                "required_certifications": [],
                "preferred_certifications": [],
                "responsibilities": [],
                "domain_requirements": [],
                "communication_requirements": [],
                "leadership_requirements": [],
                "work_authorization_requirements": [],
                "travel_requirements": [],
                "other_requirements": [],
            }
        )


def test_job_analysis_rejects_malformed_skill_values() -> None:
    with pytest.raises(ValidationError):
        JobAnalysis.model_validate(
            {
                "required_skills": [{"name": "", "category": "language"}],
                "preferred_skills": [],
                "experience_requirements": [],
                "education_requirements": [],
                "required_certifications": [],
                "preferred_certifications": [],
                "responsibilities": [],
                "domain_requirements": [],
                "communication_requirements": [],
                "leadership_requirements": [],
                "work_authorization_requirements": [],
                "travel_requirements": [],
                "other_requirements": [],
            }
        )


def test_job_analysis_deduplicates_skills_and_text_lists() -> None:
    analysis = JobAnalysis.model_validate(
        {
            "required_skills": [
                {"name": " Python ", "category": "language"},
                {"name": "python", "category": "language"},
            ],
            "preferred_skills": [
                {"name": "AWS", "category": "cloud"},
                {"name": "AWS", "category": "cloud"},
            ],
            "experience_requirements": [],
            "education_requirements": ["  Bachelors  ", "bachelors"],
            "required_certifications": [],
            "preferred_certifications": [],
            "responsibilities": [],
            "domain_requirements": [],
            "communication_requirements": [],
            "leadership_requirements": [],
            "work_authorization_requirements": [],
            "travel_requirements": [],
            "other_requirements": [],
        }
    )

    assert len(analysis.required_skills) == 1
    assert analysis.required_skills[0].name == "Python"
    assert len(analysis.preferred_skills) == 1
    assert analysis.education_requirements == ["Bachelors"]
