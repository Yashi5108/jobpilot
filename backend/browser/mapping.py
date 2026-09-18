from __future__ import annotations

from dataclasses import dataclass

from backend.database.models import Application, ApplicationQuestion, UserProfile


@dataclass(frozen=True)
class BrowserField:
    name: str
    label: str
    field_type: str
    required: bool = False


def map_fields(
    *,
    profile: UserProfile,
    application: Application,
    fields: list[BrowserField],
) -> tuple[list[dict[str, str]], list[str]]:
    mapped: list[dict[str, str]] = []
    unknown: list[str] = []

    qa_map = _question_map(application.questions)

    for field in fields:
        value = _resolve_value(
            profile=profile,
            application=application,
            field=field,
            qa_map=qa_map,
        )
        if value is None:
            if field.required:
                unknown.append(field.label or field.name)
            continue

        mapped.append(
            {
                "field": field.name,
                "label": field.label,
                "type": field.field_type,
                "value": value,
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
