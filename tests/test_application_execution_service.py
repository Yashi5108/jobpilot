from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.browser.mapping import BrowserField
from backend.database.database import Base
from backend.database.models import (
    Application,
    ApplicationStatus,
    Job,
    JobSource,
    Resume,
    UserProfile,
)
from backend.schemas.application_execution import ApplicationExecutionRequest
from backend.services.application_execution_service import (
    AuthorizedExecutionResult,
    execute_application,
)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_execution_service_test.db"
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


def _seed_application(db: Session, *, job_url: str) -> Application:
    profile = UserProfile(name="Applicant", email="user@example.test")
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
        url=job_url,
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

    application = Application(
        job_id=job.id,
        profile_id=profile.id,
        resume_id=resume.id,
        status=ApplicationStatus.READY_FOR_REVIEW,
        user_approved=True,
        cover_letter="Approved cover letter",
        preparation_details={"cover_letter_status": "APPROVED"},
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def test_execute_application_returns_open_and_apply_for_restricted_sites(
    db_session: Session,
) -> None:
    application = _seed_application(
        db_session,
        job_url="https://www.linkedin.com/jobs/view/123",
    )

    result = execute_application(
        db_session,
        application.id,
        ApplicationExecutionRequest(),
    )

    assert result.mode == "OPEN_AND_APPLY"
    assert result.status == "OPEN_AND_APPLY"
    assert result.submitted is False


def test_execute_application_uses_authorized_adapter_when_available(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _seed_application(
        db_session,
        job_url="https://apply.example.test/job/123",
    )

    class _Adapter:
        name = "fake-api"

        def supports(self, app: Application) -> bool:
            return app.id == application.id

        def submit(self, *, application: Application, application_url: str | None):
            return AuthorizedExecutionResult(
                success=True,
                message="Submitted through authorized API.",
            )

    monkeypatch.setattr(
        "backend.services.application_execution_service._authorized_adapters",
        lambda: [_Adapter()],
    )

    result = execute_application(
        db_session,
        application.id,
        ApplicationExecutionRequest(submit=True),
    )

    assert result.mode == "AUTHORIZED_API"
    assert result.status == "SUBMITTED"
    assert result.submitted is True

    refreshed = db_session.get(Application, application.id)
    assert refreshed is not None
    assert refreshed.status == ApplicationStatus.APPLIED


def test_execute_application_runs_browser_assisted_flow(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _seed_application(
        db_session,
        job_url="https://careers.example.test/jobs/backend-engineer",
    )

    monkeypatch.setattr(
        "backend.services.application_execution_service.discover_browser_fields",
        lambda *args, **kwargs: [
            BrowserField(
                name="email",
                label="Email",
                field_type="email",
                required=True,
            )
        ],
    )
    monkeypatch.setattr(
        "backend.services.application_execution_service.run_browser_assistant_detailed",
        lambda **kwargs: (
            [
                {
                    "field": "email",
                    "label": "Email",
                    "type": "email",
                    "status": "FILLED",
                    "value": "user@example.test",
                    "message": "Filled successfully.",
                }
            ],
            (
                "Form fields were filled where safely mapped. "
                "Manual review and submission required."
            ),
        ),
    )

    result = execute_application(
        db_session,
        application.id,
        ApplicationExecutionRequest(detect_fields=True),
    )

    assert result.mode == "BROWSER_ASSISTED"
    assert result.status == "READY"
    assert result.submitted is False
    assert result.field_results[0].status == "FILLED"
