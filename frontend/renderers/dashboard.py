from __future__ import annotations

import streamlit as st

from frontend.api_client import ApiClient, ApiClientError
from frontend.components.metrics import metric_row


def render_dashboard(api: ApiClient) -> None:
    st.header("Dashboard")
    st.caption(
        "Your JobPilot workspace will appear here as you discover jobs "
        "and prepare applications."
    )
    st.markdown(
        "Workflow: Dashboard -> Profile / Resume -> Find Jobs -> "
        "Job Matches -> Applications"
    )

    jobs_found = 0
    shortlisted = 0
    applications_count = 0
    interviews = 0
    offers = 0
    rejected = 0
    average_match = None
    top_missing: list[str] = []

    try:
        analytics_response = api.get("/api/v1/analytics/overview")
        analytics = (
            analytics_response.data if isinstance(analytics_response.data, dict) else {}
        )

        jobs_found = int(analytics.get("jobs_found") or 0)
        shortlisted = int(analytics.get("shortlisted_jobs") or 0)
        applications_count = int(analytics.get("applications") or 0)
        interviews = int(analytics.get("interviews") or 0)
        offers = int(analytics.get("offers") or 0)
        rejected = int(analytics.get("rejected") or 0)
        raw_avg = analytics.get("average_match_score")
        average_match = round(float(raw_avg), 1) if raw_avg is not None else None

        missing = analytics.get("frequently_missing_skills")
        if isinstance(missing, list):
            top_missing = [
                str(item.get("skill"))
                for item in missing
                if isinstance(item, dict) and item.get("skill")
            ][:5]
    except ApiClientError as exc:
        st.warning(str(exc))

    metric_row(
        [
            ("Jobs Found", jobs_found),
            ("Shortlisted", shortlisted),
            ("Applications", applications_count),
            ("Interviews", interviews),
            ("Offers", offers),
        ]
    )
    metric_row(
        [
            ("Rejected", rejected),
            (
                "Avg Match",
                f"{average_match}" if average_match is not None else "-",
            ),
        ]
    )

    if top_missing:
        st.write("Frequent skill gaps")
        for item in top_missing:
            st.write(f"- {item}")
