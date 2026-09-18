from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.database.models import (
    Application,
    ApplicationStatus,
    Job,
    Resume,
    UserProfile,
)
from backend.schemas.job import JobCreate, JobUpdate
from backend.services.job_service import (
    JobServiceError,
    create_job,
    delete_job,
    get_job,
    list_jobs,
    update_job,
)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_job_service.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = local_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _manual_job_payload(**overrides: object) -> JobCreate:
    base = {
        "title": "Senior Backend Engineer",
        "company": "Example Technologies",
        "location": "Bengaluru, India",
        "url": "https://example.com/jobs/senior-backend-engineer",
        "description": "Build reliable backend services",
        "employment_type": "Full-time",
    }
    base.update(overrides)
    return JobCreate(**base)


def test_create_and_get_job(db_session: Session) -> None:
    created = create_job(db_session, _manual_job_payload())
    fetched = get_job(db_session, created.id)

    assert fetched is not None
    assert fetched.title == "Senior Backend Engineer"
    assert fetched.source.source_type == "manual"


def test_manual_source_reused(db_session: Session) -> None:
    first = create_job(
        db_session, _manual_job_payload(url="https://example.com/jobs/1")
    )
    second = create_job(
        db_session, _manual_job_payload(url="https://example.com/jobs/2")
    )

    assert first.source_id == second.source_id


def test_duplicate_url_rejected(db_session: Session) -> None:
    create_job(db_session, _manual_job_payload())

    with pytest.raises(JobServiceError, match="already exists") as exc:
        create_job(db_session, _manual_job_payload(title="Another title"))

    assert exc.value.status_code == 409


def test_url_less_jobs_allowed(db_session: Session) -> None:
    create_job(db_session, _manual_job_payload(url=None, title="Role A"))
    create_job(db_session, _manual_job_payload(url=None, title="Role B"))

    assert len(list_jobs(db_session)) == 2


def test_list_jobs_with_company_filter(db_session: Session) -> None:
    create_job(db_session, _manual_job_payload(url="https://example.com/jobs/1"))
    create_job(
        db_session,
        _manual_job_payload(
            title="Data Engineer",
            company="Data Corp",
            url="https://example.com/jobs/2",
        ),
    )

    filtered = list_jobs(db_session, company="data corp")

    assert len(filtered) == 1
    assert filtered[0].company == "Data Corp"


def test_update_job(db_session: Session) -> None:
    created = create_job(db_session, _manual_job_payload())

    updated = update_job(
        db_session,
        created.id,
        JobUpdate(
            title="Principal Backend Engineer",
            company="Example Technologies",
            location="Remote",
            url="https://example.com/jobs/principal-backend-engineer",
            description="Updated description",
            employment_type="Contract",
        ),
    )

    assert updated.title == "Principal Backend Engineer"
    assert updated.location == "Remote"
    assert updated.employment_type == "Contract"


def test_delete_job_without_applications(db_session: Session) -> None:
    created = create_job(db_session, _manual_job_payload())

    delete_job(db_session, created.id)

    assert db_session.get(Job, created.id) is None


def test_delete_job_with_applications_rejected(db_session: Session) -> None:
    profile = UserProfile(name="User")
    db_session.add(profile)
    db_session.flush()

    job = create_job(db_session, _manual_job_payload())
    resume = Resume(
        profile_id=profile.id,
        name="Resume",
        file_path="data/resumes/r.pdf",
        file_type="pdf",
        parse_status="PARSED",
        normalized_text="resume text",
    )
    db_session.add(resume)
    db_session.flush()

    application = Application(
        job_id=job.id,
        profile_id=profile.id,
        resume_id=resume.id,
        status=ApplicationStatus.DISCOVERED,
    )
    db_session.add(application)
    db_session.commit()

    with pytest.raises(JobServiceError, match="application history") as exc:
        delete_job(db_session, job.id)

    assert exc.value.status_code == 409
    assert (
        db_session.scalar(select(Application).where(Application.job_id == job.id))
        is not None
    )
