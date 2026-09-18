from __future__ import annotations

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class ManualJobImportRequest(BaseModel):
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


class JobImportRecord(BaseModel):
    index: int = Field(ge=0)
    title: str | None = None
    company: str | None = None
    status: str
    job_id: int | None = None
    error: str | None = None


class JobImportResult(BaseModel):
    imported_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    records: list[JobImportRecord] = Field(default_factory=list)
