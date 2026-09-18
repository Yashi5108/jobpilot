"""Connectors for importing jobs from safe/manual sources."""

from backend.connectors.base import JobConnector, NormalizedJob
from backend.connectors.manual import ManualConnector, ManualJobInput
from backend.connectors.structured import StructuredImportConnector

__all__ = [
    "JobConnector",
    "NormalizedJob",
    "ManualConnector",
    "ManualJobInput",
    "StructuredImportConnector",
]
