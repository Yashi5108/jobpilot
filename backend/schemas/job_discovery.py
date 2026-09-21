from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field

from backend.schemas.job_match import JobMatchResult


class JobDiscoveryRequest(BaseModel):
    resume_id: int = Field(gt=0)
    sources: list[str] = Field(default_factory=lambda: ["remotive"])
    max_results_per_source: int = Field(default=10, ge=1, le=25)
    min_match_score: int | None = Field(default=None, ge=0, le=100)


class JobSearchCriteriaRead(BaseModel):
    queries: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    remote_preference: str | None = None
    years_of_experience: float | None = None


class JobDiscoveryErrorRead(BaseModel):
    source: str
    message: str


class JobDiscoveryLinkRead(BaseModel):
    source: str
    source_type: str
    job_url: AnyHttpUrl | None = None


class JobDiscoveryResultRead(BaseModel):
    job_id: int
    title: str
    company: str
    location: str | None = None
    job_url: AnyHttpUrl | None = None
    source: str
    source_type: str
    discovered_sources: list[str] = Field(default_factory=list)
    discovered_links: list[JobDiscoveryLinkRead] = Field(default_factory=list)
    external_id: str | None = None
    discovered_at: datetime | None = None
    action: Literal["APPLY", "OPEN_AND_APPLY"]
    action_url: AnyHttpUrl | None = None
    match_score: int = Field(ge=0, le=100)
    match: JobMatchResult


class JobDiscoveryResponse(BaseModel):
    resume_id: int
    criteria: JobSearchCriteriaRead
    total_discovered: int = 0
    total_deduplicated: int = 0
    total_matched: int = 0
    results: list[JobDiscoveryResultRead] = Field(default_factory=list)
    errors: list[JobDiscoveryErrorRead] = Field(default_factory=list)
