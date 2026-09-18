from __future__ import annotations

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ValidationError, field_validator

from backend.connectors.base import JobConnector, NormalizedJob


class ManualJobInput(BaseModel):
    title: str
    company: str
    description: str
    location: str | None = None
    employment_type: str | None = None
    work_arrangement: str | None = None
    url: AnyHttpUrl | None = None
    source_name: str = "manual"
    source_type: str = "manual"
    source_base_url: AnyHttpUrl | None = None
    external_id: str | None = None
    posted_at: datetime | None = None

    @field_validator("title", "company", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty")
        return cleaned

    @field_validator(
        "location",
        "employment_type",
        "work_arrangement",
        "source_name",
        "source_type",
        "external_id",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("source_type")
    @classmethod
    def default_source_type(cls, value: str | None) -> str:
        return (value or "manual").lower()

    @field_validator("source_name")
    @classmethod
    def default_source_name(cls, value: str | None) -> str:
        return value or "manual"


class ManualConnector(JobConnector):
    def __init__(self, payload: dict[str, object]) -> None:
        try:
            self.input = ManualJobInput.model_validate(payload)
        except ValidationError as exc:
            raise ValueError("Invalid manual job payload") from exc

    def discover(self) -> list[NormalizedJob]:
        return [
            NormalizedJob(
                title=self.input.title,
                company=self.input.company,
                description=self.input.description,
                location=self.input.location,
                employment_type=self.input.employment_type,
                work_arrangement=self.input.work_arrangement,
                url=str(self.input.url) if self.input.url else None,
                source_name=self.input.source_name,
                source_type=self.input.source_type,
                source_base_url=(
                    str(self.input.source_base_url)
                    if self.input.source_base_url
                    else None
                ),
                external_id=self.input.external_id,
                posted_at=self.input.posted_at,
            )
        ]
