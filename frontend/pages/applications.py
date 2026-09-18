from __future__ import annotations

import streamlit as st

from backend.database.models import ApplicationStatus
from frontend.api_client import ApiClient, ApiClientError


def render_applications(api: ApiClient) -> None:
    st.header("Applications")

    _render_prepare_section(api)

    try:
        tracker_response = api.get("/api/v1/applications/tracker")
    except ApiClientError as exc:
        st.error(str(exc))
        return

    items = tracker_response.data if isinstance(tracker_response.data, list) else []
    if not items:
        st.info("No applications found yet.")
        return

    st.subheader("Application Tracker")
    for item in items:
        if not isinstance(item, dict):
            continue
        _render_tracker_item(api, item)


def _render_prepare_section(api: ApiClient) -> None:
    with st.expander("Prepare Application", expanded=False):
        with st.form("prepare_application_form"):
            job_id = st.number_input("Job ID", min_value=1, step=1)
            profile_id = st.number_input("Profile ID", min_value=1, step=1)
            resume_id = st.number_input("Resume ID", min_value=1, step=1)
            custom_questions = st.text_area(
                "Screening questions (one per line, optional)",
                value="",
                height=120,
            )
            force_regenerate = st.checkbox("Force regenerate drafts")
            submitted = st.form_submit_button("Prepare")

        if submitted:
            payload = {
                "job_id": int(job_id),
                "profile_id": int(profile_id),
                "resume_id": int(resume_id),
                "force_regenerate": force_regenerate,
            }
            questions = [
                line.strip() for line in custom_questions.splitlines() if line.strip()
            ]
            if questions:
                payload["screening_questions"] = questions

            try:
                response = api.post("/api/v1/applications/prepare", payload)
                data = response.data if isinstance(response.data, dict) else {}
                st.success(
                    "Prepared Application "
                    f"#{data.get('application_id', '-')}. Ready for review."
                )
                st.rerun()
            except ApiClientError as exc:
                st.error(str(exc))


def _render_tracker_item(api: ApiClient, item: dict[str, object]) -> None:
    app_id = item.get("id")
    if not isinstance(app_id, int):
        return

    title = str(item.get("job_title") or "Unknown role")
    company = str(item.get("company") or "Unknown company")
    status = str(item.get("status") or "UNKNOWN")

    with st.container(border=True):
        st.markdown(f"### Application #{app_id}")
        st.write(f"Job: {title}")
        st.write(f"Company: {company}")
        st.write(f"Status: {status}")
        st.write(f"Resume ID: {item.get('resume_id') or '-'}")
        match_score = (
            item.get("match_score") if item.get("match_score") is not None else "-"
        )
        st.write(f"Match Score: {match_score}")
        st.write(f"Applied date: {item.get('submitted_at') or '-'}")
        st.write(f"Last updated: {item.get('updated_at') or '-'}")

        _render_event_history(item.get("events"))

        col1, col2, col3 = st.columns(3)
        with col1:
            _render_status_update(api, app_id, status)
        with col2:
            if st.button("Approve", key=f"app_approve_{app_id}"):
                try:
                    api.post(
                        f"/api/v1/applications/{app_id}/approve",
                        {"approve": True},
                    )
                    st.success(f"Application {app_id} approved.")
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))
            if st.button("Confirm Submitted", key=f"app_submit_{app_id}"):
                try:
                    api.post(
                        f"/api/v1/applications/{app_id}/submit-confirmation",
                        {"confirm": True},
                    )
                    st.success(f"Application {app_id} marked APPLIED.")
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))
        with col3:
            if st.button("Refresh Review", key=f"app_review_{app_id}"):
                try:
                    response = api.get(f"/api/v1/applications/{app_id}/review")
                    review_payload = (
                        response.data if isinstance(response.data, dict) else {}
                    )
                    st.session_state[f"review_payload_{app_id}"] = review_payload
                except ApiClientError as exc:
                    st.error(str(exc))

            if st.button("Regenerate Cover Letter", key=f"app_regen_{app_id}"):
                try:
                    response = api.post(
                        f"/api/v1/applications/{app_id}/cover-letter/regenerate",
                        {},
                    )
                    review_payload = (
                        response.data if isinstance(response.data, dict) else {}
                    )
                    st.session_state[f"review_payload_{app_id}"] = review_payload
                    st.success("Cover letter regenerated.")
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))

        review_payload = st.session_state.get(f"review_payload_{app_id}")
        if isinstance(review_payload, dict):
            _render_review_payload(review_payload)
            _render_browser_assist_controls(api, app_id)


def _render_status_update(api: ApiClient, app_id: int, current_status: str) -> None:
    options = [status.value for status in ApplicationStatus]
    default_idx = options.index(current_status) if current_status in options else 0
    selected = st.selectbox(
        "Update status",
        options=options,
        index=default_idx,
        key=f"app_status_{app_id}",
    )
    if st.button("Save Status", key=f"app_status_save_{app_id}"):
        try:
            api.patch(f"/api/v1/applications/{app_id}/status", {"status": selected})
            st.success(f"Application {app_id} updated.")
            st.rerun()
        except ApiClientError as exc:
            st.error(str(exc))


def _render_event_history(raw_events: object) -> None:
    st.write("History")
    if not isinstance(raw_events, list) or not raw_events:
        st.write("- None")
        return

    for event in raw_events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type") or "-"
        created_at = event.get("created_at") or "-"
        description = event.get("description") or ""
        suffix = f" ({description})" if description else ""
        st.write(f"- {created_at} | {event_type}{suffix}")


def _render_review_payload(payload: dict[str, object]) -> None:
    st.write("Review")
    st.write(f"Review status: {payload.get('status') or '-'}")
    st.write(f"User approved: {payload.get('user_approved')}")
    match_score = (
        payload.get("match_score") if payload.get("match_score") is not None else "-"
    )
    st.write(f"Match score: {match_score}")
    st.write(f"Selected resume: {payload.get('selected_resume_id') or '-'}")
    st.write("Cover letter")
    st.text_area(
        "Cover letter draft",
        value=str(payload.get("cover_letter") or ""),
        height=220,
        key=f"cover_letter_review_{payload.get('application_id')}",
    )

    st.write("Screening answers")
    answers = payload.get("screening_answers")
    if isinstance(answers, list) and answers:
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            st.write(
                f"- {answer.get('question')} => "
                f"{answer.get('answer') or '[NEEDS_USER_INPUT]'} "
                f"({answer.get('status')})"
            )
    else:
        st.write("- None")

    fields = payload.get("fields_to_submit")
    st.write("Fields to be submitted")
    if isinstance(fields, list) and fields:
        for field in fields:
            if isinstance(field, dict):
                st.write(f"- {field.get('field')}: {field.get('value')}")
    else:
        st.write("- None")

    unknown = payload.get("unknown_fields")
    st.write("Unknown fields")
    if isinstance(unknown, list) and unknown:
        for item in unknown:
            st.write(f"- {item}")
    else:
        st.write("- None")


def _render_browser_assist_controls(api: ApiClient, app_id: int) -> None:
    with st.expander("Browser Assistance", expanded=False):
        application_url = st.text_input(
            "Application URL",
            key=f"browser_url_{app_id}",
        )
        st.caption(
            "Optional field map lines: name|label|type|required. "
            "Example: email|Email|email|true"
        )
        default_field_map = (
            "full_name|Full Name|text|true\n"
            "email|Email|email|true\n"
            "phone|Phone|tel|false\n"
            "cover_letter|Cover Letter|textarea|false"
        )
        lines = st.text_area(
            "Field map",
            value=default_field_map,
            height=120,
            key=f"browser_fields_{app_id}",
        )
        dry_run = st.checkbox(
            "Dry run (recommended)",
            value=True,
            key=f"browser_dry_run_{app_id}",
        )

        if st.button("Run Browser Assistant", key=f"browser_run_{app_id}"):
            if not application_url.strip():
                st.error("Application URL is required.")
                return

            fields = _parse_field_lines(lines)
            try:
                response = api.post(
                    f"/api/v1/applications/{app_id}/browser-assist",
                    {
                        "application_url": application_url.strip(),
                        "dry_run": dry_run,
                        "fields": fields,
                    },
                )
                payload = response.data if isinstance(response.data, dict) else {}
                st.success(
                    str(payload.get("message") or "Browser assistance completed.")
                )
                st.write("Mapped Fields")
                for item in payload.get("mapped_fields", []):
                    if isinstance(item, dict):
                        st.write(
                            f"- {item.get('field')} "
                            f"({item.get('type')}): {item.get('value')}"
                        )
                unknown = payload.get("unknown_fields")
                if isinstance(unknown, list) and unknown:
                    st.write("Unknown Fields")
                    for item in unknown:
                        st.write(f"- {item}")
            except ApiClientError as exc:
                st.error(str(exc))


def _parse_field_lines(raw: str) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split("|")]
        if len(parts) < 4:
            continue
        fields.append(
            {
                "name": parts[0],
                "label": parts[1],
                "field_type": parts[2] or "text",
                "required": parts[3].lower() in {"true", "1", "yes", "y"},
            }
        )
    return fields
