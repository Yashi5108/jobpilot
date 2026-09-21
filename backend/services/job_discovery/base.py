from __future__ import annotations

from abc import ABC, abstractmethod

from backend.services.job_discovery.models import DiscoveredJob, DiscoverySearchCriteria


class JobDiscoveryConnectorError(ValueError):
    pass


class JobDiscoveryConnector(ABC):
    source_name: str
    source_type: str
    supports_apply: bool = False

    @abstractmethod
    def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
        """Return normalized jobs for the provided search criteria."""
