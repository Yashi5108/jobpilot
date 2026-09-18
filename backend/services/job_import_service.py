from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.connectors.base import NormalizedJob
from backend.connectors.manual import ManualConnector
from backend.connectors.structured import (
    StructuredImportConnector,
    load_csv_jobs,
    load_json_jobs,
)
from backend.schemas.job import JobCreate
from backend.schemas.job_import import (
    JobImportRecord,
    JobImportResult,
    ManualJobImportRequest,
)
from backend.services.job_service import JobServiceError, create_job


class JobImportServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class JobImportItem:
    payload: dict[str, object]


def import_manual_job(db: Session, payload: ManualJobImportRequest) -> JobImportResult:
    connector = ManualConnector(payload.model_dump(mode="json"))
    jobs = connector.discover()
    return _persist_jobs(db, jobs)


def import_jobs_from_json(db: Session, content: bytes) -> JobImportResult:
    try:
        records = load_json_jobs(content)
        connector = StructuredImportConnector(records)
        jobs = connector.discover()
    except ValueError as exc:
        raise JobImportServiceError(str(exc), status_code=422) from exc
    return _persist_jobs(db, jobs)


def import_jobs_from_csv(db: Session, content: bytes) -> JobImportResult:
    try:
        records = load_csv_jobs(content)
        connector = StructuredImportConnector(records)
        jobs = connector.discover()
    except ValueError as exc:
        raise JobImportServiceError(str(exc), status_code=422) from exc
    return _persist_jobs(db, jobs)


def _persist_jobs(db: Session, jobs: list[NormalizedJob]) -> JobImportResult:
    result = JobImportResult()

    for idx, job in enumerate(jobs):
        record = JobImportRecord(
            index=idx,
            title=job.title,
            company=job.company,
            status="IMPORTED",
        )

        try:
            created = create_job(db, _normalized_to_job_create(job))
        except JobServiceError as exc:
            if exc.status_code == 409:
                result.skipped_count += 1
                record.status = "SKIPPED_DUPLICATE"
                record.error = str(exc)
            else:
                result.failed_count += 1
                record.status = "FAILED"
                record.error = str(exc)
        except ValueError as exc:
            result.failed_count += 1
            record.status = "FAILED"
            record.error = str(exc)
        else:
            result.imported_count += 1
            record.job_id = created.id

        result.records.append(record)

    return result


def _normalized_to_job_create(job: NormalizedJob) -> JobCreate:
    return JobCreate.model_validate(
        {
            "source_name": job.source_name,
            "source_type": job.source_type,
            "source_base_url": job.source_base_url,
            "external_id": job.external_id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
            "description": job.description,
            "employment_type": job.employment_type,
            "remote_type": job.work_arrangement,
            "discovered_at": job.posted_at,
        }
    )
