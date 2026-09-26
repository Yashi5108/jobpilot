from __future__ import annotations

import streamlit as st

from frontend.api_client import ApiClient, ApiClientError
from frontend.components.cards import job_card


def render_job_matches(api: ApiClient) -> None:
    """Display all jobs ranked by match score against resumes."""
    st.header("Job Matches")
    st.caption(
        "View all jobs ranked by match score. Highest scores indicate best alignment "
        "with your profile and skills."
    )

    # Fetch all jobs
    try:
        jobs_response = api.get("/api/v1/jobs")
        jobs = jobs_response.data if isinstance(jobs_response.data, list) else []
    except ApiClientError as exc:
        st.error(f"Failed to load jobs: {exc}")
        return

    if not jobs:
        st.info("No jobs found yet. Start by uploading a resume and searching for jobs.")
        return

    # Collect all matches
    all_matches = []
    for job in jobs:
        job_id = job.get("id")
        try:
            matches_response = api.get(f"/api/v1/jobs/{job_id}/matches")
            matches = (
                matches_response.data
                if isinstance(matches_response.data, list)
                else []
            )
            for match in matches:
                if isinstance(match, dict):
                    match["job"] = job
                    all_matches.append(match)
        except ApiClientError:
            pass

    if not all_matches:
        st.info(
            "No matches yet. Upload a resume to calculate match scores with available jobs."
        )
        return

    # Sort by match score (descending)
    all_matches.sort(
        key=lambda m: float(m.get("match_score") or 0), reverse=True
    )

    # Sidebar filters
    st.sidebar.markdown("### Match Filters")
    min_score = st.sidebar.slider("Minimum Match Score", 0, 100, 0)
    
    # Filter matches
    filtered_matches = [
        m for m in all_matches
        if float(m.get("match_score") or 0) >= min_score
    ]

    st.subheader(f"Ranked Matches ({len(filtered_matches)} of {len(all_matches)})")

    # Display matches with tabs by score range
    score_ranges = [
        ("🟢 Excellent (80+)", 80, 100),
        ("🟡 Good (60-79)", 60, 79),
        ("🟠 Fair (40-59)", 40, 59),
        ("🔴 Low (0-39)", 0, 39),
    ]

    tabs = st.tabs([label for label, _, _ in score_ranges])

    for tab, (label, min_val, max_val) in zip(tabs, score_ranges):
        with tab:
            range_matches = [
                m for m in filtered_matches
                if min_val <= float(m.get("match_score") or 0) <= max_val
            ]
            
            if not range_matches:
                st.info(f"No matches in {label} range.")
                continue

            for idx, match in enumerate(range_matches, 1):
                job = match.get("job", {})
                score = float(match.get("match_score") or 0)
                
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.subheader(job.get("title", "Unknown Job"))
                        st.caption(f"{job.get('company', 'Unknown')} • {job.get('location', 'Remote')}")
                    
                    with col2:
                        st.metric("Match Score", f"{score:.0f}%")
                    
                    with col3:
                        if job.get("url"):
                            st.link_button(
                                "View Job", 
                                url=job["url"],
                                use_container_width=True
                            )

                    # Match details
                    expander_key = f"match_{job.get('id')}_{idx}"
                    with st.expander("Match Details & Reasoning"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**Matched Skills:**")
                            matched_skills = match.get("matched_skills", [])
                            if matched_skills:
                                for skill in matched_skills:
                                    st.write(f"- {skill}")
                            else:
                                st.write("- (none)")
                        
                        with col2:
                            st.write("**Missing Skills:**")
                            missing_skills = match.get("missing_skills", [])
                            if missing_skills:
                                for skill in missing_skills:
                                    st.write(f"- {skill}")
                            else:
                                st.write("- (none)")
                        
                        if match.get("reasoning"):
                            st.write("**Analysis:**")
                            st.write(match["reasoning"])
                    
                    # Prepare application button
                    if st.button(
                        "→ Prepare Application",
                        key=f"prepare_{job.get('id')}_{idx}",
                        use_container_width=True,
                    ):
                        st.session_state["selected_job_id"] = job.get("id")
                        st.session_state["selected_job"] = job
                        st.switch_page("pages/6_applications.py")
