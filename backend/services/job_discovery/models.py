from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DiscoveredJobAction(str, Enum):
    APPLY = "APPLY"
    OPEN_AND_APPLY = "OPEN_AND_APPLY"


@dataclass(frozen=True)
class DiscoverySearchCriteria:
    queries: list[str]
    skills: list[str]
    location: str | None = None
    remote_preference: str | None = None
    years_of_experience: float | None = None
    limit_per_source: int = 10


@dataclass(frozen=True)
class DiscoveredJob:
    title: str
    company: str
    location: str | None
    description: str
    job_url: str | None
    source_name: str
    source_type: str
    external_id: str | None = None
    discovered_at: datetime | None = None
    source_base_url: str | None = None
    supports_apply: bool = False


@dataclass(frozen=True)
class DiscoveryError:
    source: str
    message: str


@dataclass(frozen=True)
class DiscoveredJobLink:
    source: str
    source_type: str
    job_url: str | None = None


@dataclass
class AggregatedDiscoveredJob:
    primary: DiscoveredJob
    discovered_sources: list[str] = field(default_factory=list)
    discovered_links: list[DiscoveredJobLink] = field(default_factory=list)

    def add_source(self, source_label: str, job: DiscoveredJob) -> None:
        if source_label not in self.discovered_sources:
            self.discovered_sources.append(source_label)

        link = DiscoveredJobLink(
            source=job.source_name,
            source_type=job.source_type,
            job_url=job.job_url,
        )
        if link not in self.discovered_links:
            self.discovered_links.append(link)

        if _job_quality_key(job) > _job_quality_key(self.primary):
            self.primary = job


def _job_quality_key(job: DiscoveredJob) -> tuple[int, int, int, int]:
    return (
        1 if job.external_id else 0,
        1 if job.job_url else 0,
        len(job.description.strip()),
        1 if job.supports_apply else 0,
    )
