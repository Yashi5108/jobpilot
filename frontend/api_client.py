from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from uuid import uuid4

DEFAULT_TIMEOUT_SECONDS = 10


class ApiClientError(Exception):
    """Raised when the backend API call fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    data: Any


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        configured_url = base_url or os.getenv(
            "JOBPILOT_API_BASE_URL", "http://127.0.0.1:8000"
        )
        self.base_url = configured_url.rstrip("/")
        self.timeout = timeout

    def get(self, path: str) -> ApiResponse:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> ApiResponse:
        return self._request("POST", path, payload)

    def post_empty(self, path: str) -> ApiResponse:
        return self._request("POST", path)

    def put(self, path: str, payload: dict[str, Any]) -> ApiResponse:
        return self._request("PUT", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> ApiResponse:
        return self._request("PATCH", path, payload)

    def delete(self, path: str) -> ApiResponse:
        return self._request("DELETE", path)

    def post_multipart(
        self,
        path: str,
        form_fields: dict[str, str],
        file_field_name: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> ApiResponse:
        boundary = f"jobpilot-{uuid4().hex}"
        body = self._build_multipart_body(
            boundary=boundary,
            form_fields=form_fields,
            file_field_name=file_field_name,
            filename=filename,
            content=content,
            content_type=content_type,
        )

        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        return self._request(path=path, method="POST", body=body, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> ApiResponse:
        url = f"{self.base_url}{path}"

        request_body: bytes | None = body
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)

        if payload is not None:
            request_body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        req = request.Request(
            url=url,
            method=method,
            data=request_body,
            headers=request_headers,
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw_body = response.read().decode("utf-8")
                data = json.loads(raw_body) if raw_body else {}
                return ApiResponse(status_code=response.getcode(), data=data)
        except error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8") if exc.fp else ""
            details = self._safe_parse(raw_body)
            message = (
                details.get("detail") if isinstance(details, dict) else str(details)
            )
            error_detail = message or "Request failed"
            raise ApiClientError(
                f"{method} {path} failed with {exc.code}: {error_detail}",
                status_code=exc.code,
            ) from exc
        except error.URLError as exc:
            raise ApiClientError(
                "Cannot reach JobPilot backend. Start FastAPI at http://127.0.0.1:8000"
            ) from exc

    @staticmethod
    def _safe_parse(raw_body: str) -> Any:
        if not raw_body:
            return {}
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            return raw_body

    @staticmethod
    def _build_multipart_body(
        boundary: str,
        form_fields: dict[str, str],
        file_field_name: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> bytes:
        lines: list[bytes] = []
        boundary_line = f"--{boundary}".encode("utf-8")

        for field_name, field_value in form_fields.items():
            lines.extend(
                [
                    boundary_line,
                    (f'Content-Disposition: form-data; name="{field_name}"').encode(
                        "utf-8"
                    ),
                    b"",
                    str(field_value).encode("utf-8"),
                ]
            )

        lines.extend(
            [
                boundary_line,
                (
                    f'Content-Disposition: form-data; name="{file_field_name}"; '
                    f'filename="{filename}"'
                ).encode("utf-8"),
                f"Content-Type: {content_type}".encode("utf-8"),
                b"",
                content,
                f"--{boundary}--".encode("utf-8"),
                b"",
            ]
        )

        return b"\r\n".join(lines)
