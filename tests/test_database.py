from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.database.models import (
    Application,
    ApplicationEvent,
    ApplicationQuestion,
    ApplicationStatus,
    Job,
    JobSource,
    QuestionStatus,
    Resume,
    UserProfile,
)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_test.db"
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


def test_database_creation_creates_tables(db_session: Session) -> None:
    profile = UserProfile(name="Test User")
    db_session.add(profile)
    db_session.commit()

    stored = db_session.scalar(select(UserProfile).where(UserProfile.id == profile.id))
    assert stored is not None


def test_user_profile_create_and_retrieve(db_session: Session) -> None:
    profile = UserProfile(name="Alex", email="alex@example.test", location="Remote")
    db_session.add(profile)
    db_session.commit()

    retrieved = db_session.scalar(
        select(UserProfile).where(UserProfile.email == "alex@example.test")
    )
    assert retrieved is not None
    assert retrieved.name == "Alex"
    assert retrieved.location == "Remote"


def test_job_source_and_job_relationship(db_session: Session) -> None:
    source = JobSource(name="Manual Board", source_type="manual")
    job = Job(title="Backend Engineer", company="Acme", source=source)
    db_session.add(job)
    db_session.commit()

    retrieved_job = db_session.scalar(
        select(Job).where(Job.title == "Backend Engineer")
    )
    assert retrieved_job is not None
    assert retrieved_job.source.name == "Manual Board"
    assert source.jobs[0].title == "Backend Engineer"


def test_application_relationships(db_session: Session) -> None:
    profile = UserProfile(name="Riley")
    source = JobSource(name="API Source", source_type="api")
    job = Job(title="Data Engineer", source=source)
    resume = Resume(
        profile=profile, name="Primary Resume", file_path="data/resumes/a.pdf"
    )
    application = Application(
        job=job,
        profile=profile,
        resume=resume,
        status=ApplicationStatus.PREPARING,
    )
    db_session.add(application)
    db_session.commit()

    stored_application = db_session.scalar(
        select(Application).where(Application.id == application.id)
    )
    assert stored_application is not None
    assert stored_application.profile.name == "Riley"
    assert stored_application.job.title == "Data Engineer"
    assert stored_application.resume is not None
    assert stored_application.resume.name == "Primary Resume"


def test_application_status_allows_only_supported_values(db_session: Session) -> None:
    profile = UserProfile(name="Jordan")
    source = JobSource(name="Career Site", source_type="career_site")
    job = Job(title="Platform Engineer", source=source)
    db_session.add_all([profile, job])
    db_session.flush()

    valid = Application(job=job, profile=profile, status=ApplicationStatus.DISCOVERED)
    db_session.add(valid)
    db_session.commit()

    invalid = Application(job=job, profile=profile, status="INVALID")  # type: ignore[arg-type]
    db_session.add(invalid)
    with pytest.raises((StatementError, LookupError)):
        db_session.commit()
    db_session.rollback()


def test_application_question_needs_user_input_status(db_session: Session) -> None:
    profile = UserProfile(name="Taylor")
    source = JobSource(name="Manual", source_type="manual")
    job = Job(title="QA Engineer", source=source)
    application = Application(
        job=job, profile=profile, status=ApplicationStatus.PREPARING
    )
    question = ApplicationQuestion(
        application=application,
        question="Are you authorized to work in this country?",
        status=QuestionStatus.NEEDS_USER_INPUT,
    )
    db_session.add(question)
    db_session.commit()

    stored_question = db_session.scalar(
        select(ApplicationQuestion).where(ApplicationQuestion.id == question.id)
    )
    assert stored_question is not None
    assert stored_question.status == QuestionStatus.NEEDS_USER_INPUT


def test_deleting_application_cascades_questions_and_events(
    db_session: Session,
) -> None:
    profile = UserProfile(name="Sam")
    source = JobSource(name="Manual", source_type="manual")
    job = Job(title="SRE", source=source)
    application = Application(
        job=job, profile=profile, status=ApplicationStatus.SHORTLISTED
    )
    question = ApplicationQuestion(
        application=application,
        question="When can you join?",
        status=QuestionStatus.DRAFT,
    )
    event = ApplicationEvent(
        application=application,
        event_type="CREATED",
        description="Application created",
    )

    db_session.add_all([question, event])
    db_session.commit()

    db_session.delete(application)
    db_session.commit()

    remaining_questions = db_session.scalars(select(ApplicationQuestion)).all()
    remaining_events = db_session.scalars(select(ApplicationEvent)).all()
    assert remaining_questions == []
    assert remaining_events == []
