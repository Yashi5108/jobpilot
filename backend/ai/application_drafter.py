from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from backend.ai.ollama_client import OllamaClient, OllamaClientError
from backend.ai.prompts import (
    build_cover_letter_messages,
    build_screening_answer_messages,
)
from backend.database.models import QuestionStatus, UserProfile
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.job_match import JobMatchResult
from backend.schemas.resume_analysis import CandidateProfile


class ApplicationDraftError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


class _CoverLetterPayload(BaseModel):
    cover_letter: str


class _ScreeningAnswerPayload(BaseModel):
    answer: str


def generate_cover_letter(
    *,
    profile: UserProfile,
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
    job_title: str,
    company: str,
    job_description: str,
    match_result: JobMatchResult,
    client: OllamaClient | None = None,
) -> str:
    ollama_client = client or OllamaClient()
    messages = build_cover_letter_messages(
        profile=profile,
        resume_analysis=resume_analysis,
        job_analysis=job_analysis,
        job_title=job_title,
        company=company,
        job_description=job_description,
        match_result=match_result,
    )

    try:
        response = ollama_client.chat_json(messages)
        payload = _CoverLetterPayload.model_validate(
            json.loads(_strip(response.content))
        )
        text = payload.cover_letter.strip()
        if text:
            return text
    except (OllamaClientError, json.JSONDecodeError, ValidationError):
        pass

    # Conservative fallback uses only known facts and avoids fabricated claims.
    skill_names = [skill.name for skill in resume_analysis.skills[:4]]
    top_skills = (
        ", ".join(skill_names) if skill_names else "relevant engineering skills"
    )
    return (
        f"Dear Hiring Team at {company},\n\n"
        f"I am applying for the {job_title} role. My background includes "
        f"{top_skills}, and I am interested in this opportunity because it aligns "
        "with my experience and the responsibilities described in the role.\n\n"
        "Thank you for your time and consideration.\n"
    )


def generate_screening_answer(
    *,
    question: str,
    profile: UserProfile,
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
    match_result: JobMatchResult,
    client: OllamaClient | None = None,
) -> tuple[str | None, QuestionStatus]:
    normalized = question.strip().lower()
    if not normalized:
        return None, QuestionStatus.NEEDS_USER_INPUT

    if "years" in normalized and "python" in normalized:
        years = _estimate_years_of_experience(resume_analysis)
        if years is None:
            return None, QuestionStatus.NEEDS_USER_INPUT
        return (
            f"I have approximately {years} years of Python experience.",
            QuestionStatus.DRAFT,
        )

    if "authorized" in normalized and "work" in normalized:
        if profile.work_authorization:
            return profile.work_authorization.strip(), QuestionStatus.DRAFT
        return None, QuestionStatus.NEEDS_USER_INPUT

    if "relocate" in normalized:
        preference = (profile.remote_preference or "").strip().lower()
        if not preference:
            return None, QuestionStatus.NEEDS_USER_INPUT
        if "remote" in preference:
            return (
                "I prefer remote opportunities and can discuss relocation "
                "if required.",
                QuestionStatus.DRAFT,
            )
        return "I am open to discussing relocation requirements.", QuestionStatus.DRAFT

    if "why" in normalized and "role" in normalized:
        return _draft_interest_answer(
            question=question,
            profile=profile,
            resume_analysis=resume_analysis,
            job_analysis=job_analysis,
            match_result=match_result,
            client=client,
        )

    return None, QuestionStatus.NEEDS_USER_INPUT


def _draft_interest_answer(
    *,
    question: str,
    profile: UserProfile,
    resume_analysis: CandidateProfile,
    job_analysis: JobAnalysis,
    match_result: JobMatchResult,
    client: OllamaClient | None,
) -> tuple[str | None, QuestionStatus]:
    ollama_client = client or OllamaClient()
    messages = build_screening_answer_messages(
        question=question,
        profile=profile,
        resume_analysis=resume_analysis,
        job_analysis=job_analysis,
        match_result=match_result,
    )

    try:
        response = ollama_client.chat_json(messages)
        payload = _ScreeningAnswerPayload.model_validate(
            json.loads(_strip(response.content))
        )
        answer = payload.answer.strip()
    except (OllamaClientError, json.JSONDecodeError, ValidationError):
        answer = ""

    if answer:
        return answer, QuestionStatus.DRAFT

    role_summary = job_analysis.role_summary or "this role"
    headline = resume_analysis.headline or "my experience"
    return (
        "I am interested in this opportunity because "
        f"{role_summary.lower()} aligns with {headline.lower()}.",
        QuestionStatus.DRAFT,
    )


def _estimate_years_of_experience(profile: CandidateProfile) -> int | None:
    starts: list[datetime] = []
    ends: list[datetime] = []

    for item in profile.experience:
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

    return max(0, int((latest - earliest).days / 365.25))


def _parse_partial_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) == 4 and text.isdigit():
        return datetime(int(text), 1, 1, tzinfo=UTC)
    if len(text) == 7 and text[4] == "-":
        year, month = text.split("-")
        if year.isdigit() and month.isdigit():
            m = int(month)
            if 1 <= m <= 12:
                return datetime(int(year), m, 1, tzinfo=UTC)
    return None


def _strip(content: str) -> str:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text
