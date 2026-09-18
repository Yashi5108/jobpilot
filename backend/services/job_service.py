from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.models import Application, Job, JobSource
from backend.schemas.job import JobCreate, JobUpdate


class JobServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def list_jobs(db: Session, company: str | None = None) -> list[Job]:
    statement = select(Job).order_by(Job.id.desc())
    if company:
        statement = statement.where(func.lower(Job.company) == company.strip().lower())
    return list(db.scalars(statement).all())


def get_job(db: Session, job_id: int) -> Job | None:
    return db.get(Job, job_id)


def create_job(db: Session, payload: JobCreate) -> Job:
    source: JobSource

    if payload.source_id is not None:
        source = db.get(JobSource, payload.source_id)
        if source is None:
            raise JobServiceError("Job source not found", status_code=404)
    else:
        source = _get_or_create_source(
            db,
            source_name=payload.source_name or "manual",
            source_type=payload.source_type or "manual",
            source_base_url=payload.source_base_url,
        )

    duplicate = _find_duplicate_job(db, payload=payload, source_id=source.id)
    if duplicate is not None:
        raise JobServiceError(
            "A duplicate job already exists for this source/identity.",
            status_code=409,
        )

    job_data = payload.model_dump(
        exclude={"source_id", "source_name", "source_type", "source_base_url"},
        mode="json",
    )
    if job_data.get("url"):
        job_data["url"] = str(job_data["url"])

    job = Job(source_id=source.id, **job_data)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: int, payload: JobUpdate) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise JobServiceError("Job not found", status_code=404)

    new_url = str(payload.url) if payload.url else None
    if new_url:
        duplicate = _find_duplicate_by_url(db, new_url)
        if duplicate is not None and duplicate.id != job.id:
            raise JobServiceError(
                "A job with this URL already exists.",
                status_code=409,
            )

    job.title = payload.title
    job.company = payload.company
    job.location = payload.location
    job.url = new_url
    job.description = payload.description
    job.employment_type = payload.employment_type

    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def delete_job(db: Session, job_id: int) -> None:
    job = db.get(Job, job_id)
    if job is None:
        raise JobServiceError("Job not found", status_code=404)

    has_applications = db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.job_id == job.id)
    )
    if has_applications:
        raise JobServiceError(
            "Job cannot be deleted because application history exists.",
            status_code=409,
        )

    db.delete(job)
    db.commit()


def _get_or_create_source(
    db: Session,
    source_name: str,
    source_type: str,
    source_base_url: str | None,
) -> JobSource:
    existing = db.scalar(
        select(JobSource).where(
            func.lower(JobSource.name) == source_name.strip().lower(),
            func.lower(JobSource.source_type) == source_type.strip().lower(),
        )
    )
    if existing is not None:
        return existing

    source = JobSource(
        name=source_name.strip(),
        source_type=source_type.strip().lower(),
        base_url=source_base_url.strip() if source_base_url else None,
    )
    db.add(source)
    db.flush()
    return source


def _find_duplicate_by_url(db: Session, url: str | None) -> Job | None:
    if not url:
        return None
    return db.scalar(select(Job).where(Job.url == url.strip()))


def _find_duplicate_job(db: Session, payload: JobCreate, source_id: int) -> Job | None:
    external_id = (payload.external_id or "").strip()
    if external_id:
        existing = db.scalar(
            select(Job).where(
                Job.source_id == source_id,
                Job.external_id == external_id,
            )
        )
        if existing is not None:
            return existing

    if payload.url is not None:
        url = str(payload.url).strip()
        existing = db.scalar(select(Job).where(Job.url == url))
        if existing is not None:
            return existing

    company = payload.company.strip().lower()
    title = payload.title.strip().lower()
    if payload.url is not None:
        url = str(payload.url).strip()
        return db.scalar(
            select(Job).where(
                func.lower(Job.company) == company,
                func.lower(Job.title) == title,
                Job.url == url,
            )
        )

    return None
