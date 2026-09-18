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

    with st.container(border=True):
        st.markdown(f"### {title}")
        st.caption(company)
        st.write(f"Location: {location}")
        st.write(f"Employment: {employment_type}")
        st.write(f"Source: {source_name}")
        if job.get("url"):
            st.link_button("Open Job Posting", job["url"])
        if preview:
            st.write(preview)


def application_card(application: dict) -> None:
    status = application.get("status", "UNKNOWN")
    job_id = application.get("job_id", "-")
    profile_id = application.get("profile_id", "-")
    resume_id = application.get("resume_id") or "-"

    with st.container(border=True):
        st.markdown(f"### Application #{application.get('id', '-')}")
        st.write(f"Status: {status}")
        st.write(f"Job ID: {job_id}")
        st.write(f"Profile ID: {profile_id}")
        st.write(f"Resume ID: {resume_id}")
        if application.get("submitted_at"):
            st.write(f"Submitted At: {application['submitted_at']}")
