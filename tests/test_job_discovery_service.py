from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.database.models import Job, Resume, UserProfile
from backend.schemas.job_discovery import JobDiscoveryRequest
from backend.schemas.job_match import JobMatchResult
from backend.schemas.resume_analysis import CandidateProfile
from backend.services.job_discovery.base import JobDiscoveryConnectorError
from backend.services.job_discovery.models import (
    DiscoveredJob,
    DiscoverySearchCriteria,
)
from backend.services.job_discovery.service import (
    _build_connectors,
    build_search_criteria,
    deduplicate_discovered_jobs,
    discover_jobs_for_resume,
)


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_discovery_service.db"
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


def _seed_resume(db: Session) -> Resume:
    profile = UserProfile(
        name="Searcher",
        location="Bengaluru",
        remote_preference="remote",
        years_of_experience=6,
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
                "headline": "Senior Backend Engineer",
                "location": "Bengaluru",
                "skills": [
                    {"name": "Python"},
                    {"name": "FastAPI"},
                    {"name": "AWS"},
                ],
                "experience": [
                    {
                        "title": "Backend Engineer",
                        "start_date": "2018-01",
                        "is_current": True,
                    }
                ],
                "education": [],
                "projects": [],
                "certifications": [],
                "achievements": [],
                "languages": [],
            }
        ).model_dump(),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def _match_result(
    job_id: int, resume_id: int, profile_id: int, score: int = 88
) -> JobMatchResult:
    return JobMatchResult.model_validate(
        {
            "job_id": job_id,
            "resume_id": resume_id,
            "profile_id": profile_id,
            "score": score,
            "required_skill_score": 90,
            "preferred_skill_score": 80,
            "experience_score": 100,
            "education_score": None,
            "certification_score": None,
            "domain_score": None,
            "matched_required_skills": ["Python"],
            "missing_required_skills": [],
            "matched_preferred_skills": ["AWS"],
            "missing_preferred_skills": [],
            "matched_required_certifications": [],
            "missing_required_certifications": [],
            "matched_preferred_certifications": [],
            "missing_preferred_certifications": [],
            "experience_result": "MATCHED",
            "education_result": "NOT_REQUIRED",
            "certification_result": "NOT_REQUIRED",
            "domain_result": "NOT_REQUIRED",
            "strengths": ["Required skill matched: Python"],
            "gaps": [],
            "matched_at": datetime.now(UTC),
        }
    )


def test_build_search_criteria_uses_resume_and_profile() -> None:
    profile = UserProfile(
        location="Bengaluru",
        remote_preference="remote",
        years_of_experience=5,
    )
    resume_profile = CandidateProfile.model_validate(
        {
            "headline": "Backend Engineer",
            "skills": [{"name": "Python"}, {"name": "FastAPI"}],
            "experience": [
                {
                    "title": "Senior Engineer",
                    "start_date": "2019-01",
                    "is_current": True,
                }
            ],
            "education": [],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
        }
    )

    criteria = build_search_criteria(resume_profile, profile, 10)

    assert "Backend Engineer" in criteria.queries
    assert "Senior Engineer" in criteria.queries
    assert criteria.skills[:2] == ["Python", "FastAPI"]
    assert criteria.location == "Bengaluru"
    assert criteria.remote_preference == "remote"


def test_deduplicate_discovered_jobs_merges_multiple_sources() -> None:
    jobs = [
        DiscoveredJob(
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Build APIs",
            job_url="https://example.com/jobs/1?utm=source-a",
            source_name="source-a",
            source_type="feed",
        ),
        DiscoveredJob(
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Build APIs",
            job_url="https://example.com/jobs/1?utm=source-b",
            source_name="source-b",
            source_type="api",
        ),
    ]

    deduplicated = deduplicate_discovered_jobs(jobs)

    assert len(deduplicated) == 1
    assert len(deduplicated[0].discovered_sources) == 2


def test_deduplicate_discovered_jobs_merges_same_url_across_queries() -> None:
    jobs = [
        DiscoveredJob(
            title="Senior Backend Engineer",
            company="Acme",
            location="Remote",
            description="Query one",
            job_url="https://jobs.acme.com/roles/123",
            source_name="web_search",
            source_type="search_result",
        ),
        DiscoveredJob(
            title="Senior Backend Engineer",
            company="Acme",
            location="Remote",
            description="Query two",
            job_url="https://jobs.acme.com/roles/123",
            source_name="web_search",
            source_type="search_result",
        ),
    ]

    deduplicated = deduplicate_discovered_jobs(jobs)

    assert len(deduplicated) == 1
    assert len(deduplicated[0].discovered_links) == 1


def test_deduplicate_discovered_jobs_ignores_tracking_parameters() -> None:
    jobs = [
        DiscoveredJob(
            title="Senior Backend Engineer",
            company="Acme",
            location="Remote",
            description="Tracked URL A",
            job_url="https://jobs.acme.com/roles/123?utm_source=google&ref=abc",
            source_name="web_search",
            source_type="search_result",
        ),
        DiscoveredJob(
            title="Senior Backend Engineer",
            company="Acme",
            location="Remote",
            description="Tracked URL B",
            job_url="https://jobs.acme.com/roles/123?utm_source=bing",
            source_name="remotive",
            source_type="public_api",
        ),
    ]

    deduplicated = deduplicate_discovered_jobs(jobs)

    assert len(deduplicated) == 1
    assert len(deduplicated[0].discovered_sources) == 2
    assert len(deduplicated[0].discovered_links) == 2


def test_deduplicate_discovered_jobs_merges_same_company_title_location() -> None:
    jobs = [
        DiscoveredJob(
            title="Sr. Backend Engineer",
            company="Acme   Corp",
            location=" Bengaluru ",
            description="Description A",
            job_url=None,
            source_name="web_search",
            source_type="search_result",
        ),
        DiscoveredJob(
            title="Senior Backend Engineer",
            company="acme corp",
            location="bengaluru",
            description="Description B",
            job_url=None,
            source_name="remotive",
            source_type="public_api",
        ),
    ]

    deduplicated = deduplicate_discovered_jobs(jobs)

    assert len(deduplicated) == 1
    assert len(deduplicated[0].discovered_sources) == 2


def test_deduplicate_discovered_jobs_keeps_distinct_similar_titles() -> None:
    jobs = [
        DiscoveredJob(
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Platform team",
            job_url=None,
            source_name="web_search",
            source_type="search_result",
        ),
        DiscoveredJob(
            title="Backend Engineering Manager",
            company="Acme",
            location="Remote",
            description="Manager role",
            job_url=None,
            source_name="remotive",
            source_type="public_api",
        ),
    ]

    deduplicated = deduplicate_discovered_jobs(jobs)

    assert len(deduplicated) == 2


def test_discover_jobs_preserves_merged_source_links(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = _seed_resume(db_session)

    class _Connector:
        source_name = "web_search"
        source_type = "search_result"

        def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
            return [
                DiscoveredJob(
                    title="Senior Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="First description",
                    job_url="https://jobs.acme.com/roles/123?utm_source=google",
                    source_name="web_search",
                    source_type="search_result",
                ),
                DiscoveredJob(
                    title="Senior Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="Second description",
                    job_url="https://jobs.acme.com/roles/123?utm_source=bing",
                    source_name="remotive",
                    source_type="public_api",
                ),
            ]

    monkeypatch.setattr(
        "backend.services.job_discovery.service._build_connectors",
        lambda payload: [_Connector()],
    )
    monkeypatch.setattr(
        "backend.services.job_discovery.service.analyze_job",
        lambda db, job_id, force=False: _fake_completed_job(db, job_id),
    )
    monkeypatch.setattr(
        "backend.services.job_discovery.service.match_job_with_resume",
        lambda db, job_id, resume_id: _match_result(
            job_id,
            resume_id,
            resume.profile_id,
        ),
    )

    response = discover_jobs_for_resume(
        db_session,
        JobDiscoveryRequest(resume_id=resume.id, sources=["web_search"]),
    )

    assert response.total_discovered == 2
    assert response.total_deduplicated == 1
    assert len(response.results) == 1
    assert len(response.results[0].discovered_sources) == 2
    assert len(response.results[0].discovered_links) == 2
    assert response.results[0].discovered_links[0].job_url is not None


def test_discover_jobs_matches_and_marks_open_apply(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = _seed_resume(db_session)

    class _Connector:
        source_name = "remotive"
        source_type = "public_api"

        def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
            assert criteria.queries
            return [
                DiscoveredJob(
                    title="Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="Need Python and FastAPI",
                    job_url="https://example.com/jobs/backend",
                    source_name="remotive",
                    source_type="public_api",
                )
            ]

    monkeypatch.setattr(
        "backend.services.job_discovery.service._build_connectors",
        lambda payload: [_Connector()],
    )

    def _fake_analyze(db: Session, job_id: int, force: bool = False):
        job = db.get(Job, job_id)
        assert job is not None
        job.analysis_status = "COMPLETED"
        job.analysis_result = {
            "required_skills": [{"name": "Python", "category": "language"}],
            "preferred_skills": [],
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
        db.add(job)
        db.commit()
        db.refresh(job)
        return job, None

    monkeypatch.setattr(
        "backend.services.job_discovery.service.analyze_job",
        _fake_analyze,
    )
    monkeypatch.setattr(
        "backend.services.job_discovery.service.match_job_with_resume",
        lambda db, job_id, resume_id: _match_result(
            job_id,
            resume_id,
            resume.profile_id,
        ),
    )

    response = discover_jobs_for_resume(
        db_session,
        JobDiscoveryRequest(resume_id=resume.id, sources=["remotive"]),
    )

    assert response.total_discovered == 1
    assert response.total_matched == 1
    assert response.results[0].action == "OPEN_AND_APPLY"
    assert response.results[0].match_score == 88


def test_discover_jobs_apply_action_requires_supported_connector(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = _seed_resume(db_session)

    class _Connector:
        source_name = "authorized-ats"
        source_type = "authorized_api"

        def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
            return [
                DiscoveredJob(
                    title="Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="Need Python",
                    job_url="https://authorized.example/apply/123",
                    source_name="authorized-ats",
                    source_type="authorized_api",
                    supports_apply=True,
                )
            ]

    monkeypatch.setattr(
        "backend.services.job_discovery.service._build_connectors",
        lambda payload: [_Connector()],
    )
    monkeypatch.setattr(
        "backend.services.job_discovery.service.analyze_job",
        lambda db, job_id, force=False: _fake_completed_job(db, job_id),
    )
    monkeypatch.setattr(
        "backend.services.job_discovery.service.match_job_with_resume",
        lambda db, job_id, resume_id: _match_result(
            job_id,
            resume_id,
            resume.profile_id,
            score=91,
        ),
    )

    response = discover_jobs_for_resume(
        db_session,
        JobDiscoveryRequest(resume_id=resume.id, sources=["authorized-ats"]),
    )

    assert response.results[0].action == "APPLY"


def test_discover_jobs_reports_connector_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = _seed_resume(db_session)

    class _BrokenConnector:
        source_name = "remotive"
        source_type = "public_api"

        def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
            raise JobDiscoveryConnectorError("temporarily unavailable")

    monkeypatch.setattr(
        "backend.services.job_discovery.service._build_connectors",
        lambda payload: [_BrokenConnector()],
    )

    response = discover_jobs_for_resume(
        db_session,
        JobDiscoveryRequest(resume_id=resume.id, sources=["remotive"]),
    )

    assert response.total_discovered == 0
    assert response.total_matched == 0
    assert len(response.errors) == 1
    assert response.errors[0].source == "remotive"


def test_build_connectors_supports_web_search_source() -> None:
    connectors = _build_connectors(
        JobDiscoveryRequest(resume_id=1, sources=["remotive", "web_search"])
    )

    connector_names = [item.source_name for item in connectors]
    assert connector_names == ["remotive", "web_search"]


def _fake_completed_job(db: Session, job_id: int):
    job = db.get(Job, job_id)
    assert job is not None
    job.analysis_status = "COMPLETED"
    job.analysis_result = {
        "required_skills": [{"name": "Python", "category": "language"}],
        "preferred_skills": [],
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
    db.add(job)
    db.commit()
    db.refresh(job)
    return job, None
