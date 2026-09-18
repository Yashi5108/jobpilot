from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MatchStatus = Literal["MATCHED", "NOT_MATCHED", "UNKNOWN", "NOT_REQUIRED"]


class JobMatchRequest(BaseModel):
    resume_id: int = Field(gt=0)


class JobMatchResult(BaseModel):
    job_id: int
    resume_id: int
    profile_id: int
    score: int = Field(ge=0, le=100)

    required_skill_score: int | None = Field(default=None, ge=0, le=100)
    preferred_skill_score: int | None = Field(default=None, ge=0, le=100)
    experience_score: int | None = Field(default=None, ge=0, le=100)
    education_score: int | None = Field(default=None, ge=0, le=100)
    certification_score: int | None = Field(default=None, ge=0, le=100)
    domain_score: int | None = Field(default=None, ge=0, le=100)

    matched_required_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)

    matched_required_certifications: list[str] = Field(default_factory=list)
    missing_required_certifications: list[str] = Field(default_factory=list)
    matched_preferred_certifications: list[str] = Field(default_factory=list)
    missing_preferred_certifications: list[str] = Field(default_factory=list)

    experience_result: MatchStatus
    education_result: MatchStatus
    certification_result: MatchStatus
    domain_result: MatchStatus

    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    matched_at: datetime
