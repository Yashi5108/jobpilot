from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from pydantic import ValidationError

from backend.connectors.base import JobConnector, NormalizedJob
from backend.connectors.manual import ManualJobInput


class StructuredImportConnector(JobConnector):
    def __init__(self, jobs: list[dict[str, object]]) -> None:
        self.jobs = jobs

    def discover(self) -> list[NormalizedJob]:
        normalized: list[NormalizedJob] = []
        for item in self.jobs:
            payload = _coerce_aliases(item)
            try:
                parsed = ManualJobInput.model_validate(payload)
            except ValidationError as exc:
                message = exc.errors()[0]["msg"]
                raise ValueError(f"Invalid job record: {message}") from exc

            normalized.append(
                NormalizedJob(
                    title=parsed.title,
                    company=parsed.company,
                    description=parsed.description,
                    location=parsed.location,
                    employment_type=parsed.employment_type,
                    work_arrangement=parsed.work_arrangement,
                    url=str(parsed.url) if parsed.url else None,
                    source_name=parsed.source_name,
                    source_type=parsed.source_type,
                    source_base_url=(
                        str(parsed.source_base_url) if parsed.source_base_url else None
                    ),
                    external_id=parsed.external_id,
                    posted_at=parsed.posted_at,
                )
            )
        return normalized


def load_json_jobs(content: bytes) -> list[dict[str, object]]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON file") from exc

    if isinstance(payload, dict):
        jobs = payload.get("jobs")
    else:
        jobs = payload

    if not isinstance(jobs, list):
        raise ValueError("JSON import must contain a list of jobs")

    result: list[dict[str, object]] = []
    for item in jobs:
        if isinstance(item, dict):
            result.append(item)
        else:
            raise ValueError("Each JSON job item must be an object")
    return result


def load_csv_jobs(content: bytes) -> list[dict[str, object]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV import is missing a header row")

    rows: list[dict[str, object]] = []
    for row in reader:
        rows.append({key: value for key, value in row.items() if key is not None})

    if not rows:
        raise ValueError("CSV import file is empty")

    return rows


def _coerce_aliases(item: dict[str, object]) -> dict[str, object]:
    payload = dict(item)

    if "work_arrangement" not in payload and "remote_type" in payload:
        payload["work_arrangement"] = payload.get("remote_type")

    if "posted_at" in payload and isinstance(payload["posted_at"], str):
        value = payload["posted_at"].strip()
        if value:
            try:
                payload["posted_at"] = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("posted_at must be an ISO-8601 datetime") from exc
        else:
            payload["posted_at"] = None

    if "source" in payload and "source_name" not in payload:
        payload["source_name"] = payload.get("source")

    return payload
