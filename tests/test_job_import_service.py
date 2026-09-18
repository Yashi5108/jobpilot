from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.database import Base
from backend.schemas.job_import import ManualJobImportRequest
from backend.services.job_import_service import (
    import_jobs_from_csv,
    import_jobs_from_json,
    import_manual_job,
)


def _session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_job_import_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return local_session()


def test_manual_import_deduplicates_by_source_and_external_id(tmp_path: Path) -> None:
    db = _session(tmp_path)
    try:
        payload = ManualJobImportRequest(
            title="Backend Engineer",
            company="Acme",
            description="Build APIs",
            source_name="Indeed",
            source_type="feed",
            external_id="job-123",
        )

        first = import_manual_job(db, payload)
        second = import_manual_job(db, payload)

        assert first.imported_count == 1
        assert second.imported_count == 0
        assert second.skipped_count == 1
        assert second.records[0].status == "SKIPPED_DUPLICATE"
    finally:
        db.close()


def test_json_import_reports_import_and_skip(tmp_path: Path) -> None:
    db = _session(tmp_path)
    try:
        content = b"""[
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "description": "Build systems",
                "url": "https://example.com/jobs/platform"
            },
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "description": "Build systems",
                "url": "https://example.com/jobs/platform"
            }
        ]"""

        result = import_jobs_from_json(db, content)

        assert result.imported_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 0
    finally:
        db.close()


def test_csv_import_success(tmp_path: Path) -> None:
    db = _session(tmp_path)
    try:
        content = (
            "title,company,description,url,source_name,source_type,external_id\n"
            "Backend Engineer,Acme,Build APIs,https://example.com/jobs/1,Manual,manual,ext-1\n"
        ).encode("utf-8")

        result = import_jobs_from_csv(db, content)

        assert result.imported_count == 1
        assert result.skipped_count == 0
        assert result.failed_count == 0
    finally:
        db.close()
