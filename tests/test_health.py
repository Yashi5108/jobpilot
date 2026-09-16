import asyncio
import json
from collections.abc import Awaitable
from typing import Any

from backend.main import app


def _run(coro: Awaitable[Any]) -> Any:
    """Run async code in tests without requiring pytest-asyncio."""
    return asyncio.run(coro)


async def _asgi_get(path: str) -> tuple[int, dict[str, Any]]:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, str | bool]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)

    start = next(msg for msg in messages if msg["type"] == "http.response.start")
    body_chunks = [
        msg.get("body", b"") for msg in messages if msg["type"] == "http.response.body"
    ]
    body = b"".join(body_chunks)
    payload = json.loads(body.decode("utf-8")) if body else {}

    return int(start["status"]), payload


def test_health_endpoint_returns_ok() -> None:
    status_code, payload = _run(_asgi_get("/health"))

    assert status_code == 200
    assert payload.get("status") == "ok"
