from __future__ import annotations

import streamlit as st


def job_card(job: dict) -> None:
    company = job.get("company") or "Unknown company"
    title = job.get("title") or "Untitled role"
    location = job.get("location") or "Location not specified"
    employment_type = job.get("employment_type") or "Not specified"
    source_name = (job.get("source") or {}).get("name", "Unknown source")
    description = job.get("description") or ""
    preview = description[:280].strip()
    if preview and len(description) > 280:
        preview = f"{preview}..."

    st.markdown(
        f"""
        <div class="panel-card">
            <div style="display:flex; justify-content:space-between; gap:0.75rem; align-items:flex-start;">
                <div>
                    <div class="mini-label">Job</div>
                    <div style="font-size:1.35rem; font-weight:800; margin-bottom:0.2rem;">{title}</div>
                    <div style="color:#cbd5e1; font-weight:600;">{company}</div>
                </div>
                <span class="status-pill primary">{source_name}</span>
            </div>
            <div style="margin-top:0.8rem; display:flex; gap:1rem; flex-wrap:wrap; color:#cbd5e1; font-size:0.92rem;">
                <span>📍 {location}</span>
                <span>💼 {employment_type}</span>
            </div>
            {f'<div style="margin-top:0.8rem; color:#dfe7f5; line-height:1.5;">{preview}</div>' if preview else ''}
            {f'<div style="margin-top:0.8rem;"><a href="{job["url"]}" target="_blank" style="text-decoration:none; color:#7dd3fc; font-weight:700;">Open Job Posting →</a></div>' if job.get("url") else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def application_card(application: dict) -> None:
    status = application.get("status", "UNKNOWN")
    job_id = application.get("job_id", "-")
    profile_id = application.get("profile_id", "-")
    resume_id = application.get("resume_id") or "-"

    pill_class = "primary"
    if str(status).upper() in {"APPLIED", "SUBMITTED"}:
        pill_class = "success"
    elif str(status).upper() in {"READY_FOR_REVIEW", "IN_REVIEW"}:
        pill_class = "warning"
    elif str(status).upper() in {"REJECTED", "DECLINED"}:
        pill_class = "danger"

    st.markdown(
        f"""
        <div class="panel-card">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem;">
                <div>
                    <div class="mini-label">Application</div>
                    <div style="font-size:1.2rem; font-weight:800;">#{application.get('id', '-')}</div>
                </div>
                <span class="status-pill {pill_class}">{status}</span>
            </div>
            <div style="margin-top:0.8rem; color:#dfe7f5; display:grid; gap:0.35rem;">
                <div>Job ID: {job_id}</div>
                <div>Profile ID: {profile_id}</div>
                <div>Resume ID: {resume_id}</div>
                {f'<div>Submitted At: {application["submitted_at"]}</div>' if application.get("submitted_at") else ''}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
