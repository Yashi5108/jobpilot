from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JobSkillCategory = Literal[
    "language",
    "framework",
    "library",
    "database",
    "cloud",
    "devops",
    "testing",
    "architecture",
    "tool",
    "domain",
    "other",
]


class JobSkill(BaseModel):
    name: str
    category: JobSkillCategory | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Skill name must not be empty")
        return cleaned


class JobExperienceRequirement(BaseModel):
    requirement: str
    minimum_years: float | None = Field(default=None, ge=0, le=80)
    preferred_years: float | None = Field(default=None, ge=0, le=80)

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Experience requirement must not be empty")
        return cleaned

    @model_validator(mode="after")
    def validate_year_bounds(self) -> "JobExperienceRequirement":
        if (
            self.minimum_years is not None
            and self.preferred_years is not None
            and self.preferred_years < self.minimum_years
        ):
            raise ValueError("preferred_years must be >= minimum_years")
        return self


class JobAnalysis(BaseModel):
    role_summary: str | None = None
    seniority_level: str | None = None
    employment_type: str | None = None
    work_arrangement: str | None = None
    location: str | None = None

    required_skills: list[JobSkill] = Field(default_factory=list)
    preferred_skills: list[JobSkill] = Field(default_factory=list)

    minimum_years_experience: float | None = Field(default=None, ge=0, le=80)
    preferred_years_experience: float | None = Field(default=None, ge=0, le=80)
    experience_requirements: list[JobExperienceRequirement] = Field(
        default_factory=list
    )

    education_requirements: list[str] = Field(default_factory=list)
    required_certifications: list[str] = Field(default_factory=list)
    preferred_certifications: list[str] = Field(default_factory=list)

    responsibilities: list[str] = Field(default_factory=list)

    domain_requirements: list[str] = Field(default_factory=list)
    communication_requirements: list[str] = Field(default_factory=list)
    leadership_requirements: list[str] = Field(default_factory=list)
    work_authorization_requirements: list[str] = Field(default_factory=list)
    travel_requirements: list[str] = Field(default_factory=list)
    other_requirements: list[str] = Field(default_factory=list)

    @field_validator(
        "role_summary",
        "seniority_level",
        "employment_type",
        "work_arrangement",
        "location",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator(
        "education_requirements",
        "required_certifications",
        "preferred_certifications",
        "responsibilities",
        "domain_requirements",
        "communication_requirements",
        "leadership_requirements",
        "work_authorization_requirements",
        "travel_requirements",
        "other_requirements",
    )
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            cleaned = raw.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def dedupe_skills(cls, skills: list[JobSkill]) -> list[JobSkill]:
        normalized: list[JobSkill] = []
        seen: set[tuple[str, str | None]] = set()
        for skill in skills:
            key = (skill.name.strip().lower(), skill.category)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(skill)
        return normalized

    @model_validator(mode="after")
    def validate_top_level_year_bounds(self) -> "JobAnalysis":
        if (
            self.minimum_years_experience is not None
            and self.preferred_years_experience is not None
            and self.preferred_years_experience < self.minimum_years_experience
        ):
            raise ValueError(
                "preferred_years_experience must be >= minimum_years_experience"
            )
        return self


class JobAnalysisRead(BaseModel):
    job_id: int
    analysis_status: str
    analyzed_at: datetime | None = None
    analysis: JobAnalysis | None = None

    model_config = ConfigDict(from_attributes=True)
