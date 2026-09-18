from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.ai.resume_analyzer import ResumeAnalysisError
from backend.core.config import get_settings
from backend.database.database import Base, get_db
from backend.database.models import Job, QuestionStatus, Resume
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
