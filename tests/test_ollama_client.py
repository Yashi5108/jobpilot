from __future__ import annotations

import io
import json
from urllib import error

import pytest

from backend.ai.ollama_client import OllamaClient, OllamaClientError


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.status_code = status_code

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload

    def getcode(self) -> int:
        return self.status_code


def test_ollama_client_chat_json_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        return _FakeResponse({"message": {"content": '{"name":"Jane"}'}})

    monkeypatch.setattr("backend.ai.ollama_client.request.urlopen", _fake_urlopen)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.1")
    response = client.chat_json([{"role": "user", "content": "text"}])

    assert response.content == '{"name":"Jane"}'


def test_ollama_client_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        raise error.HTTPError(
            url="http://localhost:11434/api/chat",
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=io.BytesIO(b"{}"),
        )

    monkeypatch.setattr("backend.ai.ollama_client.request.urlopen", _fake_urlopen)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.1")
    with pytest.raises(OllamaClientError, match="status 500") as exc:
        client.chat_json([{"role": "user", "content": "text"}])

    assert exc.value.status_code == 502


def test_ollama_client_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        raise error.URLError("connection refused")

    monkeypatch.setattr("backend.ai.ollama_client.request.urlopen", _fake_urlopen)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.1")
    with pytest.raises(OllamaClientError, match="not available") as exc:
        client.chat_json([{"role": "user", "content": "text"}])

    assert exc.value.status_code == 503


def test_ollama_client_invalid_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class _InvalidResponse:
        def __enter__(self) -> "_InvalidResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    def _fake_urlopen(*_: object, **__: object) -> _InvalidResponse:
        return _InvalidResponse()

    monkeypatch.setattr("backend.ai.ollama_client.request.urlopen", _fake_urlopen)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.1")
    with pytest.raises(OllamaClientError, match="invalid JSON"):
        client.chat_json([{"role": "user", "content": "text"}])


def test_ollama_client_missing_content(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        return _FakeResponse({"message": {"content": ""}})

    monkeypatch.setattr("backend.ai.ollama_client.request.urlopen", _fake_urlopen)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.1")
    with pytest.raises(OllamaClientError, match="valid content"):
        client.chat_json([{"role": "user", "content": "text"}])
