from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.resume_analysis import CandidateProfile


def test_candidate_profile_valid_payload() -> None:
    payload = {
        "name": "Jane Doe",
        "headline": "Software Engineer",
        "skills": [
            {"name": "Python", "category": "programming_language"},
            {"name": "FastAPI", "category": "framework"},
        ],
        "experience": [
            {
                "company": "Example Corp",
                "title": "Software Engineer",
                "start_date": "2022-01",
                "end_date": None,
                "is_current": True,
                "responsibilities": ["Built backend APIs"],
            }
        ],
        "education": [],
        "projects": [],
        "certifications": [],
        "achievements": [],
        "languages": [],
    }

    profile = CandidateProfile.model_validate(payload)

    assert profile.name == "Jane Doe"
    assert profile.experience[0].end_date is None
    assert profile.skills[0].category == "programming_language"


def test_candidate_profile_allows_missing_optionals() -> None:
    payload = {
        "skills": [],
        "experience": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "achievements": [],
        "languages": [],
    }

    profile = CandidateProfile.model_validate(payload)

    assert profile.name is None
    assert profile.skills == []


def test_candidate_profile_rejects_invalid_skill_category() -> None:
    payload = {
        "skills": [{"name": "Python", "category": "made_up_category"}],
        "experience": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "achievements": [],
        "languages": [],
    }

    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(payload)
