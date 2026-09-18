from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.browser.assistant import run_browser_assistant
from backend.browser.mapping import BrowserField, map_fields
from backend.database.database import Base
from backend.database.models import (
    Application,
    ApplicationQuestion,
    ApplicationStatus,
    Job,
    JobSource,
    QuestionStatus,
    Resume,
    UserProfile,
)


def _session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_browser_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return local_session()


def _seed_app(db: Session) -> Application:
    profile = UserProfile(
        name="User",
        email="user@example.test",
        phone="12345",
        location="Bengaluru",
    )
    db.add(profile)
    db.flush()

    source = JobSource(name="manual", source_type="manual")
    db.add(source)
    db.flush()

    job = Job(
        source_id=source.id,
        title="Backend Engineer",
        company="Acme",
        description="Build APIs",
        url="https://example.com/jobs/backend-engineer",
    )
    db.add(job)
    db.flush()

    resume = Resume(
        profile_id=profile.id,
        name="Resume",
        file_path="data/resumes/resume.pdf",
    )
    db.add(resume)
    db.flush()

    app = Application(
        job_id=job.id,
        profile_id=profile.id,
        resume_id=resume.id,
        status=ApplicationStatus.READY_FOR_REVIEW,
        cover_letter="Cover letter draft",
    )
    db.add(app)
    db.flush()

    question = ApplicationQuestion(
        application_id=app.id,
        question="why are you interested in this role?",
        answer="Role fit",
        status=QuestionStatus.DRAFT,
    )
    db.add(question)
    db.commit()
    db.refresh(app)
    return app


def test_map_fields_marks_unknown_required(tmp_path: Path) -> None:
    db = _session(tmp_path)
    try:
        app = _seed_app(db)
        profile = db.get(UserProfile, app.profile_id)
        assert profile is not None

        mapped, unknown = map_fields(
            profile=profile,
            application=app,
            fields=[
                BrowserField(
                    name="email",
                    label="Email",
                    field_type="email",
                    required=True,
                ),
                BrowserField(
                    name="mystery",
                    label="Favorite color",
                    field_type="text",
                    required=True,
                ),
            ],
        )

        assert any(item["field"] == "email" for item in mapped)
        assert "Favorite color" in unknown
    finally:
        db.close()


def test_browser_assistant_dry_run_never_submits(tmp_path: Path) -> None:
    db = _session(tmp_path)
    try:
        app = _seed_app(db)
        mapped, unknown, message = run_browser_assistant(
            db=db,
            application_id=app.id,
            application_url="https://example.com/jobs/backend-engineer/apply",
            fields=[
                BrowserField(
                    name="full_name",
                    label="Full Name",
                    field_type="text",
                    required=True,
                ),
                BrowserField(
                    name="email",
                    label="Email",
                    field_type="email",
                    required=True,
                ),
            ],
            dry_run=True,
        )

        assert len(mapped) >= 1
        assert isinstance(unknown, list)
        assert "Manual" in message or "manual" in message

        refreshed = db.get(Application, app.id)
        assert refreshed is not None
        assert refreshed.status == ApplicationStatus.READY_FOR_REVIEW
        assert refreshed.preparation_details is not None
    finally:
        db.close()
