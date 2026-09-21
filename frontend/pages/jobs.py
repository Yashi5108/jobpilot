from __future__ import annotations

from urllib.parse import quote_plus

import streamlit as st

from frontend.api_client import ApiClient, ApiClientError
from frontend.components.cards import job_card


def render_jobs(api: ApiClient) -> None:
    st.header("Jobs")
    st.caption(
        "Discover matching jobs from supported sources, then fall back to manual "
        "entry or imports when needed."
    )

    resumes: list[dict[str, object]] = []
    try:
        resume_response = api.get("/api/v1/resumes")
        if isinstance(resume_response.data, list):
            resumes = [item for item in resume_response.data if isinstance(item, dict)]
    except ApiClientError as exc:
        st.warning(f"Unable to load resumes for discovery: {exc}")

    analyzed_resumes = [
        item
        for item in resumes
        if str(item.get("analysis_status") or "") == "COMPLETED"
        and isinstance(item.get("id"), int)
    ]

    _render_find_jobs_section(api, analyzed_resumes)

    with st.expander("Import Jobs", expanded=False):
        st.write("Manual URL import")
        with st.form("import_manual_job_form"):
            manual_payload = {
                "title": st.text_input("Import title *", key="import_title"),
                "company": st.text_input("Import company *", key="import_company"),
                "description": st.text_area(
                    "Import description *",
                    height=140,
                    key="import_description",
                ),
                "location": st.text_input("Import location", key="import_location"),
                "employment_type": st.text_input(
                    "Import employment type",
                    key="import_employment_type",
                ),
                "work_arrangement": st.text_input(
                    "Import work arrangement",
                    key="import_work_arrangement",
                ),
                "url": st.text_input("Import job URL", key="import_url"),
                "source_name": st.text_input(
                    "Source name", value="manual", key="import_source_name"
                ),
                "source_type": st.text_input(
                    "Source type", value="manual", key="import_source_type"
                ),
                "external_id": st.text_input(
                    "External ID (optional)",
                    key="import_external_id",
                ),
            }

            manual_submitted = st.form_submit_button("Import Manual Job")
            if manual_submitted:
                try:
                    response = api.post(
                        "/api/v1/jobs/import/manual",
                        {
                            key: value
                            for key, value in manual_payload.items()
                            if value not in ("", None)
                        },
                    )
                    _render_import_result(response.data)
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))

        st.write("Structured import")
        json_file = st.file_uploader(
            "Import JSON file",
            type=["json"],
            key="jobs_import_json_file",
        )
        if st.button("Import JSON", key="jobs_import_json_button"):
            if json_file is None:
                st.error("Select a JSON file before importing.")
            else:
                try:
                    response = api.post_multipart(
                        path="/api/v1/jobs/import/json",
                        form_fields={},
                        file_field_name="file",
                        filename=json_file.name,
                        content=json_file.read(),
                        content_type=json_file.type or "application/json",
                    )
                    _render_import_result(response.data)
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))

        csv_file = st.file_uploader(
            "Import CSV file",
            type=["csv"],
            key="jobs_import_csv_file",
        )
        if st.button("Import CSV", key="jobs_import_csv_button"):
            if csv_file is None:
                st.error("Select a CSV file before importing.")
            else:
                try:
                    response = api.post_multipart(
                        path="/api/v1/jobs/import/csv",
                        form_fields={},
                        file_field_name="file",
                        filename=csv_file.name,
                        content=csv_file.read(),
                        content_type=csv_file.type or "text/csv",
                    )
                    _render_import_result(response.data)
                    st.rerun()
                except ApiClientError as exc:
                    st.error(str(exc))

    with st.form("create_job_form"):
        st.subheader("Add a Job")
        payload = {
            "title": st.text_input("Job title *"),
            "company": st.text_input("Company *"),
            "location": st.text_input("Location"),
            "url": st.text_input("Job URL"),
            "employment_type": st.text_input("Employment type"),
            "description": st.text_area("Job description *", height=180),
        }
        submitted = st.form_submit_button("Save Job")
        if submitted:
            try:
                clean_payload = {
                    key: value
                    for key, value in payload.items()
                    if value not in ("", None)
                }
                api.post("/api/v1/jobs", clean_payload)
                st.success("Job saved successfully.")
                st.rerun()
            except ApiClientError as exc:
                st.error(str(exc))

    company_filter = st.text_input("Filter tracked jobs by company (optional)")
    jobs_path = "/api/v1/jobs"
    if company_filter.strip():
        jobs_path = f"/api/v1/jobs?company={quote_plus(company_filter.strip())}"

    try:
        response = api.get(jobs_path)
    except ApiClientError as exc:
        st.error(str(exc))
        return

    jobs = response.data if isinstance(response.data, list) else []
    if not jobs:
        st.info("No jobs found yet. Add a job to begin tracking.")
        return

    resume_options = {
        int(item["id"]): str(item.get("name") or f"Resume #{item['id']}")
        for item in resumes
        if isinstance(item.get("id"), int)
    }

    st.subheader("Tracked Jobs")
    for job in jobs:
        job_card(job)

        job_id = job.get("id")
        if not isinstance(job_id, int):
            continue

        with st.expander(f"View details #{job_id}"):
            st.write(f"Title: {job.get('title') or '-'}")
            st.write(f"Company: {job.get('company') or '-'}")
            st.write(f"Location: {job.get('location') or '-'}")
            st.write(f"Employment type: {job.get('employment_type') or '-'}")
            st.write("Description")
            st.text_area(
                "Job description",
                value=job.get("description") or "",
                height=220,
                key=f"job_description_{job_id}",
            )
            source = job.get("source") if isinstance(job.get("source"), dict) else {}
            st.write(f"Source: {source.get('name') or 'manual'}")
            st.write(f"URL: {job.get('url') or '-'}")

            st.divider()
            st.subheader("AI Analysis")
            analysis_status = str(job.get("analysis_status") or "NOT_ANALYZED")
            st.write(f"Status: {analysis_status}")

            analyze_col, rerun_col = st.columns(2)
            with analyze_col:
                if st.button("Analyze Job", key=f"job_analyze_{job_id}"):
                    try:
                        api.post_empty(f"/api/v1/jobs/{job_id}/analyze")
                        st.success("Job analysis completed.")
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))

            with rerun_col:
                if st.button("Re-run Analysis", key=f"job_reanalyze_{job_id}"):
                    try:
                        api.post_empty(f"/api/v1/jobs/{job_id}/analyze?force=true")
                        st.success("Job analysis rerun completed.")
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))

            try:
                analysis_payload = api.get(f"/api/v1/jobs/{job_id}/analysis").data
                if isinstance(analysis_payload, dict):
                    _render_job_analysis(analysis_payload)
            except ApiClientError as exc:
                st.error(str(exc))

            st.divider()
            st.subheader("Match Resume")

            if not resume_options:
                st.info("No resumes available. Add and analyze a resume first.")
            else:
                selected_resume_id = st.selectbox(
                    "Select Resume",
                    options=list(resume_options.keys()),
                    format_func=(
                        lambda item_id: f"#{item_id} - {resume_options[item_id]}"
                    ),
                    key=f"job_match_resume_{job_id}",
                )

                if st.button("Analyze Match", key=f"job_match_run_{job_id}"):
                    try:
                        match_response = api.post(
                            f"/api/v1/jobs/{job_id}/match",
                            {"resume_id": selected_resume_id},
                        )
                        data = (
                            match_response.data
                            if isinstance(match_response.data, dict)
                            else {}
                        )
                        st.success("Match analysis completed.")
                        _render_match_result(data)
                    except ApiClientError as exc:
                        st.error(str(exc))

                if st.button("Prepare Application", key=f"job_prepare_{job_id}"):
                    selected_resume = next(
                        (
                            item
                            for item in resumes
                            if int(item.get("id", 0)) == selected_resume_id
                        ),
                        None,
                    )
                    if not isinstance(selected_resume, dict) or not isinstance(
                        selected_resume.get("profile_id"), int
                    ):
                        st.error("Selected resume is missing a valid profile mapping.")
                    else:
                        try:
                            payload = {
                                "job_id": job_id,
                                "profile_id": int(selected_resume["profile_id"]),
                                "resume_id": selected_resume_id,
                            }
                            response = api.post("/api/v1/applications/prepare", payload)
                            data = (
                                response.data if isinstance(response.data, dict) else {}
                            )
                            app_id = data.get("application_id")
                            st.success(
                                "Application prepared and moved to READY_FOR_REVIEW"
                                + (f" (Application #{app_id})" if app_id else "")
                            )
                            st.rerun()
                        except ApiClientError as exc:
                            st.error(str(exc))

                try:
                    matches_response = api.get(f"/api/v1/jobs/{job_id}/matches")
                    matches = (
                        matches_response.data
                        if isinstance(matches_response.data, list)
                        else []
                    )
                    if matches:
                        st.write("Saved Matches")
                        for match in matches:
                            if isinstance(match, dict):
                                with st.container(border=True):
                                    _render_match_result(match)
                except ApiClientError as exc:
                    st.error(str(exc))

        with st.expander(f"Edit job #{job_id}"):
            with st.form(f"update_job_form_{job_id}"):
                update_payload = {
                    "title": st.text_input(
                        "Job title *",
                        value=job.get("title") or "",
                        key=f"job_title_{job_id}",
                    ),
                    "company": st.text_input(
                        "Company *",
                        value=job.get("company") or "",
                        key=f"job_company_{job_id}",
                    ),
                    "location": st.text_input(
                        "Location",
                        value=job.get("location") or "",
                        key=f"job_location_{job_id}",
                    ),
                    "url": st.text_input(
                        "Job URL",
                        value=job.get("url") or "",
                        key=f"job_url_{job_id}",
                    ),
                    "employment_type": st.text_input(
                        "Employment type",
                        value=job.get("employment_type") or "",
                        key=f"job_employment_{job_id}",
                    ),
                    "description": st.text_area(
                        "Job description *",
                        value=job.get("description") or "",
                        height=180,
                        key=f"job_description_edit_{job_id}",
                    ),
                }

                update_submitted = st.form_submit_button("Update Job")
                if update_submitted:
                    try:
                        clean_update_payload = {
                            key: value
                            for key, value in update_payload.items()
                            if value not in ("", None)
                        }
                        api.put(f"/api/v1/jobs/{job_id}", clean_update_payload)
                        st.success("Job updated.")
                        st.rerun()
                    except ApiClientError as exc:
                        st.error(str(exc))

        if st.button("Delete Job", key=f"job_delete_{job_id}"):
            try:
                api.delete(f"/api/v1/jobs/{job_id}")
                st.success("Job deleted.")
                st.rerun()
            except ApiClientError as exc:
                st.error(str(exc))


def _render_job_analysis(payload: dict[str, object]) -> None:
    status = str(payload.get("analysis_status") or "NOT_ANALYZED")
    analyzed_at = payload.get("analyzed_at") or "-"
    st.write(f"Latest status: {status}")
    st.write(f"Analyzed at: {analyzed_at}")

    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        st.info("No analysis stored for this job yet.")
        return

    st.write(f"Role Summary: {analysis.get('role_summary') or '-'}")
    st.write(f"Seniority: {analysis.get('seniority_level') or '-'}")
    st.write(f"Employment Type: {analysis.get('employment_type') or '-'}")
    st.write(f"Work Arrangement: {analysis.get('work_arrangement') or '-'}")
    st.write(f"Location: {analysis.get('location') or '-'}")
    st.write(
        "Experience: "
        f"minimum={analysis.get('minimum_years_experience')}, "
        f"preferred={analysis.get('preferred_years_experience')}"
    )

    _render_skill_list("Required Skills", analysis.get("required_skills"))
    _render_skill_list("Preferred Skills", analysis.get("preferred_skills"))

    _render_text_list(
        "Experience Requirements",
        analysis.get("experience_requirements"),
    )
    _render_text_list(
        "Education Requirements",
        analysis.get("education_requirements"),
    )
    _render_text_list(
        "Required Certifications",
        analysis.get("required_certifications"),
    )
    _render_text_list(
        "Preferred Certifications",
        analysis.get("preferred_certifications"),
    )
    _render_text_list("Responsibilities", analysis.get("responsibilities"))
    _render_text_list("Domain Requirements", analysis.get("domain_requirements"))
    _render_text_list(
        "Communication Requirements",
        analysis.get("communication_requirements"),
    )
    _render_text_list(
        "Leadership Requirements",
        analysis.get("leadership_requirements"),
    )
    _render_text_list(
        "Work Authorization Requirements",
        analysis.get("work_authorization_requirements"),
    )
    _render_text_list("Travel Requirements", analysis.get("travel_requirements"))
    _render_text_list("Other Requirements", analysis.get("other_requirements"))


def _render_skill_list(title: str, skills: object) -> None:
    st.write(title)
    if isinstance(skills, list) and skills:
        for skill in skills:
            if isinstance(skill, dict):
                name = skill.get("name") or "-"
                category = skill.get("category") or "other"
                st.write(f"- {name} ({category})")
    else:
        st.write("- None")


def _render_text_list(title: str, items: object) -> None:
    st.write(title)
    if isinstance(items, list) and items:
        for item in items:
            if isinstance(item, dict):
                requirement = item.get("requirement") or "-"
                min_years = item.get("minimum_years")
                pref_years = item.get("preferred_years")
                st.write(
                    f"- {requirement} "
                    f"(min_years={min_years}, preferred_years={pref_years})"
                )
            else:
                st.write(f"- {item}")
    else:
        st.write("- None")


def _render_match_result(payload: dict[str, object]) -> None:
    score = payload.get("score")
    if isinstance(score, int):
        st.write(f"Match Score: {score} / 100")

    st.write("Required Skills")
    _render_checklist(
        matched=payload.get("matched_required_skills"),
        missing=payload.get("missing_required_skills"),
    )

    st.write("Preferred Skills")
    _render_checklist(
        matched=payload.get("matched_preferred_skills"),
        missing=payload.get("missing_preferred_skills"),
    )

    st.write(f"Experience: {payload.get('experience_result') or 'UNKNOWN'}")
    st.write(f"Education: {payload.get('education_result') or 'UNKNOWN'}")
    st.write(f"Certification: {payload.get('certification_result') or 'UNKNOWN'}")

    strengths = payload.get("strengths")
    st.write("Strengths")
    if isinstance(strengths, list) and strengths:
        for item in strengths:
            st.write(f"- {item}")
    else:
        st.write("- None")

    gaps = payload.get("gaps")
    st.write("Gaps")
    if isinstance(gaps, list) and gaps:
        for item in gaps:
            st.write(f"- {item}")
    else:
        st.write("- None")


def _render_checklist(matched: object, missing: object) -> None:
    if isinstance(matched, list):
        for item in matched:
            st.write(f"- [matched] {item}")

    if isinstance(missing, list):
        for item in missing:
            st.write(f"- [missing] {item}")

    if (not isinstance(matched, list) or not matched) and (
        not isinstance(missing, list) or not missing
    ):
        st.write("- None")


def _render_import_result(payload: object) -> None:
    if not isinstance(payload, dict):
        st.success("Import completed.")
        return

    imported = payload.get("imported_count") or 0
    skipped = payload.get("skipped_count") or 0
    failed = payload.get("failed_count") or 0
    st.success(
        f"Import completed: imported={imported}, skipped={skipped}, failed={failed}"
    )

    records = payload.get("records")
    if isinstance(records, list) and records:
        with st.expander("Import details", expanded=False):
            for item in records:
                if not isinstance(item, dict):
                    continue
                status = item.get("status") or "UNKNOWN"
                title = item.get("title") or "-"
                company = item.get("company") or "-"
                job_id = item.get("job_id") or "-"
                error = item.get("error") or "-"
                st.write(
                    f"- [{status}] {title} @ {company} | job_id={job_id} | {error}"
                )


def _render_find_jobs_section(
    api: ApiClient,
    analyzed_resumes: list[dict[str, object]],
) -> None:
    st.subheader("Find Jobs")
    st.caption(
        "Use an analyzed resume to discover jobs, analyze them, and rank the best "
        "matches automatically."
    )

    if not analyzed_resumes:
        st.info("Analyze at least one resume before running job discovery.")
        return

    resume_options = {
        int(item["id"]): str(item.get("name") or f"Resume #{item['id']}")
        for item in analyzed_resumes
        if isinstance(item.get("id"), int)
    }
    source_options = ["remotive", "web_search"]

    with st.form("discover_jobs_form"):
        selected_resume_id = st.selectbox(
            "Analyzed resume",
            options=list(resume_options.keys()),
            format_func=lambda item_id: f"#{item_id} - {resume_options[item_id]}",
        )
        selected_sources = st.multiselect(
            "Sources",
            options=source_options,
            default=["remotive"],
        )
        max_results = st.slider(
            "Max results per source",
            min_value=1,
            max_value=25,
            value=10,
        )
        requested_min_score = st.slider(
            "Initial minimum match score",
            min_value=0,
            max_value=100,
            value=50,
        )
        submitted = st.form_submit_button("Find Matching Jobs")

    if submitted:
        try:
            response = api.post(
                "/api/v1/jobs/discover",
                {
                    "resume_id": selected_resume_id,
                    "sources": selected_sources or source_options,
                    "max_results_per_source": max_results,
                    "min_match_score": requested_min_score,
                },
            )
            payload = response.data if isinstance(response.data, dict) else {}
            st.session_state["job_discovery_results"] = payload
        except ApiClientError as exc:
            st.error(str(exc))

    payload = st.session_state.get("job_discovery_results")
    if not isinstance(payload, dict):
        return

    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    if not results:
        st.info("No matching jobs found yet for the latest discovery run.")
        _render_discovery_errors(payload)
        return

    available_sources = sorted(
        {
            str(item.get("source"))
            for item in results
            if isinstance(item, dict) and item.get("source")
        }
    )

    st.write(
        f"Discovered {payload.get('total_discovered', 0)} jobs, "
        f"deduplicated to {payload.get('total_deduplicated', 0)}, "
        f"matched {payload.get('total_matched', 0)}."
    )

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        min_score = st.slider(
            "Filter by match score",
            min_value=0,
            max_value=100,
            value=50,
            key="discovery_filter_min_score",
        )
    with filter_col2:
        selected_source_filter = st.multiselect(
            "Filter by source",
            options=available_sources,
            default=available_sources,
            key="discovery_filter_sources",
        )
    with filter_col3:
        location_filter = (
            st.text_input(
                "Filter by location",
                key="discovery_filter_location",
            )
            .strip()
            .lower()
        )

    filtered_results = []
    for item in results:
        if not isinstance(item, dict):
            continue
        score = int(item.get("match_score") or 0)
        source = str(item.get("source") or "")
        location = str(item.get("location") or "")
        if score < min_score:
            continue
        if selected_source_filter and source not in selected_source_filter:
            continue
        if location_filter and location_filter not in location.lower():
            continue
        filtered_results.append(item)

    for item in filtered_results:
        _render_discovery_result_card(item)

    _render_discovery_errors(payload)


def _render_discovery_result_card(item: dict[str, object]) -> None:
    with st.container(border=True):
        title = str(item.get("title") or "Untitled role")
        company = str(item.get("company") or "Unknown company")
        score = int(item.get("match_score") or 0)
        location = str(item.get("location") or "Location not specified")
        sources = item.get("discovered_sources")
        source_labels = (
            ", ".join(sources)
            if isinstance(sources, list)
            else str(item.get("source") or "-")
        )

        st.markdown(f"### {title}")
        st.caption(company)
        st.write(f"Match Score: {score} / 100")
        st.write(f"Location: {location}")
        st.write(f"Source: {source_labels}")

        match_payload = item.get("match")
        if isinstance(match_payload, dict):
            strengths = match_payload.get("strengths")
            if isinstance(strengths, list) and strengths:
                st.write("Strengths")
                for strength in strengths[:3]:
                    st.write(f"- {strength}")

            gaps = match_payload.get("gaps")
            if isinstance(gaps, list) and gaps:
                st.write("Gaps")
                for gap in gaps[:2]:
                    st.write(f"- {gap}")

        action = str(item.get("action") or "OPEN_AND_APPLY")
        action_url = item.get("action_url")
        if isinstance(action_url, str) and action_url:
            st.link_button(
                "Apply" if action == "APPLY" else "Open & Apply",
                action_url,
            )


def _render_discovery_errors(payload: dict[str, object]) -> None:
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return

    with st.expander("Discovery warnings", expanded=False):
        for item in errors:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or "source"
            message = item.get("message") or "-"
            st.write(f"- {source}: {message}")
