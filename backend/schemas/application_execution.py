from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.browser_assistant import BrowserFieldInput

ExecutionMode = Literal["AUTHORIZED_API", "BROWSER_ASSISTED", "OPEN_AND_APPLY"]
ExecutionStatus = Literal["READY", "SUBMITTED", "OPEN_AND_APPLY", "BLOCKED"]
FieldExecutionStatus = Literal[
    "FILLED",
    "SKIPPED",
    "FAILED",
    "NEEDS_USER_INPUT",
]


class ApplicationExecutionRequest(BaseModel):
    application_url: str | None = None
    dry_run: bool = False
    submit: bool = False
    detect_fields: bool = True
    fields: list[BrowserFieldInput] = Field(default_factory=list)


class FieldExecutionResult(BaseModel):
    field: str
    label: str
    type: str
    status: FieldExecutionStatus
    value: str | None = None
    message: str | None = None


class ApplicationExecutionResponse(BaseModel):
    application_id: int
    mode: ExecutionMode
    status: ExecutionStatus
    submitted: bool = False
    requires_human_submit: bool = True
    application_url: str | None = None
    field_results: list[FieldExecutionResult] = Field(default_factory=list)
    message: str
