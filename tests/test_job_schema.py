from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.job import JobCreate, JobUpdate


def test_job_create_valid_payload() -> None:
    payload = JobCreate(
        title="Senior Backend Engineer",
        company="Example Technologies",
        description="Build reliable backend services.",
        url="https://example.com/jobs/senior-backend-engineer",
        location="Bengaluru, India",
        employment_type="Full-time",
    )

    assert payload.title == "Senior Backend Engineer"
    assert str(payload.url) == "https://example.com/jobs/senior-backend-engineer"


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "   "),
        ("company", ""),
        ("description", "\n\n"),
    ],
)
def test_job_create_rejects_empty_required_fields(field: str, value: str) -> None:
    data = {
        "title": "Role",
        "company": "Company",
        "description": "Desc",
    }
    data[field] = value

    with pytest.raises(ValidationError):
        JobCreate(**data)


def test_job_create_allows_omitted_optional_fields() -> None:
    payload = JobCreate(
        title="Backend Engineer",
        company="Example",
        description="Core backend role",
    )

    assert payload.url is None
    assert payload.location is None


def test_job_create_rejects_invalid_url_scheme() -> None:
    with pytest.raises(ValidationError):
        JobCreate(
            title="Backend Engineer",
            company="Example",
            description="Role",
            url="ftp://example.com/jobs/1",
        )


def test_job_update_validation() -> None:
    payload = JobUpdate(
        title="Updated Role",
        company="Example",
        description="Updated description",
        url="https://example.com/jobs/updated",
    )

    assert payload.title == "Updated Role"
