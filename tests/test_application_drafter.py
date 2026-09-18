from __future__ import annotations

from dataclasses import dataclass

from backend.ai.application_drafter import (
    generate_cover_letter,
    generate_screening_answer,
)
from backend.ai.ollama_client import OllamaChatResponse
from backend.database.models import UserProfile
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.job_match import JobMatchResult
from backend.schemas.resume_analysis import CandidateProfile


@dataclass
class _FakeClient:
    content: str

    def chat_json(self, messages: list[dict[str, str]]) -> OllamaChatResponse:
        assert messages
        return OllamaChatResponse(content=self.content)


def _fixtures() -> tuple[UserProfile, CandidateProfile, JobAnalysis, JobMatchResult]:
    profile = UserProfile(name="User", work_authorization="Authorized")
    resume = CandidateProfile.model_validate(
        {
            "headline": "Backend Engineer",
            "skills": [{"name": "Python"}],
            "experience": [{"start_date": "2018-01", "is_current": True}],
            "education": [],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
        }
    )
    job = JobAnalysis.model_validate(
        {
            "role_summary": "Backend API role",
            "required_skills": [{"name": "Python", "category": "language"}],
            "preferred_skills": [],
            "minimum_years_experience": 1,
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
    )
    match = JobMatchResult.model_validate(
        {
            "job_id": 1,
            "resume_id": 1,
            "profile_id": 1,
            "score": 75,
            "required_skill_score": 100,
            "preferred_skill_score": None,
            "experience_score": 100,
            "education_score": None,
            "certification_score": None,
            "domain_score": None,
            "matched_required_skills": ["Python"],
            "missing_required_skills": [],
            "matched_preferred_skills": [],
            "missing_preferred_skills": [],
            "matched_required_certifications": [],
            "missing_required_certifications": [],
            "matched_preferred_certifications": [],
            "missing_preferred_certifications": [],
            "experience_result": "MATCHED",
            "education_result": "NOT_REQUIRED",
            "certification_result": "NOT_REQUIRED",
            "domain_result": "NOT_REQUIRED",
            "strengths": ["Required skill matched: Python"],
            "gaps": [],
            "matched_at": "2026-09-18T00:00:00Z",
        }
    )
    return profile, resume, job, match


def test_generate_cover_letter_uses_ai_json_output() -> None:
    profile, resume, job, match = _fixtures()
    draft = generate_cover_letter(
        profile=profile,
        resume_analysis=resume,
        job_analysis=job,
        job_title="Backend Engineer",
        company="Acme",
        job_description="Need Python",
        match_result=match,
        client=_FakeClient('{"cover_letter":"Hello"}'),
    )

    assert draft == "Hello"


def test_screening_answer_needs_user_input_for_unknown() -> None:
    profile, resume, job, match = _fixtures()
    answer, status = generate_screening_answer(
        question="What is your expected CTC?",
        profile=profile,
        resume_analysis=resume,
        job_analysis=job,
        match_result=match,
        client=_FakeClient('{"answer":""}'),
    )

    assert answer is None
    assert status.value == "NEEDS_USER_INPUT"
