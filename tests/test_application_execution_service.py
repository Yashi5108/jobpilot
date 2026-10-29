from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.automation.provider_adapters import (
    GreenhouseProviderAdapter,
    LeverProviderAdapter,
    LinkedInProviderAdapter,
)
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

    assert result.mode == "AUTHORIZED_API"
    assert result.status == "LOGIN_REQUIRED"
    assert result.submitted is False
    assert result.requires_human_submit is True


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


def test_provider_adapters_support_real_job_sites() -> None:
    app = Application(job=Job(url="https://boards.greenhouse.io/acme/jobs/123"))
    assert GreenhouseProviderAdapter().supports(app) is True

    app = Application(job=Job(url="https://jobs.lever.co/acme/abc123"))
    assert LeverProviderAdapter().supports(app) is True

    app = Application(job=Job(url="https://www.linkedin.com/jobs/view/123456789"))
    assert LinkedInProviderAdapter().supports(app) is True


def test_provider_orchestration_summary_is_consistent() -> None:
    summaries = {
        adapter.name: adapter.summary()
        for adapter in [
            LinkedInProviderAdapter(),
            GreenhouseProviderAdapter(),
            LeverProviderAdapter(),
        ]
    }

    assert summaries["linkedin"].login_required is True
    assert summaries["linkedin"].approval_required is True
    assert summaries["greenhouse"].login_required is False
    assert summaries["lever"].approval_required is True
    assert all(summary.automation_actions for summary in summaries.values())
    assert all(summary.human_review_instructions for summary in summaries.values())


def test_greenhouse_provider_runs_playwright_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    application = Application(
        job=Job(url="https://boards.greenhouse.io/acme/jobs/123"),
        cover_letter="Dear team, I am excited to apply.",
    )
    application.profile = UserProfile(name="Ada Lovelace", email="ada@example.test", phone="1234567890", location="Remote")
    application.resume = Resume(name="Ada Resume", file_path="/tmp/resume.pdf")

    called: dict[str, str] = {}

    class _FakePage:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def goto(self, *args, **kwargs) -> None:
            return None

        def locator(self, selector: str):
            class _Locator:
                def __init__(self, parent: _FakePage, selector: str) -> None:
                    self.parent = parent
                    self.selector = selector

                def count(self) -> int:
                    return 1

                def get_attribute(self, attribute: str) -> str | None:
                    return None

                def evaluate(self, script: str):
                    return "TEXTAREA" if "textarea" in self.selector else "INPUT"

                def fill(self, value: str) -> None:
                    self.parent.values[self.selector] = value

                def click(self) -> None:
                    self.parent.values["clicked"] = self.selector

            return _Locator(self, selector)

    class _FakeBrowser:
        def __init__(self) -> None:
            self.page = _FakePage()

        def new_page(self):
            return self.page

        def close(self) -> None:
            return None

    class _FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless: bool):
                return _FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _FakePlaywright(),
    )

    result = GreenhouseProviderAdapter().submit(
        application=application,
        application_url="https://boards.greenhouse.io/acme/jobs/123",
    )

    assert result.success is True
    assert result.status == "SUBMITTED"
    assert "Greenhouse application flow" in result.message


def test_greenhouse_provider_runs_playwright_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = Application(
        job=Job(url="https://boards.greenhouse.io/acme/jobs/123"),
        cover_letter="Dear team, I am excited to apply.",
    )
    application.profile = UserProfile(
        name="Ada Lovelace",
        email="ada@example.test",
        phone="1234567890",
        location="Remote",
    )
    application.resume = Resume(name="Ada Resume", file_path="/tmp/resume.pdf")

    class _FakeLocator:
        def __init__(self, parent: "_FakePage", selector: str) -> None:
            self.parent = parent
            self.selector = selector

        def count(self) -> int:
            return 1

        def get_attribute(self, attribute: str) -> str | None:
            return None

        def fill(self, value: str) -> None:
            self.parent.values[self.selector] = value

        def click(self) -> None:
            self.parent.values["clicked"] = self.selector

    class _FakePage:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def goto(self, *args, **kwargs) -> None:
            return None

        def locator(self, selector: str):
            return _FakeLocator(self, selector)

    class _FakeBrowser:
        def __init__(self) -> None:
            self.page = _FakePage()

        def new_page(self):
            return self.page

        def close(self) -> None:
            return None

    class _FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless: bool):
                return _FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    import sys
    import types

    fake_module = types.ModuleType("playwright")
    fake_playwright_module = types.ModuleType("playwright.sync_api")
    fake_playwright_module.sync_playwright = lambda: _FakePlaywright()
    fake_module.sync_api = fake_playwright_module
    sys.modules["playwright"] = fake_module
    sys.modules["playwright.sync_api"] = fake_playwright_module

    result = GreenhouseProviderAdapter().submit(
        application=application,
        application_url="https://boards.greenhouse.io/acme/jobs/123",
    )

    assert result.success is True
    assert result.status == "SUBMITTED"
    assert "Greenhouse application flow" in result.message


def test_linkedin_provider_requires_login_and_disables_auto_submit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = Application(
        job=Job(url="https://www.linkedin.com/jobs/view/123456789"),
        cover_letter="I am excited to apply.",
    )
    application.profile = UserProfile(
        name="Ada Lovelace",
        email="ada@example.test",
        phone="1234567890",
        location="Remote",
    )

    class _FakeLocator:
        def __init__(self, parent: "_FakePage", selector: str) -> None:
            self.parent = parent
            self.selector = selector

        def count(self) -> int:
            return 1

        def fill(self, value: str) -> None:
            self.parent.values[self.selector] = value

        def click(self) -> None:
            self.parent.values["clicked"] = self.selector

    class _FakePage:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def goto(self, *args, **kwargs) -> None:
            return None

        def locator(self, selector: str):
            return _FakeLocator(self, selector)

    class _FakeBrowser:
        def __init__(self) -> None:
            self.page = _FakePage()

        def new_page(self):
            return self.page

        def close(self) -> None:
            return None

    class _FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless: bool):
                return _FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    import sys
    import types

    fake_module = types.ModuleType("playwright")
    fake_playwright_module = types.ModuleType("playwright.sync_api")
    fake_playwright_module.sync_playwright = lambda: _FakePlaywright()
    fake_module.sync_api = fake_playwright_module
    sys.modules["playwright"] = fake_module
    sys.modules["playwright.sync_api"] = fake_playwright_module

    result = LinkedInProviderAdapter().submit(
        application=application,
        application_url="https://www.linkedin.com/jobs/view/123456789",
    )

    assert result.success is False
    assert result.status == "LOGIN_REQUIRED"
    assert "login" in result.message.lower()
    assert "auto-submit" in result.message.lower()


def test_execute_application_passes_auto_submit_flag_when_enabled(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _seed_application(
        db_session,
        job_url="https://careers.example.test/jobs/backend-engineer",
    )

    monkeypatch.setattr(
        "backend.services.application_execution_service.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "browser_headless": True,
                "browser_assistant_mode": "playwright",
                "browser_auto_submit_enabled": True,
                "browser_restricted_hosts": ["linkedin.com", "naukri.com"],
            },
        )(),
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

    seen: dict[str, bool] = {}

    def fake_run(**kwargs):
        seen["auto_submit"] = kwargs.get("auto_submit", False)
        return (
            [{
                "field": "email",
                "label": "Email",
                "type": "email",
                "status": "FILLED",
                "value": "user@example.test",
                "message": "Filled successfully.",
            }],
            "Form fields were filled and submit was triggered automatically.",
        )

    monkeypatch.setattr(
        "backend.services.application_execution_service.run_browser_assistant_detailed",
        fake_run,
    )

    execute_application(
        db_session,
        application.id,
        ApplicationExecutionRequest(detect_fields=True, submit=True),
    )

    assert seen["auto_submit"] is True


def test_restricted_hosts_are_configurable() -> None:
    from backend.services.application_execution_service import _is_restricted_browser_host

    assert _is_restricted_browser_host("https://www.linkedin.com/jobs/view/123") is True
    assert _is_restricted_browser_host("https://careers.example.test/jobs/123") is False
