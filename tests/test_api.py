from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.ai.ollama_client import OllamaClientError
from backend.ai.resume_analyzer import ResumeAnalysisError
from backend.core.config import get_settings
from backend.database.database import Base, get_db
from backend.database.models import (
    Application,
    ApplicationEvent,
    ApplicationQuestion,
    ApplicationStatus,
    Job,
    JobMatch,
    JobSource,
    QuestionStatus,
    Resume,
    UserProfile,
)
from backend.main import app
from backend.schemas.job_analysis import JobAnalysis
from backend.schemas.resume_analysis import CandidateProfile


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "jobpilot_api_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    local_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = local_session()

    def override_get_db() -> Awaitable[Session]:
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def _run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


async def _asgi_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    path_only, _, query = path.partition("?")
    body = raw_body or b""
    headers: list[tuple[bytes, bytes]] = []
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers.append((b"content-type", b"application/json"))
    if extra_headers:
        for key, value in extra_headers.items():
            headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path_only,
        "raw_path": path_only.encode("utf-8"),
        "query_string": query.encode("utf-8"),
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)

    start = next(msg for msg in messages if msg["type"] == "http.response.start")
    status_code = int(start["status"])
    response_headers = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }

    body_chunks = [
        msg.get("body", b"") for msg in messages if msg["type"] == "http.response.body"
    ]
    response_body = b"".join(body_chunks)

    parsed_body: dict[str, Any] = {}
    if response_body:
        parsed_body = json.loads(response_body.decode("utf-8"))

    return status_code, parsed_body, response_headers


def test_health_endpoints(db_session: Session) -> None:
    status_code, payload, _ = _run(_asgi_request("GET", "/health"))
    assert status_code == 200
    assert payload["status"] == "ok"

    v1_status_code, v1_payload, _ = _run(_asgi_request("GET", "/api/v1/health"))
    assert v1_status_code == 200
    assert v1_payload["database"] == "connected"


def _build_pdf_with_text(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("utf-8")

    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        4: b"<< /Length "
        + str(len(stream)).encode("utf-8")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    output = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in range(1, 6):
        offsets[obj_id] = len(output)
        output.extend(f"{obj_id} 0 obj\n".encode("utf-8"))
        output.extend(objects[obj_id])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(b"xref\n0 6\n")
    output.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, 6):
        output.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("utf-8"))

    output.extend(
        (
            f"trailer\n<< /Size 6 /Root 1 0 R >>\n" f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("utf-8")
    )
    return bytes(output)


def _build_multipart_body(
    profile_id: int,
    filename: str,
    content: bytes,
    content_type: str,
    boundary: str,
) -> bytes:
    lines = [
        f"--{boundary}".encode("utf-8"),
        b'Content-Disposition: form-data; name="profile_id"',
        b"",
        str(profile_id).encode("utf-8"),
        f"--{boundary}".encode("utf-8"),
        (f'Content-Disposition: form-data; name="file"; filename="{filename}"').encode(
            "utf-8"
        ),
        f"Content-Type: {content_type}".encode("utf-8"),
        b"",
        content,
        f"--{boundary}--".encode("utf-8"),
        b"",
    ]
    return b"\r\n".join(lines)


def test_profile_create_read_update(db_session: Session) -> None:
    not_found_status, _, _ = _run(_asgi_request("GET", "/api/v1/profile"))
    assert not_found_status == 404

    create_payload = {
        "name": "Yashi",
        "email": "yashi@example.test",
        "location": "Bengaluru",
    }
    create_status, created, _ = _run(
        _asgi_request("POST", "/api/v1/profile", create_payload)
    )
    assert create_status == 201
    assert created["name"] == "Yashi"

    read_status, profile, _ = _run(_asgi_request("GET", "/api/v1/profile"))
    assert read_status == 200
    assert profile["email"] == "yashi@example.test"

    update_status, updated, _ = _run(
        _asgi_request("PUT", "/api/v1/profile", {"location": "Remote"})
    )
    assert update_status == 200
    assert updated["location"] == "Remote"


def test_resume_list_retrieve_and_404(db_session: Session) -> None:
    _, created_profile, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Resume User"})
    )

    create_resume_payload = {
        "profile_id": created_profile["id"],
        "name": "Primary Resume",
        "file_path": "data/resumes/primary.pdf",
        "file_type": "pdf",
    }
    create_status, resume, _ = _run(
        _asgi_request("POST", "/api/v1/resumes", create_resume_payload)
    )
    assert create_status == 201

    list_status, resumes, _ = _run(_asgi_request("GET", "/api/v1/resumes"))
    assert list_status == 200
    assert len(resumes) == 1
    assert resumes[0]["name"] == "Primary Resume"

    get_status, fetched_resume, _ = _run(
        _asgi_request("GET", f"/api/v1/resumes/{resume['id']}")
    )
    assert get_status == 200
    assert fetched_resume["file_type"] == "pdf"

    missing_status, missing_payload, _ = _run(
        _asgi_request("GET", "/api/v1/resumes/9999")
    )
    assert missing_status == 404
    assert missing_payload["detail"] == "Resume not found"


def test_resume_upload_pdf_and_read_text(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path / "resumes"))
    monkeypatch.setenv("RESUME_UPLOAD_MAX_BYTES", "10485760")
    get_settings.cache_clear()

    try:
        _, profile, _ = _run(
            _asgi_request("POST", "/api/v1/profile", {"name": "Yashi"})
        )

        boundary = "test-boundary"
        body = _build_multipart_body(
            profile_id=profile["id"],
            filename="resume.pdf",
            content=_build_pdf_with_text("Backend Engineer Python FastAPI"),
            content_type="application/pdf",
            boundary=boundary,
        )

        upload_status, upload_payload, _ = _run(
            _asgi_request(
                "POST",
                "/api/v1/resumes/upload",
                raw_body=body,
                extra_headers={
                    "content-type": f"multipart/form-data; boundary={boundary}"
                },
            )
        )
        assert upload_status == 201
        assert upload_payload["parse_status"] == "PARSED"
        assert "Backend Engineer" in upload_payload["text_preview"]

        list_status, resumes, _ = _run(_asgi_request("GET", "/api/v1/resumes"))
        assert list_status == 200
        assert len(resumes) == 1
        assert resumes[0]["file_type"] == "pdf"

        text_status, text_payload, _ = _run(
            _asgi_request("GET", f"/api/v1/resumes/{upload_payload['id']}/text")
        )
        assert text_status == 200
        assert "FastAPI" in text_payload["normalized_text"]

        stored_file = tmp_path / "resumes"
        assert len(list(stored_file.glob("*.pdf"))) == 1
    finally:
        get_settings.cache_clear()


def test_resume_upload_rejects_unsupported_and_corrupted(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path / "resumes"))
    monkeypatch.setenv("RESUME_UPLOAD_MAX_BYTES", "10485760")
    get_settings.cache_clear()

    try:
        _, profile, _ = _run(_asgi_request("POST", "/api/v1/profile", {"name": "Y"}))

        unsupported_boundary = "unsupported"
        unsupported_body = _build_multipart_body(
            profile_id=profile["id"],
            filename="resume.txt",
            content=b"hello",
            content_type="text/plain",
            boundary=unsupported_boundary,
        )

        unsupported_status, unsupported_payload, _ = _run(
            _asgi_request(
                "POST",
                "/api/v1/resumes/upload",
                raw_body=unsupported_body,
                extra_headers={
                    "content-type": (
                        f"multipart/form-data; boundary={unsupported_boundary}"
                    )
                },
            )
        )
        assert unsupported_status == 415
        assert "Unsupported file type" in unsupported_payload["detail"]

        corrupted_boundary = "corrupted"
        corrupted_body = _build_multipart_body(
            profile_id=profile["id"],
            filename="resume.pdf",
            content=b"%PDF-not-valid",
            content_type="application/pdf",
            boundary=corrupted_boundary,
        )
        corrupted_status, corrupted_payload, _ = _run(
            _asgi_request(
                "POST",
                "/api/v1/resumes/upload",
                raw_body=corrupted_body,
                extra_headers={
                    "content-type": (
                        f"multipart/form-data; boundary={corrupted_boundary}"
                    )
                },
            )
        )
        assert corrupted_status == 422
        assert "Invalid or corrupted PDF" in corrupted_payload["detail"]
    finally:
        get_settings.cache_clear()


def test_job_create_retrieve_and_validation(db_session: Session) -> None:
    create_payload = {
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Bengaluru",
        "url": "https://example.com/jobs/backend-engineer",
        "employment_type": "Full-time",
        "description": "Build backend APIs and review code.",
    }
    create_status, created_job, _ = _run(
        _asgi_request("POST", "/api/v1/jobs", create_payload)
    )
    assert create_status == 201
    assert created_job["title"] == "Backend Engineer"
    assert created_job["source"]["source_type"] == "manual"

    list_status, jobs, _ = _run(_asgi_request("GET", "/api/v1/jobs"))
    assert list_status == 200
    assert len(jobs) == 1

    get_status, job, _ = _run(_asgi_request("GET", f"/api/v1/jobs/{created_job['id']}"))
    assert get_status == 200
    assert job["company"] == "Acme"
    assert job["description"] == "Build backend APIs and review code."

    invalid_status, _, _ = _run(
        _asgi_request("POST", "/api/v1/jobs", {"title": "Invalid Job"})
    )
    assert invalid_status == 422


def test_job_duplicate_url_update_delete_and_filter(db_session: Session) -> None:
    first_payload = {
        "title": "Senior Backend Engineer",
        "company": "Example Technologies",
        "location": "Bengaluru, India",
        "url": "https://example.com/jobs/senior-backend-engineer",
        "employment_type": "Full-time",
        "description": "Design and build backend services.",
    }
    create_status, created_job, _ = _run(
        _asgi_request("POST", "/api/v1/jobs", first_payload)
    )
    assert create_status == 201

    duplicate_status, duplicate_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Another role",
                "company": "Example Technologies",
                "url": "https://example.com/jobs/senior-backend-engineer",
                "description": "Same URL should conflict",
            },
        )
    )
    assert duplicate_status == 409
    assert "already exists" in duplicate_payload["detail"]

    invalid_url_status, _, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Bad URL Role",
                "company": "Example Technologies",
                "url": "javascript:alert(1)",
                "description": "bad url",
            },
        )
    )
    assert invalid_url_status == 422

    no_url_status, no_url_job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Role without URL",
                "company": "Example Technologies",
                "description": "URL optional role",
            },
        )
    )
    assert no_url_status == 201
    assert no_url_job["url"] is None

    update_status, updated_job, _ = _run(
        _asgi_request(
            "PUT",
            f"/api/v1/jobs/{created_job['id']}",
            {
                "title": "Principal Backend Engineer",
                "company": "Example Technologies",
                "location": "Remote",
                "url": "https://example.com/jobs/principal-backend-engineer",
                "employment_type": "Contract",
                "description": "Updated role details.",
            },
        )
    )
    assert update_status == 200
    assert updated_job["title"] == "Principal Backend Engineer"

    filter_status, filtered_jobs, _ = _run(
        _asgi_request("GET", "/api/v1/jobs?company=example%20technologies")
    )
    assert filter_status == 200
    assert len(filtered_jobs) == 2

    delete_status, _, _ = _run(
        _asgi_request("DELETE", f"/api/v1/jobs/{created_job['id']}")
    )
    assert delete_status == 204

    missing_status, _, _ = _run(
        _asgi_request("GET", f"/api/v1/jobs/{created_job['id']}")
    )
    assert missing_status == 404


def test_job_manual_import_endpoint(db_session: Session) -> None:
    import_status, import_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/import/manual",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Build APIs",
                "url": "https://example.com/jobs/backend-engineer",
                "source_name": "manual",
                "source_type": "manual",
            },
        )
    )
    assert import_status == 200
    assert import_payload["imported_count"] == 1
    assert import_payload["skipped_count"] == 0

    duplicate_status, duplicate_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/import/manual",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Build APIs",
                "url": "https://example.com/jobs/backend-engineer",
                "source_name": "manual",
                "source_type": "manual",
            },
        )
    )
    assert duplicate_status == 200
    assert duplicate_payload["imported_count"] == 0
    assert duplicate_payload["skipped_count"] == 1


def test_job_structured_import_endpoints(db_session: Session) -> None:
    json_body = b"""[
        {
            \"title\": \"Data Engineer\",
            \"company\": \"Acme\",
            \"description\": \"Build ETL\",
            \"url\": \"https://example.com/jobs/data-engineer\"
        }
    ]"""
    json_boundary = "json-import-boundary"
    json_multipart = _build_multipart_body(
        profile_id=1,
        filename="jobs.json",
        content=json_body,
        content_type="application/json",
        boundary=json_boundary,
    )

    json_status, json_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/import/json",
            raw_body=json_multipart,
            extra_headers={
                "content-type": f"multipart/form-data; boundary={json_boundary}"
            },
        )
    )
    assert json_status == 200
    assert json_payload["imported_count"] == 1

    csv_content = (
        "title,company,description,url,source_name,source_type,external_id\n"
        "Platform Engineer,Acme,Build systems,https://example.com/jobs/platform,CSV,csv,ext-123\n"
    ).encode("utf-8")
    csv_boundary = "csv-import-boundary"
    csv_multipart = _build_multipart_body(
        profile_id=1,
        filename="jobs.csv",
        content=csv_content,
        content_type="text/csv",
        boundary=csv_boundary,
    )

    csv_status, csv_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/import/csv",
            raw_body=csv_multipart,
            extra_headers={
                "content-type": f"multipart/form-data; boundary={csv_boundary}"
            },
        )
    )
    assert csv_status == 200
    assert csv_payload["imported_count"] == 1


def test_job_discovery_endpoint(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, profile_payload, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Discovery User"})
    )

    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Resume",
                "file_path": "data/resumes/r.pdf",
            },
        )
    )

    resume = db_session.get(Resume, resume_payload["id"])
    assert resume is not None
    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "headline": "Backend Engineer",
            "skills": [{"name": "Python"}],
            "experience": [
                {
                    "title": "Backend Engineer",
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
    ).model_dump()
    db_session.add(resume)
    db_session.commit()

    class _Connector:
        source_name = "remotive"
        source_type = "public_api"

        def search(self, criteria: object) -> list[object]:
            from backend.services.job_discovery.models import DiscoveredJob

            return [
                DiscoveredJob(
                    title="Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="Need Python",
                    job_url="https://example.com/jobs/backend-engineer",
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
        job.analysis_result = JobAnalysis.model_validate(
            {
                "required_skills": [{"name": "Python", "category": "language"}],
                "preferred_skills": [],
                "minimum_years_experience": 1,
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
        ).model_dump()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job, JobAnalysis.model_validate(job.analysis_result)

    monkeypatch.setattr(
        "backend.services.job_discovery.service.analyze_job",
        _fake_analyze,
    )

    discover_status, discover_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/discover",
            {
                "resume_id": resume_payload["id"],
                "sources": ["remotive"],
                "max_results_per_source": 5,
            },
        )
    )
    assert discover_status == 200
    assert discover_payload["total_discovered"] == 1
    assert discover_payload["total_matched"] == 1
    assert discover_payload["results"][0]["action"] == "OPEN_AND_APPLY"


def test_job_delete_rejected_when_application_exists(db_session: Session) -> None:
    _, profile, _ = _run(_asgi_request("POST", "/api/v1/profile", {"name": "P"}))

    _, job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "description": "Build systems",
                "url": "https://example.com/jobs/platform-engineer",
            },
        )
    )

    _, resume, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile["id"],
                "name": "Resume A",
                "file_path": "data/resumes/resume_a.pdf",
            },
        )
    )

    created_status, _, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/applications",
            {
                "job_id": job["id"],
                "profile_id": profile["id"],
                "resume_id": resume["id"],
            },
        )
    )
    assert created_status == 201

    delete_status, delete_payload, _ = _run(
        _asgi_request("DELETE", f"/api/v1/jobs/{job['id']}")
    )
    assert delete_status == 409
    assert "application history" in delete_payload["detail"].lower()


def test_application_create_retrieve_and_status_update(db_session: Session) -> None:
    _, profile, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Applicant"})
    )

    _, job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "description": "Build platform services",
            },
        )
    )

    _, resume, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile["id"],
                "name": "Resume A",
                "file_path": "data/resumes/resume_a.pdf",
            },
        )
    )

    create_status, application, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/applications",
            {
                "job_id": job["id"],
                "profile_id": profile["id"],
                "resume_id": resume["id"],
            },
        )
    )
    assert create_status == 201
    assert application["status"] == "DISCOVERED"

    get_status, fetched_application, _ = _run(
        _asgi_request("GET", f"/api/v1/applications/{application['id']}")
    )
    assert get_status == 200
    assert fetched_application["profile_id"] == profile["id"]

    patch_status, patched_application, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{application['id']}/status",
            {"status": "SHORTLISTED"},
        )
    )
    assert patch_status == 200
    assert patched_application["status"] == "SHORTLISTED"


def test_application_applied_requires_explicit_approval_and_confirmation(
    db_session: Session,
) -> None:
    _, profile, _ = _run(_asgi_request("POST", "/api/v1/profile", {"name": "A"}))
    _, job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Build APIs",
            },
        )
    )
    _, resume, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile["id"],
                "name": "R",
                "file_path": "data/resumes/r.pdf",
            },
        )
    )
    _, app, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/applications",
            {
                "job_id": job["id"],
                "profile_id": profile["id"],
                "resume_id": resume["id"],
            },
        )
    )

    _, _, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{app['id']}/status",
            {"status": "SHORTLISTED"},
        )
    )
    _, _, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{app['id']}/status",
            {"status": "PREPARING"},
        )
    )
    ready_status, ready_payload, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{app['id']}/status",
            {"status": "READY_FOR_REVIEW"},
        )
    )
    assert ready_status == 200
    assert ready_payload["status"] == "READY_FOR_REVIEW"

    blocked_status, blocked_payload, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{app['id']}/status",
            {"status": "APPLIED"},
        )
    )
    assert blocked_status == 409
    assert "submit confirmation" in blocked_payload["detail"].lower()

    approve_status, _, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{app['id']}/approve",
            {"approve": True},
        )
    )
    assert approve_status == 200

    submit_status, submit_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{app['id']}/submit-confirmation",
            {"confirm": True},
        )
    )
    assert submit_status == 200
    assert submit_payload["status"] == "APPLIED"


def test_application_prepare_review_browser_and_analytics(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_cover_letter",
        lambda **_: "Draft cover letter",
    )
    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_screening_answer",
        lambda **_: ("Draft answer", QuestionStatus.DRAFT),
    )

    _, profile_payload, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Matcher"})
    )

    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Resume",
                "file_path": "data/resumes/r.pdf",
            },
        )
    )

    resume = db_session.get(Resume, resume_payload["id"])
    assert resume is not None
    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "skills": [{"name": "Python"}],
            "experience": [{"start_date": "2018-01", "is_current": True}],
            "education": [],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
        }
    ).model_dump()
    db_session.add(resume)

    _, job_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Need Python",
            },
        )
    )
    job = db_session.get(Job, job_payload["id"])
    assert job is not None
    job.analysis_status = "COMPLETED"
    job.analysis_result = JobAnalysis.model_validate(
        {
            "required_skills": [{"name": "Python", "category": "language"}],
            "preferred_skills": [],
            "minimum_years_experience": 1,
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
    ).model_dump()
    db_session.add(job)
    db_session.commit()

    prep_status, prep_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/applications/prepare",
            {
                "job_id": job_payload["id"],
                "profile_id": profile_payload["id"],
                "resume_id": resume_payload["id"],
            },
        )
    )
    assert prep_status == 200
    app_id = prep_payload["application_id"]

    review_status, review_payload, _ = _run(
        _asgi_request("GET", f"/api/v1/applications/{app_id}/review")
    )
    assert review_status == 200
    assert review_payload["status"] == "READY_FOR_REVIEW"
    assert review_payload["cover_letter_status"] == "DRAFT"

    blocked_approve_status, blocked_approve_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{app_id}/approve",
            {"approve": True},
        )
    )
    assert blocked_approve_status == 409
    assert "approved" in blocked_approve_payload["detail"].lower()

    review_update_status, review_update_payload, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{app_id}/review",
            {
                "cover_letter": "Reviewed cover letter",
                "cover_letter_status": "APPROVED",
                "screening_answers": [
                    {
                        "id": review_payload["screening_answers"][0]["id"],
                        "answer": "Reviewed answer",
                        "status": "APPROVED",
                    }
                ],
            },
        )
    )
    assert review_update_status == 200
    assert review_update_payload["cover_letter_status"] == "APPROVED"
    assert review_update_payload["screening_answers"][0]["status"] == "APPROVED"

    browser_status, browser_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{app_id}/browser-assist",
            {
                "application_url": "https://example.com/jobs/backend-engineer/apply",
                "dry_run": True,
                "fields": [
                    {
                        "name": "email",
                        "label": "Email",
                        "field_type": "email",
                        "required": True,
                    }
                ],
            },
        )
    )
    assert browser_status == 200
    assert browser_payload["requires_human_submit"] is True

    tracker_status, tracker_payload, _ = _run(
        _asgi_request("GET", "/api/v1/applications/tracker")
    )
    assert tracker_status == 200
    assert len(tracker_payload) == 1
    assert len(tracker_payload[0]["events"]) >= 1
    discovered_events = [
        item
        for item in tracker_payload[0]["events"]
        if item["event_type"] == "DISCOVERED"
    ]
    assert len(discovered_events) == 1

    filtered_tracker_status, filtered_tracker_payload, _ = _run(
        _asgi_request(
            "GET",
            "/api/v1/applications/tracker?status=READY_FOR_REVIEW&company=Acme",
        )
    )
    assert filtered_tracker_status == 200
    assert len(filtered_tracker_payload) == 1

    empty_tracker_status, empty_tracker_payload, _ = _run(
        _asgi_request(
            "GET",
            "/api/v1/applications/tracker?status=APPLIED&company=Other",
        )
    )
    assert empty_tracker_status == 200
    assert empty_tracker_payload == []

    analytics_status, analytics_payload, _ = _run(
        _asgi_request("GET", "/api/v1/analytics/overview")
    )
    assert analytics_status == 200
    assert analytics_payload["jobs_found"] >= 1


def test_application_404_and_validation(db_session: Session) -> None:
    missing_status, missing_payload, _ = _run(
        _asgi_request("GET", "/api/v1/applications/9999")
    )
    assert missing_status == 404
    assert missing_payload["detail"] == "Application not found"

    invalid_patch_status, _, _ = _run(
        _asgi_request(
            "PATCH",
            "/api/v1/applications/9999/status",
            {"status": "INVALID_STATUS"},
        )
    )
    assert invalid_patch_status == 422


def test_resume_analysis_success_and_retrieve(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path / "resumes"))
    monkeypatch.setenv("RESUME_UPLOAD_MAX_BYTES", "10485760")
    get_settings.cache_clear()

    def _fake_analyze(_: str) -> CandidateProfile:
        return CandidateProfile(
            name="Jane Doe",
            headline="Software Engineer",
            skills=[
                {
                    "name": "Python",
                    "category": "programming_language",
                },
                {"name": "FastAPI", "category": "framework"},
            ],
            experience=[{"company": "Example Corp", "title": "Engineer"}],
        )

    monkeypatch.setattr(
        "backend.services.resume_analysis_service.analyze_resume_text", _fake_analyze
    )

    try:
        _, profile, _ = _run(
            _asgi_request("POST", "/api/v1/profile", {"name": "Analyzer"})
        )

        boundary = "analyze-boundary"
        body = _build_multipart_body(
            profile_id=profile["id"],
            filename="resume.pdf",
            content=_build_pdf_with_text("Jane Doe Python FastAPI"),
            content_type="application/pdf",
            boundary=boundary,
        )

        upload_status, upload_payload, _ = _run(
            _asgi_request(
                "POST",
                "/api/v1/resumes/upload",
                raw_body=body,
                extra_headers={
                    "content-type": f"multipart/form-data; boundary={boundary}"
                },
            )
        )
        assert upload_status == 201

        analyze_status, analyze_payload, _ = _run(
            _asgi_request(
                "POST",
                f"/api/v1/resumes/{upload_payload['id']}/analyze",
            )
        )
        assert analyze_status == 200
        assert analyze_payload["analysis_status"] == "COMPLETED"
        assert analyze_payload["profile"]["name"] == "Jane Doe"

        get_analysis_status, get_analysis_payload, _ = _run(
            _asgi_request(
                "GET",
                f"/api/v1/resumes/{upload_payload['id']}/analysis",
            )
        )
        assert get_analysis_status == 200
        assert get_analysis_payload["analysis_status"] == "COMPLETED"
        assert len(get_analysis_payload["profile"]["skills"]) == 2
    finally:
        get_settings.cache_clear()


def test_resume_analysis_missing_resume_and_missing_text(
    db_session: Session,
) -> None:
    missing_status, missing_payload, _ = _run(
        _asgi_request("POST", "/api/v1/resumes/999/analyze")
    )
    assert missing_status == 404
    assert missing_payload["detail"] == "Resume not found"

    _, profile, _ = _run(_asgi_request("POST", "/api/v1/profile", {"name": "A"}))
    create_status, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile["id"],
                "name": "Meta",
                "file_path": "data/resumes/meta.pdf",
                "file_type": "pdf",
            },
        )
    )
    assert create_status == 201

    no_text_status, no_text_payload, _ = _run(
        _asgi_request("POST", f"/api/v1/resumes/{resume_payload['id']}/analyze")
    )
    assert no_text_status == 422
    assert "no parsed text" in no_text_payload["detail"].lower()


def test_resume_analysis_failure_marks_failed_status(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path / "resumes"))
    monkeypatch.setenv("RESUME_UPLOAD_MAX_BYTES", "10485760")
    get_settings.cache_clear()

    def _fail_analyze(_: str) -> CandidateProfile:
        raise ResumeAnalysisError(
            "Ollama is not available. Start Ollama and try again.",
            status_code=503,
        )

    monkeypatch.setattr(
        "backend.services.resume_analysis_service.analyze_resume_text", _fail_analyze
    )

    try:
        _, profile, _ = _run(
            _asgi_request("POST", "/api/v1/profile", {"name": "Analyzer"})
        )
        boundary = "analyze-failed-boundary"
        body = _build_multipart_body(
            profile_id=profile["id"],
            filename="resume.pdf",
            content=_build_pdf_with_text("Jane Doe Python FastAPI"),
            content_type="application/pdf",
            boundary=boundary,
        )

        upload_status, upload_payload, _ = _run(
            _asgi_request(
                "POST",
                "/api/v1/resumes/upload",
                raw_body=body,
                extra_headers={
                    "content-type": (f"multipart/form-data; boundary={boundary}")
                },
            )
        )
        assert upload_status == 201

        analyze_status, analyze_payload, _ = _run(
            _asgi_request("POST", f"/api/v1/resumes/{upload_payload['id']}/analyze")
        )
        assert analyze_status == 503
        assert "Ollama is not available" in analyze_payload["detail"]

        get_analysis_status, get_analysis_payload, _ = _run(
            _asgi_request("GET", f"/api/v1/resumes/{upload_payload['id']}/analysis")
        )
        assert get_analysis_status == 200
        assert get_analysis_payload["analysis_status"] == "FAILED"
        assert get_analysis_payload["profile"] is None
    finally:
        get_settings.cache_clear()


def test_job_analysis_success_and_retrieve(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_analyze(_: str) -> JobAnalysis:
        return JobAnalysis.model_validate(
            {
                "role_summary": "Build backend APIs",
                "seniority_level": "Senior",
                "employment_type": "Full-time",
                "work_arrangement": "Hybrid",
                "location": "Bengaluru",
                "required_skills": [
                    {"name": "Python", "category": "language"},
                    {"name": "FastAPI", "category": "framework"},
                ],
                "preferred_skills": [{"name": "AWS", "category": "cloud"}],
                "minimum_years_experience": 5,
                "preferred_years_experience": None,
                "experience_requirements": [
                    {
                        "requirement": "5+ years backend experience",
                        "minimum_years": 5,
                    }
                ],
                "education_requirements": ["Bachelor's degree in CS"],
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

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description", _fake_analyze
    )

    _, created_job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": (
                    "Need Python and FastAPI with 5+ years backend " "experience."
                ),
            },
        )
    )

    analyze_status, analyze_payload, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{created_job['id']}/analyze")
    )
    assert analyze_status == 200
    assert analyze_payload["analysis_status"] == "COMPLETED"
    assert analyze_payload["analysis"]["required_skills"][0]["name"] == "Python"

    get_status, get_payload, _ = _run(
        _asgi_request("GET", f"/api/v1/jobs/{created_job['id']}/analysis")
    )
    assert get_status == 200
    assert get_payload["analysis_status"] == "COMPLETED"
    assert get_payload["analysis"]["seniority_level"] == "Senior"


def test_job_analysis_force_rerun_and_existing(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def _fake_analyze(_: str) -> JobAnalysis:
        calls["count"] += 1
        return JobAnalysis.model_validate(
            {
                "required_skills": [{"name": "Python", "category": "language"}],
                "preferred_skills": [],
                "minimum_years_experience": 5,
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
        )

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description", _fake_analyze
    )

    _, created_job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Data Engineer",
                "company": "Acme",
                "description": "Need Python with backend experience.",
            },
        )
    )

    first_status, _, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{created_job['id']}/analyze")
    )
    assert first_status == 200
    assert calls["count"] == 1

    second_status, _, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{created_job['id']}/analyze")
    )
    assert second_status == 200
    assert calls["count"] == 1

    third_status, _, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{created_job['id']}/analyze?force=true")
    )
    assert third_status == 200
    assert calls["count"] == 2


def test_job_analysis_errors(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.ai.job_analyzer import JobAnalysisError

    missing_status, missing_payload, _ = _run(
        _asgi_request("POST", "/api/v1/jobs/999/analyze")
    )
    assert missing_status == 404
    assert missing_payload["detail"] == "Job not found"

    _, empty_desc_job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Role A",
                "company": "Acme",
                "description": "Initial description",
            },
        )
    )
    empty_job = db_session.get(Job, empty_desc_job["id"])
    assert empty_job is not None
    empty_job.description = ""
    db_session.add(empty_job)
    db_session.commit()

    no_desc_status, no_desc_payload, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{empty_desc_job['id']}/analyze")
    )
    assert no_desc_status == 422
    assert "no description" in no_desc_payload["detail"].lower()

    _, created_job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Role B",
                "company": "Acme",
                "description": "Need Python",
            },
        )
    )

    def _fail_analyze(_: str) -> JobAnalysis:
        raise JobAnalysisError(
            "Ollama is not available. Start Ollama and try again.",
            503,
        )

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description", _fail_analyze
    )

    fail_status, fail_payload, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{created_job['id']}/analyze")
    )
    assert fail_status == 503
    assert "Ollama is not available" in fail_payload["detail"]

    get_status, get_payload, _ = _run(
        _asgi_request("GET", f"/api/v1/jobs/{created_job['id']}/analysis")
    )
    assert get_status == 200
    assert get_payload["analysis_status"] == "FAILED"
    assert get_payload["analysis"] is None


def test_job_analysis_invalid_result_sets_failed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.ai.job_analyzer import JobAnalysisError

    _, created_job, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Role C",
                "company": "Acme",
                "description": "Need backend engineer",
            },
        )
    )

    def _invalid(_: str) -> JobAnalysis:
        raise JobAnalysisError("AI returned invalid job analysis structure.", 502)

    monkeypatch.setattr(
        "backend.services.job_analysis_service.analyze_job_description", _invalid
    )

    analyze_status, analyze_payload, _ = _run(
        _asgi_request("POST", f"/api/v1/jobs/{created_job['id']}/analyze")
    )
    assert analyze_status == 502
    assert "invalid job analysis structure" in analyze_payload["detail"].lower()


def test_job_match_success_and_list(db_session: Session) -> None:
    _, profile_payload, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Matcher"})
    )

    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Resume",
                "file_path": "data/resumes/r.pdf",
            },
        )
    )

    resume = db_session.get(Resume, resume_payload["id"])
    assert resume is not None
    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "skills": [{"name": "Python"}, {"name": "FastAPI"}, {"name": "AWS"}],
            "experience": [
                {
                    "start_date": "2017-01",
                    "end_date": None,
                    "is_current": True,
                }
            ],
            "education": [{"degree": "Bachelor of Computer Science"}],
            "projects": [],
            "certifications": [{"name": "AWS Certified Solutions Architect"}],
            "achievements": [],
            "languages": [],
        }
    ).model_dump()
    db_session.add(resume)

    _, job_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Need Python, FastAPI, Postgres and 5 years experience",
            },
        )
    )
    job = db_session.get(Job, job_payload["id"])
    assert job is not None
    job.analysis_status = "COMPLETED"
    job.analysis_result = JobAnalysis.model_validate(
        {
            "required_skills": [
                {"name": "Python", "category": "language"},
                {"name": "FastAPI", "category": "framework"},
                {"name": "PostgreSQL", "category": "database"},
            ],
            "preferred_skills": [{"name": "AWS", "category": "cloud"}],
            "minimum_years_experience": 5,
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

    match_status, match_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/jobs/{job_payload['id']}/match",
            {"resume_id": resume_payload["id"]},
        )
    )
    assert match_status == 200
    assert match_payload["job_id"] == job_payload["id"]
    assert match_payload["resume_id"] == resume_payload["id"]
    assert "PostgreSQL" in match_payload["missing_required_skills"]

    second_status, second_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/jobs/{job_payload['id']}/match",
            {"resume_id": resume_payload["id"]},
        )
    )
    assert second_status == 200
    assert second_payload["score"] == match_payload["score"]

    list_status, list_payload, _ = _run(
        _asgi_request("GET", f"/api/v1/jobs/{job_payload['id']}/matches")
    )
    assert list_status == 200
    assert len(list_payload) == 1
    assert list_payload[0]["resume_id"] == resume_payload["id"]


def test_job_match_prerequisite_errors(db_session: Session) -> None:
    _, profile_payload, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Matcher"})
    )

    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Resume",
                "file_path": "data/resumes/r.pdf",
            },
        )
    )

    _, job_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Need Python",
            },
        )
    )

    missing_resume_analysis_status, missing_resume_analysis_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/jobs/{job_payload['id']}/match",
            {"resume_id": resume_payload["id"]},
        )
    )
    assert missing_resume_analysis_status == 422
    assert (
        "resume analysis is required"
        in missing_resume_analysis_payload["detail"].lower()
    )

    resume = db_session.get(Resume, resume_payload["id"])
    assert resume is not None
    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "skills": [{"name": "Python"}],
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

    missing_job_analysis_status, missing_job_analysis_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/jobs/{job_payload['id']}/match",
            {"resume_id": resume_payload["id"]},
        )
    )
    assert missing_job_analysis_status == 422
    assert "job analysis is required" in missing_job_analysis_payload["detail"].lower()


def test_job_match_invalid_ids(db_session: Session) -> None:
    status_missing_job, payload_missing_job, _ = _run(
        _asgi_request("POST", "/api/v1/jobs/999/match", {"resume_id": 1})
    )
    assert status_missing_job == 404
    assert payload_missing_job["detail"] == "Job not found"

    _, job_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Need Python",
            },
        )
    )

    status_missing_resume, payload_missing_resume, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/jobs/{job_payload['id']}/match",
            {"resume_id": 999},
        )
    )
    assert status_missing_resume == 404
    assert payload_missing_resume["detail"] == "Resume not found"


def test_workflow_audit_end_to_end_manual_submission(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, profile_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/profile",
            {
                "name": "Audit User",
                "email": "audit@example.test",
                "location": "Bengaluru",
                "remote_preference": "remote",
            },
        )
    )

    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Audit Resume",
                "file_path": "data/resumes/audit.pdf",
            },
        )
    )
    _set_resume_analysis(db_session, resume_payload["id"])

    class _RemotiveConnector:
        source_name = "remotive"
        source_type = "public_api"

        def search(self, criteria: object) -> list[object]:
            from backend.services.job_discovery.models import DiscoveredJob

            return [
                DiscoveredJob(
                    title="Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="Need Python and FastAPI",
                    job_url="https://careers.example.test/jobs/backend-engineer",
                    source_name="remotive",
                    source_type="public_api",
                )
            ]

    class _WebSearchConnector:
        source_name = "web_search"
        source_type = "search_result"

        def search(self, criteria: object) -> list[object]:
            from backend.services.job_discovery.models import DiscoveredJob

            return [
                DiscoveredJob(
                    title="Backend Engineer",
                    company="Acme",
                    location="Remote",
                    description="Need Python and FastAPI",
                    job_url=(
                        "https://careers.example.test/jobs/backend-engineer"
                        "?utm_source=search"
                    ),
                    source_name="web_search",
                    source_type="search_result",
                )
            ]

    monkeypatch.setattr(
        "backend.services.job_discovery.service._build_connectors",
        lambda payload: [_RemotiveConnector(), _WebSearchConnector()],
    )
    monkeypatch.setattr(
        "backend.services.job_discovery.service.analyze_job",
        _fake_completed_job_analysis,
    )

    def _draft_screening_answer(**kwargs):
        question = str(kwargs["question"]).lower()
        if "authorized" in question:
            return None, QuestionStatus.NEEDS_USER_INPUT
        return "This role aligns with my backend experience.", QuestionStatus.DRAFT

    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_cover_letter",
        lambda **_: "Draft cover letter for review.",
    )
    monkeypatch.setattr(
        "backend.services.application_preparation_service.generate_screening_answer",
        _draft_screening_answer,
    )

    discover_status, discover_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/discover",
            {
                "resume_id": resume_payload["id"],
                "sources": ["remotive", "web_search"],
                "max_results_per_source": 5,
            },
        )
    )
    assert discover_status == 200
    assert discover_payload["total_discovered"] == 2
    assert discover_payload["total_deduplicated"] == 1
    assert discover_payload["total_matched"] == 1

    first_result = discover_payload["results"][0]
    discovered_job_id = first_result["job_id"]
    assert first_result["match_score"] >= 0
    assert len(first_result["discovered_sources"]) == 2

    repeat_discover_status, repeat_discover_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/discover",
            {
                "resume_id": resume_payload["id"],
                "sources": ["remotive", "web_search"],
                "max_results_per_source": 5,
            },
        )
    )
    assert repeat_discover_status == 200
    assert len(repeat_discover_payload["results"]) == 1
    assert repeat_discover_payload["results"][0]["job_id"] == discovered_job_id

    job_rows = list(
        db_session.scalars(
            select(Job).where(
                Job.url == "https://careers.example.test/jobs/backend-engineer"
            )
        ).all()
    )
    assert len(job_rows) == 1

    match_rows = list(
        db_session.scalars(
            select(JobMatch).where(
                JobMatch.job_id == discovered_job_id,
                JobMatch.resume_id == resume_payload["id"],
            )
        ).all()
    )
    assert len(match_rows) == 1

    prepare_status, prepare_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/applications/prepare",
            {
                "job_id": discovered_job_id,
                "profile_id": profile_payload["id"],
                "resume_id": resume_payload["id"],
                "screening_questions": [
                    "Are you authorized to work in India?",
                    "Why are you interested in this role?",
                ],
            },
        )
    )
    assert prepare_status == 200
    application_id = prepare_payload["application_id"]
    assert prepare_payload["status"] == "READY_FOR_REVIEW"

    review_status, review_payload, _ = _run(
        _asgi_request("GET", f"/api/v1/applications/{application_id}/review")
    )
    assert review_status == 200
    assert review_payload["cover_letter_status"] == "DRAFT"
    assert review_payload["screening_answers"][0]["status"] == "NEEDS_USER_INPUT"
    assert review_payload["screening_answers"][0]["answer"] is None

    blocked_approve_status, blocked_approve_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{application_id}/approve",
            {"approve": True},
        )
    )
    assert blocked_approve_status == 409
    assert "approved" in blocked_approve_payload["detail"].lower()

    review_update_status, review_update_payload, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{application_id}/review",
            {
                "cover_letter": "Final reviewed cover letter.",
                "cover_letter_status": "APPROVED",
                "screening_answers": [
                    {
                        "id": answer["id"],
                        "answer": (
                            "I am authorized to work in India."
                            if "authorized" in answer["question"].lower()
                            else "This role matches my backend background."
                        ),
                        "status": "APPROVED",
                    }
                    for answer in review_payload["screening_answers"]
                ],
            },
        )
    )
    assert review_update_status == 200
    assert review_update_payload["cover_letter_status"] == "APPROVED"
    assert all(
        item["status"] == "APPROVED"
        for item in review_update_payload["screening_answers"]
    )

    approve_status, approve_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{application_id}/approve",
            {"approve": True},
        )
    )
    assert approve_status == 200
    assert approve_payload["user_approved"] is True

    confirm_status, confirm_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{application_id}/submit-confirmation",
            {"confirm": True},
        )
    )
    assert confirm_status == 200
    assert confirm_payload["status"] == "APPLIED"

    tracker_status, tracker_payload, _ = _run(
        _asgi_request("GET", "/api/v1/applications/tracker?status=APPLIED&company=Acme")
    )
    assert tracker_status == 200
    assert len(tracker_payload) == 1
    assert tracker_payload[0]["status"] == "APPLIED"
    event_types = [item["event_type"] for item in tracker_payload[0]["events"]]
    assert event_types.count("DISCOVERED") == 1
    assert "PREPARING" in event_types
    assert event_types.count("READY_FOR_REVIEW") >= 1
    assert event_types[-1] == "APPLIED"

    analytics_status, analytics_payload, _ = _run(
        _asgi_request("GET", "/api/v1/analytics/overview")
    )
    assert analytics_status == 200
    assert analytics_payload["jobs_found"] == 1
    assert analytics_payload["applications"] == 1
    assert any(
        item["status"] == "APPLIED" and item["count"] == 1
        for item in analytics_payload["applications_by_status"]
    )


def test_discovery_api_reports_search_timeout_and_bad_credentials(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services.job_discovery.base import JobDiscoveryConnectorError

    _, profile_payload, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Discovery Audit"})
    )
    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Audit Resume",
                "file_path": "data/resumes/discovery-audit.pdf",
            },
        )
    )
    _set_resume_analysis(db_session, resume_payload["id"])

    class _TimeoutConnector:
        source_name = "web_search"
        source_type = "search_result"

        def search(self, criteria: object) -> list[object]:
            raise JobDiscoveryConnectorError("Search API timed out. Try again later.")

    class _AuthConnector:
        source_name = "web_search"
        source_type = "search_result"

        def search(self, criteria: object) -> list[object]:
            raise JobDiscoveryConnectorError(
                "Search API request failed with status 401"
            )

    monkeypatch.setattr(
        "backend.services.job_discovery.service._build_connectors",
        lambda payload: [_TimeoutConnector(), _AuthConnector()],
    )

    discover_status, discover_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs/discover",
            {
                "resume_id": resume_payload["id"],
                "sources": ["web_search"],
            },
        )
    )
    assert discover_status == 200
    assert discover_payload["results"] == []
    messages = [item["message"] for item in discover_payload["errors"]]
    assert "Search API timed out. Try again later." in messages
    assert "Search API request failed with status 401" in messages


def test_prepare_application_falls_back_when_ollama_is_unavailable(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, profile_payload, _ = _run(
        _asgi_request("POST", "/api/v1/profile", {"name": "Fallback User"})
    )
    _, resume_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/resumes",
            {
                "profile_id": profile_payload["id"],
                "name": "Fallback Resume",
                "file_path": "data/resumes/fallback.pdf",
            },
        )
    )
    _set_resume_analysis(db_session, resume_payload["id"])

    _, job_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/jobs",
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Need Python and backend experience",
            },
        )
    )
    _set_job_analysis(db_session, job_payload["id"])

    def _raise_ollama(*args, **kwargs):
        raise OllamaClientError(
            "Ollama is not available. Start Ollama and try again.",
            status_code=503,
        )

    monkeypatch.setattr(
        "backend.ai.application_drafter.OllamaClient.chat_json",
        _raise_ollama,
    )

    prepare_status, prepare_payload, _ = _run(
        _asgi_request(
            "POST",
            "/api/v1/applications/prepare",
            {
                "job_id": job_payload["id"],
                "profile_id": profile_payload["id"],
                "resume_id": resume_payload["id"],
                "screening_questions": ["Why are you interested in this role?"],
            },
        )
    )
    assert prepare_status == 200
    assert prepare_payload["cover_letter"]
    assert prepare_payload["questions"][0]["status"] == "DRAFT"
    assert prepare_payload["questions"][0]["answer"]


def test_application_review_update_rejects_invalid_approved_content(
    db_session: Session,
) -> None:
    application = _seed_ready_review_application(db_session)

    review_status, review_payload, _ = _run(
        _asgi_request("GET", f"/api/v1/applications/{application.id}/review")
    )
    assert review_status == 200

    invalid_status, invalid_payload, _ = _run(
        _asgi_request(
            "PATCH",
            f"/api/v1/applications/{application.id}/review",
            {
                "cover_letter": "Approved draft",
                "cover_letter_status": "APPROVED",
                "screening_answers": [
                    {
                        "id": review_payload["screening_answers"][0]["id"],
                        "answer": "",
                        "status": "APPROVED",
                    }
                ],
            },
        )
    )
    assert invalid_status == 422
    assert "must have content before approval" in invalid_payload["detail"].lower()


def test_application_execute_endpoint_returns_open_and_apply_for_linkedin_and_naukri(
    db_session: Session,
) -> None:
    linkedin_application = _seed_ready_review_application(
        db_session,
        job_url="https://www.linkedin.com/jobs/view/123",
    )
    naukri_application = _seed_ready_review_application(
        db_session,
        job_url="https://www.naukri.com/job-listings-456",
    )

    for application in (linkedin_application, naukri_application):
        execute_status, execute_payload, _ = _run(
            _asgi_request(
                "POST",
                f"/api/v1/applications/{application.id}/execute",
                {},
            )
        )
        assert execute_status == 200
        assert execute_payload["mode"] == "OPEN_AND_APPLY"
        assert execute_payload["status"] == "OPEN_AND_APPLY"
        assert execute_payload["submitted"] is False


def test_application_execute_endpoint_reports_authorized_api_success_and_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    successful_application = _seed_ready_review_application(
        db_session,
        job_url="https://apply.example.test/jobs/1",
    )
    failed_application = _seed_ready_review_application(
        db_session,
        job_url="https://apply.example.test/jobs/2",
    )

    class _Adapter:
        name = "authorized-audit"

        def supports(self, application: Application) -> bool:
            return application.id in {successful_application.id, failed_application.id}

        def submit(self, *, application: Application, application_url: str | None):
            if application.id == successful_application.id:
                from backend.services.application_execution_service import (
                    AuthorizedExecutionResult,
                )

                return AuthorizedExecutionResult(
                    success=True,
                    message="Submitted through authorized API.",
                )
            from backend.services.application_execution_service import (
                AuthorizedExecutionResult,
            )

            return AuthorizedExecutionResult(
                success=False,
                message="Authorized API rejected the request.",
            )

    monkeypatch.setattr(
        "backend.services.application_execution_service._authorized_adapters",
        lambda: [_Adapter()],
    )

    success_status, success_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{successful_application.id}/execute",
            {"submit": True},
        )
    )
    assert success_status == 200
    assert success_payload["mode"] == "AUTHORIZED_API"
    assert success_payload["status"] == "SUBMITTED"
    assert success_payload["submitted"] is True

    failure_status, failure_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{failed_application.id}/execute",
            {"submit": True},
        )
    )
    assert failure_status == 200
    assert failure_payload["mode"] == "AUTHORIZED_API"
    assert failure_payload["status"] == "BLOCKED"
    assert failure_payload["submitted"] is False

    successful_row = db_session.get(Application, successful_application.id)
    failed_row = db_session.get(Application, failed_application.id)
    assert successful_row is not None
    assert failed_row is not None
    assert successful_row.status == ApplicationStatus.APPLIED
    assert failed_row.status == ApplicationStatus.READY_FOR_REVIEW
    assert failed_row.submitted_at is None


def test_application_execute_endpoint_reports_browser_field_outcomes(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _seed_ready_review_application(
        db_session,
        job_url="https://careers.example.test/jobs/backend-engineer/apply",
    )

    monkeypatch.setattr(
        "backend.services.application_execution_service._authorized_adapters",
        lambda: [],
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
                    "value": "audit@example.test",
                    "message": "Filled successfully.",
                },
                {
                    "field": "portfolio",
                    "label": "Portfolio",
                    "type": "text",
                    "status": "FAILED",
                    "value": "https://portfolio.example.test",
                    "message": "Failed to fill field safely.",
                },
                {
                    "field": "visa",
                    "label": "Visa Status",
                    "type": "text",
                    "status": "NEEDS_USER_INPUT",
                    "value": None,
                    "message": "No verified user value available.",
                },
            ],
            "Manual review and submission required.",
        ),
    )

    execute_status, execute_payload, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{application.id}/execute",
            {
                "application_url": "https://careers.example.test/jobs/backend-engineer/apply",
                "detect_fields": False,
                "fields": [
                    {
                        "name": "email",
                        "label": "Email",
                        "field_type": "email",
                        "required": True,
                    }
                ],
            },
        )
    )
    assert execute_status == 200
    assert execute_payload["mode"] == "BROWSER_ASSISTED"
    assert execute_payload["status"] == "READY"
    assert execute_payload["submitted"] is False
    assert [item["status"] for item in execute_payload["field_results"]] == [
        "FILLED",
        "FAILED",
        "NEEDS_USER_INPUT",
    ]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Execution currently ignores rejected preparation items and still "
        "allows browser/API execution."
    ),
)
def test_execute_blocks_rejected_preparation_items(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _seed_ready_review_application(db_session)
    application.user_approved = False
    application.preparation_details = {
        "cover_letter_status": QuestionStatus.REJECTED.value
    }
    application.questions[0].status = QuestionStatus.REJECTED
    db_session.add(application)
    db_session.add(application.questions[0])
    db_session.commit()

    monkeypatch.setattr(
        "backend.services.application_execution_service._authorized_adapters",
        lambda: [],
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
                    "value": "audit@example.test",
                    "message": "Filled successfully.",
                }
            ],
            "Manual review and submission required.",
        ),
    )

    execute_status, _, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{application.id}/execute",
            {
                "application_url": "https://careers.example.test/jobs/backend-engineer/apply",
                "detect_fields": False,
                "fields": [
                    {
                        "name": "email",
                        "label": "Email",
                        "field_type": "email",
                        "required": True,
                    }
                ],
            },
        )
    )
    assert execute_status == 409


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Authorized API success updates application status but does not "
        "record an APPLIED event in the tracker timeline."
    ),
)
def test_authorized_execution_records_applied_event(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _seed_ready_review_application(
        db_session,
        job_url="https://apply.example.test/jobs/3",
    )

    class _Adapter:
        name = "authorized-audit"

        def supports(self, app: Application) -> bool:
            return app.id == application.id

        def submit(self, *, application: Application, application_url: str | None):
            from backend.services.application_execution_service import (
                AuthorizedExecutionResult,
            )

            return AuthorizedExecutionResult(
                success=True,
                message="Submitted through authorized API.",
            )

    monkeypatch.setattr(
        "backend.services.application_execution_service._authorized_adapters",
        lambda: [_Adapter()],
    )

    execute_status, _, _ = _run(
        _asgi_request(
            "POST",
            f"/api/v1/applications/{application.id}/execute",
            {"submit": True},
        )
    )
    assert execute_status == 200

    events = list(
        db_session.scalars(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == application.id
            )
        ).all()
    )
    assert any(item.event_type == ApplicationStatus.APPLIED.value for item in events)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Browser execution with explicit fields does not gracefully degrade "
        "when Playwright is unavailable."
    ),
)
def test_execute_handles_browser_unavailable_with_explicit_fields(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BROWSER_ASSISTANT_MODE", "playwright")
    get_settings.cache_clear()
    try:
        application = _seed_ready_review_application(
            db_session,
            job_url="https://careers.example.test/jobs/backend-engineer/apply",
        )
        monkeypatch.setattr(
            "backend.services.application_execution_service._authorized_adapters",
            lambda: [],
        )
        monkeypatch.setattr(
            "backend.browser.assistant._run_playwright_fill",
            lambda application_url, fields, headless: (
                fields,
                (
                    "Playwright is unavailable in this environment. Install "
                    "browsers and use dry-run/manual flow."
                ),
            ),
        )

        execute_status, execute_payload, _ = _run(
            _asgi_request(
                "POST",
                f"/api/v1/applications/{application.id}/execute",
                {
                    "application_url": "https://careers.example.test/jobs/backend-engineer/apply",
                    "detect_fields": False,
                    "fields": [
                        {
                            "name": "email",
                            "label": "Email",
                            "field_type": "email",
                            "required": True,
                        }
                    ],
                },
            )
        )
        assert execute_status == 200
        assert execute_payload["submitted"] is False
        assert execute_payload["requires_human_submit"] is True
        assert "Playwright is unavailable" in execute_payload["message"]
    finally:
        get_settings.cache_clear()


def _set_resume_analysis(db_session: Session, resume_id: int) -> Resume:
    resume = db_session.get(Resume, resume_id)
    assert resume is not None
    resume.analysis_status = "COMPLETED"
    resume.analysis_result = CandidateProfile.model_validate(
        {
            "headline": "Backend Engineer",
            "location": "Bengaluru",
            "skills": [
                {"name": "Python"},
                {"name": "FastAPI"},
                {"name": "AWS"},
            ],
            "experience": [
                {
                    "title": "Backend Engineer",
                    "start_date": "2019-01",
                    "is_current": True,
                }
            ],
            "education": [{"degree": "Bachelor of Computer Science"}],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
        }
    ).model_dump()
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _set_job_analysis(db_session: Session, job_id: int) -> Job:
    job = db_session.get(Job, job_id)
    assert job is not None
    job.analysis_status = "COMPLETED"
    job.analysis_result = JobAnalysis.model_validate(
        {
            "role_summary": "Build backend APIs",
            "required_skills": [
                {"name": "Python", "category": "language"},
                {"name": "FastAPI", "category": "framework"},
            ],
            "preferred_skills": [{"name": "AWS", "category": "cloud"}],
            "minimum_years_experience": 3,
            "preferred_years_experience": None,
            "experience_requirements": [],
            "education_requirements": ["bachelor"],
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
    ).model_dump()
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _fake_completed_job_analysis(db: Session, job_id: int, force: bool = False):
    job = _set_job_analysis(db, job_id)
    return job, JobAnalysis.model_validate(job.analysis_result)


def _seed_ready_review_application(
    db_session: Session,
    *,
    job_url: str = "https://careers.example.test/jobs/backend-engineer/apply",
) -> Application:
    profile = UserProfile(
        name="Audit Applicant",
        email="audit@example.test",
        location="Bengaluru",
    )
    db_session.add(profile)
    db_session.flush()

    source = JobSource(name="manual", source_type="manual")
    db_session.add(source)
    db_session.flush()

    job = Job(
        source_id=source.id,
        title="Backend Engineer",
        company="Acme",
        description="Build APIs",
        url=job_url,
        analysis_status="COMPLETED",
        analysis_result=JobAnalysis.model_validate(
            {
                "required_skills": [{"name": "Python", "category": "language"}],
                "preferred_skills": [],
                "minimum_years_experience": 1,
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
    db_session.add(job)
    db_session.flush()

    resume = Resume(
        profile_id=profile.id,
        name="Audit Resume",
        file_path="data/resumes/audit-review.pdf",
        analysis_status="COMPLETED",
        analysis_result=CandidateProfile.model_validate(
            {
                "headline": "Backend Engineer",
                "skills": [{"name": "Python"}],
                "experience": [
                    {
                        "title": "Engineer",
                        "start_date": "2020-01",
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
    db_session.add(resume)
    db_session.flush()

    application = Application(
        job_id=job.id,
        profile_id=profile.id,
        resume_id=resume.id,
        status=ApplicationStatus.READY_FOR_REVIEW,
        cover_letter="Reviewed cover letter.",
        user_approved=True,
        preparation_details={"cover_letter_status": QuestionStatus.APPROVED.value},
    )
    db_session.add(application)
    db_session.flush()

    db_session.add(
        ApplicationQuestion(
            application_id=application.id,
            question="Are you authorized to work in India?",
            answer="Yes",
            status=QuestionStatus.APPROVED,
        )
    )
    db_session.commit()
    db_session.refresh(application)
    return application
