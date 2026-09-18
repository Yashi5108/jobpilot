from __future__ import annotations

from pydantic import BaseModel, Field


class StatusCount(BaseModel):
    status: str
    count: int


class TimeBucketCount(BaseModel):
    date: str
    count: int


class SkillCount(BaseModel):
    skill: str
    count: int


class AnalyticsOverview(BaseModel):
    jobs_found: int = 0
    shortlisted_jobs: int = 0
    applications: int = 0
    interviews: int = 0
    offers: int = 0
    rejected: int = 0
    applications_by_status: list[StatusCount] = Field(default_factory=list)
    applications_over_time: list[TimeBucketCount] = Field(default_factory=list)
    average_match_score: float | None = None
    top_matched_skills: list[SkillCount] = Field(default_factory=list)
    frequently_missing_skills: list[SkillCount] = Field(default_factory=list)
