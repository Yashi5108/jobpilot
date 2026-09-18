from __future__ import annotations

import pytest

from backend.ai.job_analyzer import JobAnalysisError, analyze_job_description
from backend.ai.ollama_client import OllamaChatResponse, OllamaClientError


class _FakeOllamaClient:
    def __init__(
        self,
        content: str | None = None,
        error_to_raise: Exception | None = None,
    ):
        self.content = content
        self.error_to_raise = error_to_raise

    def chat_json(self, messages: list[dict[str, str]]) -> OllamaChatResponse:
        if self.error_to_raise is not None:
            raise self.error_to_raise
        assert messages
        return OllamaChatResponse(content=self.content or "{}")


def test_analyze_job_description_valid_json() -> None:
    client = _FakeOllamaClient(
        content=(
            "{"
            '"role_summary":"Build backend APIs",'
            '"required_skills":[{"name":"Python","category":"language"}],'
            '"preferred_skills":[{"name":"AWS","category":"cloud"}],'
            '"minimum_years_experience":5,'
            '"preferred_years_experience":null,'
            '"experience_requirements":['
            '{"requirement":"5+ years backend","minimum_years":5}'
            "],"
            '"education_requirements":[],'
            '"required_certifications":[],'
            '"preferred_certifications":[],'
            '"responsibilities":["Design APIs"],'
            '"domain_requirements":[],'
            '"communication_requirements":[],'
            '"leadership_requirements":[],'
            '"work_authorization_requirements":[],'
            '"travel_requirements":[],'
            '"other_requirements":[]'
            "}"
        )
    )

    analysis = analyze_job_description("JD text", client=client)

    assert analysis.role_summary == "Build backend APIs"
    assert analysis.required_skills[0].name == "Python"


def test_analyze_job_description_handles_missing_optional_fields() -> None:
    client = _FakeOllamaClient(
        content=(
            "{"
            '"required_skills":[],'
            '"preferred_skills":[],'
            '"experience_requirements":[],'
            '"education_requirements":[],'
            '"required_certifications":[],'
            '"preferred_certifications":[],'
            '"responsibilities":[],'
            '"domain_requirements":[],'
            '"communication_requirements":[],'
            '"leadership_requirements":[],'
            '"work_authorization_requirements":[],'
            '"travel_requirements":[],'
            '"other_requirements":[]'
            "}"
        )
    )

    analysis = analyze_job_description("JD text", client=client)

    assert analysis.role_summary is None
    assert analysis.required_skills == []


def test_analyze_job_description_handles_invalid_json() -> None:
    client = _FakeOllamaClient(content="{invalid json")

    with pytest.raises(JobAnalysisError, match="malformed JSON"):
        analyze_job_description("JD text", client=client)


def test_analyze_job_description_handles_validation_failure() -> None:
    client = _FakeOllamaClient(content='{"required_skills":"not-a-list"}')

    with pytest.raises(JobAnalysisError, match="invalid job analysis structure"):
        analyze_job_description("JD text", client=client)


def test_analyze_job_description_handles_ollama_connection_failure() -> None:
    client = _FakeOllamaClient(
        error_to_raise=OllamaClientError(
            "Ollama is not available. Start Ollama and try again.",
            status_code=503,
        )
    )

    with pytest.raises(JobAnalysisError, match="not available") as exc:
        analyze_job_description("JD text", client=client)

    assert exc.value.status_code == 503


def test_analyze_job_description_handles_ollama_timeout() -> None:
    client = _FakeOllamaClient(
        error_to_raise=OllamaClientError(
            "Ollama request timed out. Try again.",
            status_code=504,
        )
    )

    with pytest.raises(JobAnalysisError, match="timed out") as exc:
        analyze_job_description("JD text", client=client)

    assert exc.value.status_code == 504


def test_analyze_job_description_ignores_unknown_fields() -> None:
    client = _FakeOllamaClient(
        content=(
            "{"
            '"required_skills":[{"name":"Python","category":"language"}],'
            '"preferred_skills":[],'
            '"experience_requirements":[],'
            '"education_requirements":[],'
            '"required_certifications":[],'
            '"preferred_certifications":[],'
            '"responsibilities":[],'
            '"domain_requirements":[],'
            '"communication_requirements":[],'
            '"leadership_requirements":[],'
            '"work_authorization_requirements":[],'
            '"travel_requirements":[],'
            '"other_requirements":[],'
            '"unexpected_field":"should be ignored"'
            "}"
        )
    )

    analysis = analyze_job_description("JD text", client=client)

    assert analysis.required_skills[0].name == "Python"
    assert not hasattr(analysis, "unexpected_field")
