from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.database.models import Job, QuestionStatus, Resume, UserProfile
from backend.schemas.application_preparation import PrepareApplicationRequest
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.resume_analysis import CandidateProfile
from backend.services.application_preparation_service import (
    prepare_application,
    regenerate_cover_letter,
)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_preparation_service_test.db"
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


def _seed_ready_entities(db: Session) -> tuple[int, int, int]:
    profile = UserProfile(
        name="Applicant",
        email="applicant@example.test",
        work_authorization="Authorized to work in India",
    )
    db.add(profile)
    db.flush()

    resume = Resume(
        profile_id=profile.id,
        name="Resume",
        file_path="data/resumes/resume.pdf",
        analysis_status="COMPLETED",
        analysis_result=CandidateProfile.model_validate(
            {
                "headline": "Backend Engineer",
                "skills": [{"name": "Python"}, {"name": "FastAPI"}],
                "experience": [
                    {"start_date": "2018-01", "end_date": None, "is_current": True}
                ],
                "education": [{"degree": "Bachelor of Engineering"}],
                "projects": [],
                "certifications": [],
                "achievements": [],
                "languages": [],
            }
        ).model_dump(),
    )
    db.add(resume)
    db.flush()

    job = Job(
        source_id=_manual_source_id(db),
        title="Backend Engineer",
        company="Acme",
        description="Build APIs with Python",
        analysis_status="COMPLETED",
        analysis_result=JobAnalysis.model_validate(
            {
                "role_summary": "Backend API engineering",
                "required_skills": [{"name": "Python", "category": "language"}],
                "preferred_skills": [{"name": "FastAPI", "category": "framework"}],
                "minimum_years_experience": 2,
                "preferred_years_experience": None,
                "experience_requirements": [],
                "education_requirements": [],
                "required_certifications": [],
                "preferred_certifications": [],
                "responsibilities": [],
                "domain_requirements": [],
                "communication_requirements": [],
                "leadership_requirements": [],
                "work_authorization_requirements": [],
                "travel_requirements": [],
                "other_requirements": [],
            }
        ).model_dump(),
    )
    db.add(job)
    db.commit()

    return profile.id, resume.id, job.id


def _manual_source_id(db: Session) -> int:
    from backend.database.models import JobSource

    source = JobSource(name="manual", source_type="manual")
    db.add(source)
    db.flush()
    return source.id


def test_prepare_application_generates_review_artifacts(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id, resume_id, job_id = _seed_ready_entities(db_session)

    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_cover_letter",
        lambda **_: "Cover letter draft",
    )
    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_screening_answer",
        lambda **_: ("Draft answer", QuestionStatus.DRAFT),
    )

    result = prepare_application(
        db_session,
        PrepareApplicationRequest(
            job_id=job_id,
            profile_id=profile_id,
            resume_id=resume_id,
        ),
    )

    assert result.status.value == "READY_FOR_REVIEW"
    assert result.cover_letter == "Cover letter draft"
    assert len(result.questions) >= 1


def test_regenerate_cover_letter_updates_draft(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id, resume_id, job_id = _seed_ready_entities(db_session)

    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_cover_letter",
        lambda **_: "Initial cover letter",
    )
    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_screening_answer",
        lambda **_: (None, QuestionStatus.NEEDS_USER_INPUT),
    )

    prepared = prepare_application(
        db_session,
        PrepareApplicationRequest(
            job_id=job_id,
            profile_id=profile_id,
            resume_id=resume_id,
        ),
    )

    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_cover_letter",
        lambda **_: "Regenerated cover letter",
    )
    review = regenerate_cover_letter(db_session, prepared.application_id)

    assert review.cover_letter == "Regenerated cover letter"
