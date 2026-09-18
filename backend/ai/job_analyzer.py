from __future__ import annotations

import json

from pydantic import ValidationError

from backend.ai.ollama_client import OllamaClient, OllamaClientError
from backend.ai.prompts import build_job_analysis_messages
from backend.schemas.job_analysis import JobAnalysis


class JobAnalysisError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def analyze_job_description(
    job_description: str,
    client: OllamaClient | None = None,
) -> JobAnalysis:
    if not job_description or not job_description.strip():
        raise JobAnalysisError("Job description is empty and cannot be analyzed.")

    ollama_client = client or OllamaClient()
    messages = build_job_analysis_messages(job_description=job_description)

    try:
        response = ollama_client.chat_json(messages)
    except OllamaClientError as exc:
        raise JobAnalysisError(str(exc), status_code=exc.status_code) from exc

    content = _strip_code_fences(response.content)

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise JobAnalysisError(
            "AI returned malformed JSON. Please try again.",
            status_code=502,
        ) from exc

    try:
        return JobAnalysis.model_validate(payload)
    except ValidationError as exc:
        raise JobAnalysisError(
            "AI returned invalid job analysis structure. Please try again.",
            status_code=502,
        ) from exc


def _strip_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text
