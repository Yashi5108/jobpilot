from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from backend.core.config import get_settings


class OllamaClientError(ValueError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class OllamaChatResponse:
    content: str


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout_seconds = timeout_seconds or settings.ollama_timeout_seconds

    def chat_json(self, messages: list[dict[str, str]]) -> OllamaChatResponse:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }

        req = request.Request(
            url=url,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=json.dumps(payload).encode("utf-8"),
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raise OllamaClientError(
                f"Ollama request failed with status {exc.code}",
                status_code=502,
            ) from exc
        except error.URLError as exc:
            raise OllamaClientError(
                "Ollama is not available. Start Ollama and try again.",
                status_code=503,
            ) from exc
        except TimeoutError as exc:
            raise OllamaClientError(
                "Ollama request timed out. Try again.",
                status_code=504,
            ) from exc

        try:
            data = json.loads(raw_body)
            message = data.get("message", {})
            content = message.get("content", "")
        except json.JSONDecodeError as exc:
            raise OllamaClientError("Ollama returned invalid JSON.") from exc

        if not isinstance(content, str) or not content.strip():
            raise OllamaClientError("Ollama response did not include valid content.")

        return OllamaChatResponse(content=content)
