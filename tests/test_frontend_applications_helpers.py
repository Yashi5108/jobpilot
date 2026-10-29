from frontend.pages.applications import _parse_field_lines
from frontend.renderers.applications import _build_apply_queue_rows
from frontend.renderers.dashboard import _build_operator_run_history


def test_parse_field_lines_parses_valid_rows() -> None:
    payload = "email|Email|email|true\nphone|Phone|tel|false"

    fields = _parse_field_lines(payload)

    assert len(fields) == 2
    assert fields[0]["name"] == "email"
    assert fields[0]["required"] is True
    assert fields[1]["required"] is False


def test_parse_field_lines_skips_invalid_rows() -> None:
    payload = "invalid-only\nname|label|text"

    fields = _parse_field_lines(payload)

    assert fields == []


def test_build_apply_queue_rows_prioritizes_ready_for_review_and_scores() -> None:
    rows = _build_apply_queue_rows(
        [
            {
                "id": 2,
                "job_title": "Senior Data Engineer",
                "company": "Northstar",
                "status": "READY_FOR_REVIEW",
                "match_score": 93,
                "application_url": "https://jobs.example.com/alpha",
                "events": [],
            },
            {
                "id": 1,
                "job_title": "ML Engineer",
                "company": "SignalAI",
                "status": "DISCOVERED",
                "match_score": 72,
                "application_url": None,
                "events": [],
            },
            {
                "id": 3,
                "job_title": "Product Manager",
                "company": "Nova",
                "status": "APPLIED",
                "match_score": 89,
                "application_url": "https://jobs.example.com/beta",
                "events": [],
            },
        ]
    )

    assert [row["id"] for row in rows] == [2, 1]
    assert rows[0]["next_action"] == "Review + browser assist"
    assert rows[1]["next_action"] == "Review fit + prepare"


def test_build_operator_run_history_keeps_latest_actions_first() -> None:
    history = _build_operator_run_history(
        [
            {"timestamp": "2026-10-29 10:00", "action": "Review queue", "status": "Complete"},
            {"timestamp": "2026-10-29 09:30", "action": "Prepare cover letters", "status": "Running"},
            {"timestamp": "2026-10-29 11:00", "action": "Approve high-fit roles", "status": "Queued"},
        ]
    )

    assert [row["action"] for row in history] == [
        "Approve high-fit roles",
        "Review queue",
        "Prepare cover letters",
    ]
    assert history[0]["status"] == "Queued"


def test_build_operator_run_history_keeps_latest_actions_first() -> None:
    history = _build_operator_run_history(
        [
            {"timestamp": "2026-10-29 10:00", "action": "Review queue", "status": "Complete"},
            {"timestamp": "2026-10-29 09:30", "action": "Prepare cover letters", "status": "Running"},
            {"timestamp": "2026-10-29 11:00", "action": "Approve high-fit roles", "status": "Queued"},
        ]
    )

    assert [row["action"] for row in history] == [
        "Approve high-fit roles",
        "Review queue",
        "Prepare cover letters",
    ]
    assert history[0]["status"] == "Queued"
