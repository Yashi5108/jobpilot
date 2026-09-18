from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.database.models import (
    Application,
    ApplicationStatus,
    Job,
    JobMatch,
    JobSource,
    Resume,
    UserProfile,
)
from backend.services.analytics_service import get_analytics_overview


def _session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_analytics_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return local_session()


def test_analytics_overview_counts_and_skills(tmp_path: Path) -> None:
    db = _session(tmp_path)
    try:
        profile = UserProfile(name="User")
        db.add(profile)
        db.flush()

        source = JobSource(name="manual", source_type="manual")
        db.add(source)
        db.flush()

        job = Job(source_id=source.id, title="Backend", company="Acme", description="D")
        db.add(job)
        db.flush()

        resume = Resume(profile_id=profile.id, name="Resume", file_path="resume.pdf")
        db.add(resume)
        db.flush()

        app = Application(
            job_id=job.id,
            profile_id=profile.id,
            resume_id=resume.id,
            status=ApplicationStatus.INTERVIEW,
        )
        db.add(app)

        match = JobMatch(
            job_id=job.id,
            profile_id=profile.id,
            resume_id=resume.id,
            match_score=80,
            matching_skills=["Python", "FastAPI"],
            missing_skills=["PostgreSQL"],
        )
        db.add(match)
        db.commit()

        overview = get_analytics_overview(db)

        assert overview.jobs_found == 1
        assert overview.applications == 1
        assert overview.interviews == 1
        assert overview.average_match_score is not None
        assert any(item.skill == "Python" for item in overview.top_matched_skills)
        assert any(
            item.skill == "PostgreSQL" for item in overview.frequently_missing_skills
        )
    finally:
        db.close()
