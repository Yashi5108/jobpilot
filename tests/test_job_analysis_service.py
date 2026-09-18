from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.ai.job_analyzer import JobAnalysisError
from backend.database.database import Base
from backend.database.models import Job
from backend.schemas.job import JobCreate
from backend.schemas.job_analysis import JobAnalysis
from backend.services.job_analysis_service import (
    JobAnalysisServiceError,
    analyze_job,
    get_job_analysis,
)
from backend.services.job_service import create_job


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_job_analysis_service.db"
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


def _create_job(db_session: Session, **overrides: object) -> Job:
    payload = {
        "title": "Senior Backend Engineer",
        "company": "Example Technologies",
        "location": "Bengaluru",
        "url": "https://example.com/jobs/backend-engineer",
        "description": "Need Python and FastAPI with 5+ years experience.",
        "employment_type": "Full-time",
    }
    payload.update(overrides)
    return create_job(db_session, JobCreate(**payload))


def _analysis_payload() -> JobAnalysis:
    return JobAnalysis.model_validate(
        {
            "role_summary": "Build backend services",
            "required_skills": [{"name": "Python", "category": "language"}],
            "preferred_skills": [{"name": "AWS", "category": "cloud"}],
            "minimum_years_experience": 5,
            "preferred_years_experience": None,
            "experience_requirements": [
                {"requirement": "5+ years backend", "minimum_years": 5}
            ],
            "education_requirements": [],
            "required_certifications": [],
            "preferred_certifications": [],
            "responsibilities": ["Design APIs"],
            "domain_requirements": [],
            "communication_requirements": [],
            "leadership_requirements": [],
            "work_authorization_requirements": [],
            "travel_requirements": [],
            "other_requirements": [],
        }
    )


def test_analyze_job_success_persists_result(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _create_job(db_session)

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description",
        lambda _: _analysis_payload(),
    )

    analyzed_job, analysis = analyze_job(db_session, job.id)

    assert analyzed_job.analysis_status == "COMPLETED"
    assert analyzed_job.analyzed_at is not None
    assert isinstance(analyzed_job.analysis_result, dict)
    assert analysis.required_skills[0].name == "Python"


def test_analyze_job_missing_job(db_session: Session) -> None:
    with pytest.raises(JobAnalysisServiceError, match="Job not found") as exc:
        analyze_job(db_session, job_id=999)

    assert exc.value.status_code == 404


def test_analyze_job_missing_description(db_session: Session) -> None:
    job = _create_job(db_session)
    job.description = ""
    db_session.add(job)
    db_session.commit()

    with pytest.raises(JobAnalysisServiceError, match="no description") as exc:
        analyze_job(db_session, job_id=job.id)

    assert exc.value.status_code == 422


def test_force_false_returns_existing_analysis(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _create_job(db_session)
    initial = _analysis_payload().model_dump()
    job.analysis_status = "COMPLETED"
    job.analysis_result = initial
    db_session.add(job)
    db_session.commit()

    def _should_not_be_called(_: str) -> JobAnalysis:
        raise AssertionError("analyze_job_description should not be called")

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description",
        _should_not_be_called,
    )

    analyzed_job, analysis = analyze_job(db_session, job_id=job.id, force=False)

    assert analyzed_job.analysis_status == "COMPLETED"
    assert analysis.role_summary == "Build backend services"


def test_force_true_reruns_analysis(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _create_job(db_session)
    job.analysis_status = "COMPLETED"
    job.analysis_result = _analysis_payload().model_dump()
    db_session.add(job)
    db_session.commit()

    called = {"count": 0}

    def _reanalyze(_: str) -> JobAnalysis:
        called["count"] += 1
        return _analysis_payload()

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description",
        _reanalyze,
    )

    analyzed_job, _ = analyze_job(db_session, job_id=job.id, force=True)

    assert called["count"] == 1
    assert analyzed_job.analysis_status == "COMPLETED"


def test_analyze_job_failure_marks_failed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _create_job(db_session)

    def _fail(_: str) -> JobAnalysis:
        raise JobAnalysisError("AI returned invalid job analysis structure.", 502)

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description",
        _fail,
    )

    with pytest.raises(JobAnalysisServiceError):
        analyze_job(db_session, job_id=job.id)

    refreshed = db_session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.analysis_status == "FAILED"
    assert refreshed.analyzed_at is not None


def test_get_job_analysis_validates_persisted_json(db_session: Session) -> None:
    job = _create_job(db_session)
    job.analysis_status = "COMPLETED"
    job.analysis_result = _analysis_payload().model_dump()
    db_session.add(job)
    db_session.commit()

    stored_job, analysis = get_job_analysis(db_session, job_id=job.id)

    assert stored_job.id == job.id
    assert analysis is not None
    assert analysis.minimum_years_experience == 5


def test_get_job_analysis_returns_none_when_invalid_json(db_session: Session) -> None:
    job = _create_job(db_session)
    job.analysis_status = "COMPLETED"
    job.analysis_result = {"required_skills": "oops"}
    db_session.add(job)
    db_session.commit()

    _, analysis = get_job_analysis(db_session, job_id=job.id)

    assert analysis is None
