from __future__ import annotations

import io
import json
from urllib import error

import pytest

from frontend.api_client import ApiClient, ApiClientError


class _FakeResponse:
    def __init__(self, status_code: int, data: dict | list | None = None) -> None:
        self._status_code = status_code
        self._payload = json.dumps(data or {}).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload

    def getcode(self) -> int:
        return self._status_code


def test_api_client_uses_default_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOBPILOT_API_BASE_URL", raising=False)
    client = ApiClient()
    assert client.base_url == "http://127.0.0.1:8000"


def test_api_client_uses_env_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBPILOT_API_BASE_URL", "http://localhost:9000/")
    client = ApiClient()
    assert client.base_url == "http://localhost:9000"


def test_api_client_get_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        return _FakeResponse(200, {"status": "ok"})

    monkeypatch.setattr("frontend.api_client.request.urlopen", _fake_urlopen)

    client = ApiClient(base_url="http://test")
    response = client.get("/health")

    assert response.status_code == 200
    assert response.data["status"] == "ok"


def test_api_client_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        raise error.HTTPError(
            url="http://test/api/v1/profile",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(json.dumps({"detail": "Profile not found"}).encode("utf-8")),
        )

    monkeypatch.setattr("frontend.api_client.request.urlopen", _fake_urlopen)

    client = ApiClient(base_url="http://test")

    with pytest.raises(ApiClientError) as exc_info:
        client.get("/api/v1/profile")

    assert exc_info.value.status_code == 404
    assert "Profile not found" in str(exc_info.value)


def test_api_client_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_urlopen(*_: object, **__: object) -> _FakeResponse:
        raise error.URLError("connection refused")

    monkeypatch.setattr("frontend.api_client.request.urlopen", _fake_urlopen)

    client = ApiClient(base_url="http://test")

    with pytest.raises(ApiClientError) as exc_info:
        client.get("/health")

    assert "Cannot reach JobPilot backend" in str(exc_info.value)


def test_api_client_post_multipart_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_urlopen(req: object, **__: object) -> _FakeResponse:
        captured["request"] = req
        return _FakeResponse(201, {"status": "uploaded"})

    monkeypatch.setattr("frontend.api_client.request.urlopen", _fake_urlopen)

    client = ApiClient(base_url="http://test")
    response = client.post_multipart(
        path="/api/v1/resumes/upload",
        form_fields={"profile_id": "1"},
        file_field_name="file",
        filename="resume.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    assert response.status_code == 201
    assert response.data["status"] == "uploaded"
    raw_request = captured["request"]
    request_headers = raw_request.header_items()  # type: ignore[union-attr]
    assert any(
        header.lower() == "content-type" and "multipart/form-data" in value.lower()
        for header, value in request_headers
    )
