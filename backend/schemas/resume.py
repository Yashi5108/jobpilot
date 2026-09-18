from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeCreate(BaseModel):
    profile_id: int
    name: str
    file_path: str
    file_type: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    parse_status: str | None = None
    is_default: bool = False


class ResumeRead(BaseModel):
    id: int
    profile_id: int
    name: str
    file_path: str
    file_type: str | None
    mime_type: str | None
    file_size_bytes: int | None
    page_count: int | None
    parse_status: str | None
    analysis_status: str
    analyzed_at: datetime | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResumeUploadResponse(BaseModel):
    id: int
    profile_id: int
    name: str
    file_type: str | None
    mime_type: str | None
    file_size_bytes: int | None
    page_count: int | None
    parse_status: str | None
    text_preview: str
    text_length: int
    created_at: datetime


class ResumeTextRead(BaseModel):
    id: int
    name: str
    file_type: str | None
    page_count: int | None
    normalized_text: str
