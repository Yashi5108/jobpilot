from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SkillCategory = Literal[
    "programming_language",
    "framework",
    "database",
    "cloud",
    "devops",
    "testing",
    "architecture",
    "tool",
    "platform",
    "other",
]


class CandidateSkill(BaseModel):
    name: str
    category: SkillCategory | None = None
    proficiency: str | None = None


class CandidateExperience(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    responsibilities: list[str] = Field(default_factory=list)


class CandidateEducation(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class CandidateProject(BaseModel):
    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class CandidateCertification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None


class CandidateProfile(BaseModel):
    name: str | None = None
    headline: str | None = None
    summary: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    skills: list[CandidateSkill] = Field(default_factory=list)
    experience: list[CandidateExperience] = Field(default_factory=list)
    education: list[CandidateEducation] = Field(default_factory=list)
    projects: list[CandidateProject] = Field(default_factory=list)
    certifications: list[CandidateCertification] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


class ResumeAnalysisRead(BaseModel):
    resume_id: int
    analysis_status: str
    analyzed_at: datetime | None = None
    profile: CandidateProfile | None = None

    model_config = ConfigDict(from_attributes=True)
