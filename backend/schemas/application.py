from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.database.models import ApplicationStatus


class ApplicationCreate(BaseModel):
    job_id: int
    profile_id: int
    resume_id: int | None = None
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    cover_letter: str | None = None
    user_approved: bool = False
    submitted_at: datetime | None = None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationApproveAction(BaseModel):
    approve: bool = True


class ApplicationSubmitAction(BaseModel):
    confirm: bool = True


class ApplicationRead(BaseModel):
    id: int
    job_id: int
    profile_id: int
    resume_id: int | None
    status: ApplicationStatus
    cover_letter: str | None
    preparation_details: dict | None
    user_approved: bool
    approved_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
