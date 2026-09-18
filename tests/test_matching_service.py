from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.database.models import Job, JobMatch, Resume, UserProfile
from backend.schemas.job import JobCreate
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.resume import ResumeCreate
from backend.schemas.resume_analysis import CandidateProfile
from backend.services.job_service import create_job
from backend.services.matching_service import (
    MatchingServiceError,
    get_job_match_for_resume,
    get_job_matches,
    match_job_with_resume,
)
from backend.services.resume_service import create_resume


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_matching_service.db"
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


def _seed_profile(db_session: Session) -> int:
    profile = UserProfile(name="Matcher")
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile.id


def _seed_resume(db_session: Session, profile_id: int) -> Resume:
    resume = create_resume(
        db_session,
        ResumeCreate(
            profile_id=profile_id,
            name="Resume",
            file_path="data/resumes/resume.pdf",
            file_type="pdf",
        ),
    )
    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "skills": [{"name": "Python"}, {"name": "FastAPI"}],
            "experience": [
                {
                    "title": "Engineer",
                    "start_date": "2018-01",
                    "end_date": None,
                    "is_current": True,
                }
            ],
            "education": [{"degree": "Bachelor of Computer Science"}],
            "certifications": [{"name": "AWS Certified Solutions Architect"}],
            "projects": [],
            "achievements": [],
            "languages": [],
        }
    ).model_dump()
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _seed_job(db_session: Session) -> int:
    job = create_job(
        db_session,
        JobCreate(
            title="Backend Engineer",
            company="Acme",
            description="Need Python and FastAPI",
            url="https://example.com/jobs/backend",
        ),
    )
    job.analysis_status = "COMPLETED"
    job.analysis_result = JobAnalysis.model_validate(
        {
            "required_skills": [
                {"name": "Python", "category": "language"},
                {"name": "FastAPI", "category": "framework"},
            ],
            "preferred_skills": [{"name": "AWS", "category": "cloud"}],
            "minimum_years_experience": 3,
            "preferred_years_experience": None,
            "experience_requirements": [],
            "education_requirements": ["bachelor"],
            "required_certifications": ["AWS Certified Solutions Architect"],
            "preferred_certifications": [],
            "responsibilities": [],
            "domain_requirements": [],
            "communication_requirements": [],
            "leadership_requirements": [],
            "work_authorization_requirements": [],
            "travel_requirements": [],
            "other_requirements": [],
        }
    ).model_dump()
    db_session.add(job)
    db_session.commit()
    return job.id


def test_match_service_errors_for_missing_entities(db_session: Session) -> None:
    with pytest.raises(MatchingServiceError, match="Job not found"):
        match_job_with_resume(db_session, job_id=999, resume_id=1)

    profile_id = _seed_profile(db_session)
    _seed_job(db_session)
    create_resume(
        db_session,
        ResumeCreate(
            profile_id=profile_id,
            name="Resume",
            file_path="data/resumes/r.pdf",
        ),
    )

    with pytest.raises(MatchingServiceError, match="Resume not found"):
        match_job_with_resume(db_session, job_id=1, resume_id=999)


def test_match_service_requires_completed_analyses(db_session: Session) -> None:
    profile_id = _seed_profile(db_session)
    resume = create_resume(
        db_session,
        ResumeCreate(profile_id=profile_id, name="Resume", file_path="data/r.pdf"),
    )
    job_id = _seed_job(db_session)

    with pytest.raises(MatchingServiceError, match="Resume analysis is required"):
        match_job_with_resume(db_session, job_id=job_id, resume_id=resume.id)

    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "skills": [],
            "experience": [],
            "education": [],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
        }
    ).model_dump()
    db_session.add(resume)
    db_session.commit()

    job = db_session.get(Job, job_id)
    assert job is not None
    job.analysis_status = "NOT_ANALYZED"
    job.analysis_result = None
    db_session.add(job)
    db_session.commit()

    with pytest.raises(MatchingServiceError, match="Job analysis is required"):
        match_job_with_resume(db_session, job_id=job_id, resume_id=resume.id)


def test_match_service_success_and_rerun_updates_single_row(
    db_session: Session,
) -> None:
    profile_id = _seed_profile(db_session)
    resume = _seed_resume(db_session, profile_id)
    job_id = _seed_job(db_session)

    first = match_job_with_resume(db_session, job_id=job_id, resume_id=resume.id)
    second = match_job_with_resume(db_session, job_id=job_id, resume_id=resume.id)

    assert first.score == second.score
    assert second.matched_at >= first.matched_at

    rows = list(
        db_session.scalars(
            select(JobMatch).where(
                JobMatch.job_id == job_id,
                JobMatch.resume_id == resume.id,
            )
        ).all()
    )
    assert len(rows) == 1
    assert rows[0].match_score == float(second.score)

    loaded = get_job_match_for_resume(db_session, job_id=job_id, resume_id=resume.id)
    assert loaded.score == second.score

    listed = get_job_matches(db_session, job_id=job_id)
    assert len(listed) == 1


def test_match_service_invalid_stored_analysis(db_session: Session) -> None:
    profile_id = _seed_profile(db_session)
    resume = _seed_resume(db_session, profile_id)
    job_id = _seed_job(db_session)

    resume.analysis_result = {"skills": "not-a-list"}
    db_session.add(resume)
    db_session.commit()

    with pytest.raises(MatchingServiceError, match="Stored resume analysis is invalid"):
        match_job_with_resume(db_session, job_id=job_id, resume_id=resume.id)


def test_match_service_invalid_stored_job_analysis(db_session: Session) -> None:
    profile_id = _seed_profile(db_session)
    resume = _seed_resume(db_session, profile_id)
    job_id = _seed_job(db_session)

    job = db_session.get(Job, job_id)
    assert job is not None
    job.analysis_result = {"required_skills": "broken"}
    db_session.add(job)
    db_session.commit()

    with pytest.raises(MatchingServiceError, match="Stored job analysis is invalid"):
        match_job_with_resume(db_session, job_id=job_id, resume_id=resume.id)
