from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.database.models import Application, ApplicationQuestion, UserProfile


@dataclass(frozen=True)
class BrowserField:
    name: str
    label: str
    field_type: str
    required: bool = False


@dataclass(frozen=True)
class FieldMappingResult:
    field: str
    label: str
    field_type: str
    required: bool
    value: str | None
    status: str
    message: str | None = None


def map_field_results(
    *,
    profile: UserProfile,
    application: Application,
    fields: list[BrowserField],
) -> list[FieldMappingResult]:
    results: list[FieldMappingResult] = []
    qa_map = _question_map(application.questions)

    for field in fields:
        value = _resolve_value(
            profile=profile,
            application=application,
            field=field,
            qa_map=qa_map,
        )
        if value is None:
            results.append(
                FieldMappingResult(
                    field=field.name,
                    label=field.label,
                    field_type=field.field_type,
                    required=field.required,
                    value=None,
                    status=("NEEDS_USER_INPUT" if field.required else "SKIPPED"),
                    message=(
                        "No verified user value available."
                        if field.required
                        else "No verified value available for optional field."
                    ),
                )
            )
            continue

        results.append(
            FieldMappingResult(
                field=field.name,
                label=field.label,
                field_type=field.field_type,
                required=field.required,
                value=value,
                status="READY",
                message=None,
            )
        )

    return results


def map_fields(
    *,
    profile: UserProfile,
    application: Application,
    fields: list[BrowserField],
) -> tuple[list[dict[str, str]], list[str]]:
    mapped: list[dict[str, str]] = []
    unknown: list[str] = []

    for field in map_field_results(
        profile=profile,
        application=application,
        fields=fields,
    ):
        if field.status != "READY" or field.value is None:
            if field.status == "NEEDS_USER_INPUT":
                unknown.append(field.label or field.field)
            continue

        mapped.append(
            {
                "field": field.field,
                "label": field.label,
                "type": field.field_type,
                "value": field.value,
            }
        )

    return mapped, _dedupe(unknown)


def _resolve_value(
    *,
    profile: UserProfile,
    application: Application,
    field: BrowserField,
    qa_map: dict[str, str],
) -> str | None:
    key = f"{field.name} {field.label}".strip().lower()

    if any(token in key for token in ["name", "full name"]):
        return profile.name
    if "email" in key:
        return profile.email
    if any(token in key for token in ["phone", "mobile"]):
        return profile.phone
    if any(token in key for token in ["location", "city"]):
        return profile.location
    if any(token in key for token in ["cover letter", "cover_letter"]):
        return application.cover_letter
    if any(token in key for token in ["resume", "cv", "upload"]):
        resume = application.resume
        if resume and resume.file_path and Path(resume.file_path).exists():
            return resume.file_path

    for question, answer in qa_map.items():
        if question and question in key:
            return answer

    return None


def _question_map(questions: list[ApplicationQuestion]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in questions:
        if not item.answer:
            continue
        result[item.question.strip().lower()] = item.answer
    return result


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out
