from __future__ import annotations

import json
import re
from datetime import datetime
from html import unescape
from urllib import error, parse, request

from backend.services.job_discovery.base import (
    JobDiscoveryConnector,
    JobDiscoveryConnectorError,
)
from backend.services.job_discovery.models import DiscoveredJob, DiscoverySearchCriteria

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveConnector(JobDiscoveryConnector):
    source_name = "remotive"
    source_type = "public_api"
    supports_apply = False

    def __init__(self, limit_per_source: int = 10):
        self.limit_per_source = limit_per_source

    def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
        queries = criteria.queries[:3] or criteria.skills[:3]
        if not queries:
            raise JobDiscoveryConnectorError(
                "Resume analysis did not contain usable search criteria."
            )

        discovered: list[DiscoveredJob] = []
        seen: set[tuple[str, str | None]] = set()

        for query in queries:
            payload = _fetch_remotive_jobs(query, self.limit_per_source)
            for item in payload:
                normalized = _normalize_job(item)
                if normalized is None:
                    continue

                key = (normalized.external_id or "", normalized.job_url)
                if key in seen:
                    continue
                seen.add(key)
                discovered.append(normalized)

                if len(discovered) >= self.limit_per_source:
                    return discovered

        return discovered


def _fetch_remotive_jobs(query: str, limit: int) -> list[dict[str, object]]:
    params = parse.urlencode({"search": query, "limit": str(limit)})
    url = f"{REMOTIVE_API_URL}?{params}"
    req = request.Request(
        url=url,
        method="GET",
        headers={"Accept": "application/json"},
    )

    try:
        with request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise JobDiscoveryConnectorError(
            f"Remotive request failed with status {exc.code}"
        ) from exc
    except error.URLError as exc:
        raise JobDiscoveryConnectorError(
            "Remotive is not reachable right now. Try again later."
        ) from exc
    except json.JSONDecodeError as exc:
        raise JobDiscoveryConnectorError("Remotive returned invalid JSON") from exc

    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise JobDiscoveryConnectorError("Remotive response did not include jobs")
    return [item for item in jobs if isinstance(item, dict)]


def _normalize_job(payload: dict[str, object]) -> DiscoveredJob | None:
    title = _clean_text(payload.get("title"))
    company = _clean_text(payload.get("company_name"))
    description = _html_to_text(payload.get("description"))
    job_url = _clean_text(payload.get("url"))

    if not title or not company or not description:
        return None

    return DiscoveredJob(
        title=title,
        company=company,
        location=_clean_text(payload.get("candidate_required_location")),
        description=description,
        job_url=job_url,
        source_name="remotive",
        source_type="public_api",
        external_id=str(payload.get("id")) if payload.get("id") is not None else None,
        discovered_at=_parse_datetime(payload.get("publication_date")),
        source_base_url="https://remotive.com",
        supports_apply=False,
    )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _html_to_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
