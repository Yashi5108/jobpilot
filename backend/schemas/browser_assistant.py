from __future__ import annotations

from pydantic import BaseModel, Field


class BrowserFieldInput(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = False


class BrowserAssistRequest(BaseModel):
    application_url: str
    dry_run: bool = True
    fields: list[BrowserFieldInput] = Field(default_factory=list)


class BrowserAssistResponse(BaseModel):
    application_id: int
    dry_run: bool
    mapped_fields: list[dict[str, str]] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    message: str
    requires_human_submit: bool = True
