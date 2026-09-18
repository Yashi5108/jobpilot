from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.database.models import ApplicationStatus


class ApplicationEventRead(BaseModel):
    id: int
    event_type: str
    description: str | None
    created_at: datetime


class ApplicationTrackerItem(BaseModel):
    id: int
    job_id: int
    job_title: str | None
    company: str | None
    status: ApplicationStatus
    resume_id: int | None
    match_score: int | None
    submitted_at: datetime | None
    updated_at: datetime
    events: list[ApplicationEventRead] = Field(default_factory=list)
