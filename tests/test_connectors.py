from __future__ import annotations

from backend.connectors.manual import ManualConnector
from backend.connectors.structured import (
    StructuredImportConnector,
    load_csv_jobs,
    load_json_jobs,
)


def test_manual_connector_returns_normalized_job() -> None:
    connector = ManualConnector(
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "description": "Build APIs",
            "url": "https://example.com/jobs/1",
            "work_arrangement": "Remote",
            "source_name": "manual",
            "source_type": "manual",
            "external_id": "abc-1",
        }
    )

    jobs = connector.discover()

    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].work_arrangement == "Remote"
    assert jobs[0].external_id == "abc-1"


def test_load_json_jobs_supports_list_and_jobs_object() -> None:
    list_payload = b'[{"title":"A","company":"C","description":"D"}]'
    wrapped_payload = b'{"jobs":[{"title":"A","company":"C","description":"D"}]}'

    list_records = load_json_jobs(list_payload)
    wrapped_records = load_json_jobs(wrapped_payload)

    assert len(list_records) == 1
    assert len(wrapped_records) == 1


def test_load_csv_jobs_reads_rows() -> None:
    content = (
        "title,company,description,url\n"
        "Backend Engineer,Acme,Build APIs,https://example.com/jobs/1\n"
    ).encode("utf-8")

    rows = load_csv_jobs(content)

    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"


def test_structured_import_connector_maps_remote_type_alias() -> None:
    connector = StructuredImportConnector(
        [
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Build APIs",
                "remote_type": "Hybrid",
            }
        ]
    )

    jobs = connector.discover()
    assert jobs[0].work_arrangement == "Hybrid"
