from __future__ import annotations

import pytest

from backend.ai.ollama_client import OllamaChatResponse, OllamaClientError
from backend.ai.resume_analyzer import ResumeAnalysisError, analyze_resume_text


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


def test_analyze_resume_text_parses_valid_json() -> None:
    client = _FakeOllamaClient(
        content=(
            '{"name":"Jane Doe","skills":[{"name":"Python",'
            '"category":"programming_language"}]}'
        )
    )

    profile = analyze_resume_text(
        "Jane Doe used Python for backend APIs.",
        client=client,
    )

    assert profile.name == "Jane Doe"
    assert len(profile.skills) == 1
    assert profile.skills[0].name == "Python"


def test_analyze_resume_text_handles_malformed_json() -> None:
    client = _FakeOllamaClient(content="{invalid json")

    with pytest.raises(ResumeAnalysisError, match="malformed JSON"):
        analyze_resume_text("Text", client=client)


def test_analyze_resume_text_handles_invalid_schema() -> None:
    client = _FakeOllamaClient(content='{"skills":"not-a-list"}')

    with pytest.raises(ResumeAnalysisError, match="invalid profile structure"):
        analyze_resume_text("Text", client=client)


def test_analyze_resume_text_handles_ollama_connection_failure() -> None:
    client = _FakeOllamaClient(
        error_to_raise=OllamaClientError(
            "Ollama is not available. Start Ollama and try again.",
            status_code=503,
        )
    )

    with pytest.raises(ResumeAnalysisError, match="Ollama is not available") as exc:
        analyze_resume_text("Text", client=client)

    assert exc.value.status_code == 503


def test_analyze_resume_text_handles_ollama_http_failure() -> None:
    client = _FakeOllamaClient(
        error_to_raise=OllamaClientError("Ollama request failed with status 500")
    )

    with pytest.raises(ResumeAnalysisError, match="status 500"):
        analyze_resume_text("Text", client=client)


def test_analyze_resume_text_rejects_empty_resume_text() -> None:
    client = _FakeOllamaClient(content="{}")

    with pytest.raises(ResumeAnalysisError, match="empty"):
        analyze_resume_text("   ", client=client)


def test_analyze_resume_text_preserves_only_provided_fields() -> None:
    synthetic_text = (
        "Jane Doe\n"
        "Software Engineer\n"
        "Worked at Example Corp.\n"
        "Used Python and FastAPI to build backend APIs."
    )
    client = _FakeOllamaClient(
        content=(
            "{"
            '"name":"Jane Doe",'
            '"headline":"Software Engineer",'
            '"skills":[{"name":"Python","category":"programming_language"},'
            '{"name":"FastAPI","category":"framework"}],'
            '"experience":[{"company":"Example Corp","title":"Software Engineer"}],'
            '"education":[],"projects":[],"certifications":[],"achievements":[],"languages":[]'
            "}"
        )
    )

    profile = analyze_resume_text(synthetic_text, client=client)

    assert profile.name == "Jane Doe"
    assert profile.location is None
    assert profile.skills[0].name == "Python"
    assert profile.education == []
