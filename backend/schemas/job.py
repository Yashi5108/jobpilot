from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, field_validator


class JobCreate(BaseModel):
    source_id: int | None = None
    source_name: str | None = None
    source_type: str | None = None
    source_base_url: str | None = None
    external_id: str | None = None
    title: str
    company: str
    location: str | None = None
    url: AnyHttpUrl | None = None
    description: str
    salary_min: float | None = None
    salary_max: float | None = None
    employment_type: str | None = None
    remote_type: str | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    discovered_at: datetime | None = None

    @field_validator("title", "company", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty")
        return cleaned

    @field_validator("location", "employment_type", "source_name", "source_type")
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


class JobUpdate(BaseModel):
    title: str
    company: str
    location: str | None = None
    url: AnyHttpUrl | None = None
    description: str
    employment_type: str | None = None

    @field_validator("title", "company", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty")
        return cleaned

    @field_validator("location", "employment_type")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class JobSourceRead(BaseModel):
    id: int
    name: str
    source_type: str
    base_url: str | None

    model_config = ConfigDict(from_attributes=True)


class JobRead(BaseModel):
    id: int
    source_id: int
    external_id: str | None
    title: str
    company: str | None
    location: str | None
    url: str | None
    description: str | None
    salary_min: float | None
    salary_max: float | None
    employment_type: str | None
    remote_type: str | None
    experience_min: float | None
    experience_max: float | None
    discovered_at: datetime | None
    analysis_status: str
    analyzed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    source: JobSourceRead

    model_config = ConfigDict(from_attributes=True)
