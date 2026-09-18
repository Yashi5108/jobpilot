from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NormalizedJob:
    title: str
    company: str
    description: str
    location: str | None = None
    employment_type: str | None = None
    work_arrangement: str | None = None
    url: str | None = None
    source_name: str = "manual"
    source_type: str = "manual"
    source_base_url: str | None = None
    external_id: str | None = None
    posted_at: datetime | None = None


class JobConnector(ABC):
    @abstractmethod
    def discover(self) -> list[NormalizedJob]:
        """Return normalized jobs discovered by this connector."""
