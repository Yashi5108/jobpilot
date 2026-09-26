from __future__ import annotations

import streamlit as st

from frontend.api_client import ApiClient, ApiClientError


def render_resumes(api: ApiClient) -> None:
    st.header("Resumes")
    st.caption("Upload PDF or DOCX resumes and parse text for downstream workflows.")

    profile_id = _resolve_profile_id(api)
    if profile_id is None:
        st.warning(
            "Create your profile first on the Profile page before uploading resumes."
        )
        return

    with st.form("upload_resume_form"):
        st.subheader("Upload Resume")
        uploaded = st.file_uploader("Choose PDF or DOCX", type=["pdf", "docx"])
        submitted = st.form_submit_button("Upload and Parse")
        if submitted:
            if uploaded is None:
                st.error("Please choose a PDF or DOCX file to upload.")
            else:
                try:
                    response = api.post_multipart(
                        path="/api/v1/resumes/upload",
                        form_fields={"profile_id": str(profile_id)},
                        file_field_name="file",
                        filename=uploaded.name,
                        content=uploaded.getvalue(),
                        content_type=uploaded.type or "application/octet-stream",
                    )
                    data = response.data if isinstance(response.data, dict) else {}
                    st.success("Resume parsed successfully.")
                    st.write(f"Resume: {data.get('name', '-')}")
                    st.write(f"Type: {(data.get('file_type') or '-').upper()}")
                    st.write(f"Size: {data.get('file_size_bytes', 0)} bytes")
                    st.write(f"Status: {data.get('parse_status') or '-'}")
                    st.write("Preview")
                    st.code(data.get("text_preview") or "No text preview available")
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))

    try:
        response = api.get("/api/v1/resumes")
    except ApiClientError as exc:
        st.error(str(exc))
        return

    resumes = response.data if isinstance(response.data, list) else []
    if not resumes:
        st.info("No resumes found yet.")
        return

    st.subheader("Stored Resumes")
    for item in resumes:
        with st.container(border=True):
            resume_id = item.get("id")
            st.write(f"ID: {item.get('id')}")
            st.write(f"Name: {item.get('name')}")
            st.write(f"File Type: {(item.get('file_type') or '-').upper()}")
            st.write(f"MIME Type: {item.get('mime_type') or '-'}")
            st.write(f"File Size: {item.get('file_size_bytes') or 0} bytes")
            st.write(f"Page Count: {item.get('page_count') or 0}")
            st.write(f"Status: {item.get('parse_status') or '-'}")
            st.write(f"AI Analysis: {item.get('analysis_status') or 'NOT_ANALYZED'}")
            st.write(f"Default: {'Yes' if item.get('is_default') else 'No'}")
            st.write(f"Created: {item.get('created_at')}")
            st.write(f"Updated: {item.get('updated_at')}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Load Details", key=f"resume_details_{resume_id}"):
                    try:
                        detail = api.get(f"/api/v1/resumes/{resume_id}").data
                        st.json(detail)
                    except ApiClientError as exc:
                        st.error(str(exc))
            with col2:
                if st.button("View Parsed Text", key=f"resume_text_{resume_id}"):
                    try:
                        text_payload = api.get(f"/api/v1/resumes/{resume_id}/text").data
                        parsed_text = text_payload.get("normalized_text", "")
                        st.text_area(
                            "Extracted Text",
                            value=parsed_text,
                            height=300,
                            key=f"resume_text_area_{resume_id}",
                        )
                    except ApiClientError as exc:
                        st.error(str(exc))

                if st.button("Analyze with AI", key=f"resume_analyze_{resume_id}"):
                    try:
                        api.post_empty(f"/api/v1/resumes/{resume_id}/analyze")
                        st.success("AI analysis completed.")
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))

                if st.button("View AI Analysis", key=f"resume_analysis_{resume_id}"):
                    try:
                        analysis_payload = api.get(
                            f"/api/v1/resumes/{resume_id}/analysis"
                        ).data
                        _render_analysis_payload(analysis_payload)
                    except ApiClientError as exc:
                        st.error(str(exc))

            with col3:
                if st.button("Delete", key=f"resume_delete_{item.get('id')}"):
                    try:
                        api.delete(f"/api/v1/resumes/{resume_id}")
                        st.success("Resume deleted.")
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))


def _resolve_profile_id(api: ApiClient) -> int | None:
    try:
        response = api.get("/api/v1/profile")
    except ApiClientError:
        return None

    payload = response.data if isinstance(response.data, dict) else {}
    profile_id = payload.get("id")
    if isinstance(profile_id, int) and profile_id > 0:
        return profile_id
    return None


def _render_analysis_payload(payload: dict[str, object]) -> None:
    status = str(payload.get("analysis_status") or "NOT_ANALYZED")
    st.write(f"Analysis Status: {status}")

    profile = payload.get("profile")
    if not isinstance(profile, dict):
        st.info("No analysis profile stored yet for this resume.")
        return

    st.write(f"Name: {profile.get('name') or '-'}")
    st.write(f"Headline: {profile.get('headline') or '-'}")
    st.write(f"Summary: {profile.get('summary') or '-'}")

    st.write("Skills")
    skills = profile.get("skills")
    if isinstance(skills, list) and skills:
        for skill in skills:
            if isinstance(skill, dict):
                label = skill.get("name") or "-"
                category = skill.get("category") or "other"
                st.write(f"- {label} ({category})")
    else:
        st.write("- None")

    st.write("Experience")
    experiences = profile.get("experience")
    if isinstance(experiences, list) and experiences:
        for exp in experiences:
            if isinstance(exp, dict):
                title = exp.get("title") or "-"
                company = exp.get("company") or "-"
                st.write(f"- {title} at {company}")
    else:
        st.write("- None")

    st.write("Education")
    education = profile.get("education")
    if isinstance(education, list) and education:
        for edu in education:
            if isinstance(edu, dict):
                degree = edu.get("degree") or "-"
                institution = edu.get("institution") or "-"
                st.write(f"- {degree} - {institution}")
    else:
        st.write("- None")
