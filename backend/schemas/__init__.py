"""Pydantic schemas for JobPilot backend APIs."""

from backend.schemas.analytics import (
    AnalyticsOverview,
    SkillCount,
    StatusCount,
    TimeBucketCount,
)
from backend.schemas.application import (
    ApplicationApproveAction,
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationSubmitAction,
)
from backend.schemas.application_preparation import (
    ApplicationPreparationRead,
    ApplicationQuestionRead,
    ApplicationReviewRead,
    PrepareApplicationRequest,
)
from backend.schemas.application_tracker import (
    ApplicationEventRead,
    ApplicationTrackerItem,
)
from backend.schemas.browser_assistant import (
    BrowserAssistRequest,
    BrowserAssistResponse,
    BrowserFieldInput,
)
from backend.schemas.job import JobCreate, JobRead, JobSourceRead, JobUpdate
from backend.schemas.job_analysis import (
    JobAnalysis,
    JobAnalysisRead,
    JobExperienceRequirement,
    JobSkill,
)
from backend.schemas.job_import import (
    JobImportRecord,
    JobImportResult,
    ManualJobImportRequest,
)
from backend.schemas.job_match import JobMatchRequest, JobMatchResult
from backend.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate
from backend.schemas.resume import (
    ResumeCreate,
    ResumeRead,
    ResumeTextRead,
    ResumeUploadResponse,
)
from backend.schemas.resume_analysis import CandidateProfile, ResumeAnalysisRead

__all__ = [
    "ApplicationCreate",
    "ApplicationRead",
    "ApplicationStatusUpdate",
    "ApplicationApproveAction",
    "ApplicationSubmitAction",
    "PrepareApplicationRequest",
    "ApplicationQuestionRead",
    "ApplicationPreparationRead",
    "ApplicationReviewRead",
    "ApplicationEventRead",
    "ApplicationTrackerItem",
    "BrowserFieldInput",
    "BrowserAssistRequest",
    "BrowserAssistResponse",
    "StatusCount",
    "TimeBucketCount",
    "SkillCount",
    "AnalyticsOverview",
    "JobSkill",
    "JobExperienceRequirement",
    "JobAnalysis",
    "JobAnalysisRead",
    "ManualJobImportRequest",
    "JobImportRecord",
    "JobImportResult",
    "JobMatchRequest",
    "JobMatchResult",
    "JobCreate",
    "JobRead",
    "JobSourceRead",
    "JobUpdate",
    "ProfileCreate",
    "ProfileRead",
    "ProfileUpdate",
    "CandidateProfile",
    "ResumeAnalysisRead",
    "ResumeCreate",
    "ResumeRead",
    "ResumeTextRead",
    "ResumeUploadResponse",
]
