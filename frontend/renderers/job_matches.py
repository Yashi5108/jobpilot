from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api_client import ApiClient, ApiClientError


def render_job_matches(api: ApiClient) -> None:
    """Display all jobs ranked by match score against resumes."""
    st.header("Job Matches")
    st.caption(
        "Executive view of opportunity fit, skill alignment, and hiring readiness."
    )

    try:
        jobs_response = api.get("/api/v1/jobs")
        jobs = jobs_response.data if isinstance(jobs_response.data, list) else []
    except ApiClientError as exc:
        st.error(f"Failed to load jobs: {exc}")
        return

    if not jobs:
        st.info("No jobs found yet. Start by uploading a resume and searching for jobs.")
        return

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

    all_matches.sort(key=lambda m: float(m.get("match_score") or 0), reverse=True)

    st.sidebar.markdown("### Match Filters")
    min_score = st.sidebar.slider("Minimum Match Score", 0, 100, 0)
    min_skill_overlap = st.sidebar.slider("Min Matched Skills", 0, 12, 0)
    role_level_options = ["Entry", "Mid", "Senior", "Lead"]
    selected_levels = st.sidebar.multiselect(
        "Role level",
        role_level_options,
        default=role_level_options,
    )
    location_options = sorted({
        str((match.get("job") or {}).get("location") or "Remote")
        for match in all_matches
    })
    selected_locations = st.sidebar.multiselect(
        "Location",
        location_options,
        default=location_options,
    )
    skill_mix = st.sidebar.selectbox(
        "Skill mix",
        ["Any", "Balanced", "Skill-dense", "Gap-aware"],
        index=0,
    )
    sort_mode = st.sidebar.selectbox(
        "Sort by",
        ["Top match score", "Most matched skills", "Newest / current order"],
        index=0,
    )
    bucket_filter = st.sidebar.radio("Score bucket", ["All", "Excellent", "Good", "Fair", "Low"], horizontal=True)

    def match_role_level(job: dict) -> str:
        title = str(job.get("title") or "").lower()
        if any(keyword in title for keyword in ["lead", "staff", "principal", "director", "head", "senior"]):
            return "Senior"
        if any(keyword in title for keyword in ["junior", "entry", "associate"]):
            return "Entry"
        if any(keyword in title for keyword in ["manager", "architect"]):
            return "Lead"
        return "Mid"

    def compute_breakdown(match: dict) -> dict[str, float]:
        score = float(match.get("match_score") or 0)
        job = match.get("job", {}) or {}
        matched = list(match.get("matched_skills") or [])
        missing = list(match.get("missing_skills") or [])
        title = str(job.get("title") or "").lower()

        role_fit = max(0.0, min(100.0, score + (7 if matched else -12)))
        skill_fit = max(0.0, min(100.0, score * 0.9 + len(matched) * 5))
        readiness = max(0.0, min(100.0, score * 0.8 + (20 if not missing else 0)))
        opportunity = max(0.0, min(100.0, score * 0.7 + (12 if "senior" in title or "lead" in title else 5)))
        return {
            "Role fit": round(role_fit, 1),
            "Skill fit": round(skill_fit, 1),
            "Readiness": round(readiness, 1),
            "Opportunity": round(opportunity, 1),
        }

    filtered_matches = []
    for match in all_matches:
        job = match.get("job", {}) or {}
        score = float(match.get("match_score") or 0)
        title = str(job.get("title") or "")
        location = str(job.get("location") or "Remote")
        level = match_role_level(job)

        if score < min_score:
            continue
        if len(match.get("matched_skills") or []) < min_skill_overlap:
            continue
        if selected_levels and level not in selected_levels:
            continue
        if selected_locations and location not in selected_locations:
            continue

        matched_skills = list(match.get("matched_skills") or [])
        missing_skills = list(match.get("missing_skills") or [])
        if skill_mix == "Balanced" and (len(matched_skills) < 2 or len(missing_skills) > 3):
            continue
        if skill_mix == "Skill-dense" and len(matched_skills) < 4:
            continue
        if skill_mix == "Gap-aware" and len(missing_skills) == 0:
            continue
        filtered_matches.append(match)

    if sort_mode == "Most matched skills":
        filtered_matches.sort(
            key=lambda m: (len(m.get("matched_skills") or []), float(m.get("match_score") or 0)),
            reverse=True,
        )
    elif sort_mode == "Newest / current order":
        filtered_matches = filtered_matches
    else:
        filtered_matches.sort(key=lambda m: float(m.get("match_score") or 0), reverse=True)

    if bucket_filter != "All":
        bucket_map = {
            "Excellent": (80, 100),
            "Good": (60, 79),
            "Fair": (40, 59),
            "Low": (0, 39),
        }
        lower, upper = bucket_map[bucket_filter]
        filtered_matches = [
            m for m in filtered_matches if lower <= float(m.get("match_score") or 0) <= upper
        ]

    top_match = max(filtered_matches, key=lambda m: float(m.get("match_score") or 0), default=None)
    avg_score = round(sum(float(m.get("match_score") or 0) for m in filtered_matches) / len(filtered_matches), 1) if filtered_matches else 0
    strong_fit_count = sum(1 for m in filtered_matches if float(m.get("match_score") or 0) >= 80)

    st.markdown(
        """
        <div class="analytics-shell">
            <div class="mini-label" style="margin-bottom: 0.4rem;">Executive summary</div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.8rem;">
                <div class="analytics-tile">
                    <div class="kicker">Tracked roles</div>
                    <div class="value">{total}</div>
                    <div style="color: #cbd5e1; font-size: 0.8rem;">Matches in view</div>
                </div>
                <div class="analytics-tile">
                    <div class="kicker">Avg fit</div>
                    <div class="value">{avg}</div>
                    <div style="color: #cbd5e1; font-size: 0.8rem;">Composite match score</div>
                </div>
                <div class="analytics-tile">
                    <div class="kicker">Strong fit</div>
                    <div class="value">{strong}</div>
                    <div style="color: #cbd5e1; font-size: 0.8rem;">80%+ opportunities</div>
                </div>
                <div class="analytics-tile">
                    <div class="kicker">Top priority</div>
                    <div style="font-size: 1.18rem; font-weight: 800; margin-top: 0.3rem;">{top}</div>
                    <div style="color: #cbd5e1; font-size: 0.8rem;">{top_score}</div>
                </div>
            </div>
        </div>
        """.format(
            total=len(filtered_matches),
            avg=f"{avg_score:.1f}%",
            strong=strong_fit_count,
            top=(top_match.get("job", {}).get("title") or "No priority") if top_match else "No priority",
            top_score=f"{float(top_match.get('match_score') or 0):.0f}% match" if top_match else "No data",
        ),
        unsafe_allow_html=True,
    )

    st.subheader(f"Ranked Matches ({len(filtered_matches)} of {len(all_matches)})")

    if filtered_matches:
        leaderboard_rows = []
        for match in filtered_matches[:10]:
            job = match.get("job", {}) or {}
            score = float(match.get("match_score") or 0)
            leaderboard_rows.append(
                {
                    "Rank": len(leaderboard_rows) + 1,
                    "Role": job.get("title") or "Unknown role",
                    "Company": job.get("company") or "Unknown company",
                    "Match": round(score, 1),
                    "Skill overlap": len(match.get("matched_skills") or []),
                    "Location": job.get("location") or "Remote",
                }
            )

        leaderboard_df = pd.DataFrame(leaderboard_rows)
        leaderboard_cols = st.columns([1.8, 1])
        with leaderboard_cols[0]:
            st.markdown("<div class='mini-label'>Top opportunities</div>", unsafe_allow_html=True)
            st.dataframe(
                leaderboard_df[["Rank", "Role", "Company", "Match"]].rename(columns={"Match": "Fit %"}),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Rank": st.column_config.NumberColumn("Rank", width="small"),
                    "Role": st.column_config.TextColumn("Role", width="large"),
                    "Company": st.column_config.TextColumn("Company", width="medium"),
                    "Fit %": st.column_config.ProgressColumn("Fit %", min_value=0, max_value=100, format="%f%"),
                },
            )

        with leaderboard_cols[1]:
            scatter_df = pd.DataFrame(
                [
                    {
                        "match_score": float(match.get("match_score") or 0),
                        "skill_overlap": len(match.get("matched_skills") or []),
                        "skill_gap": len(match.get("missing_skills") or []),
                        "company": (match.get("job") or {}).get("company") or "Unknown",
                        "role": (match.get("job") or {}).get("title") or "Unknown",
                    }
                    for match in filtered_matches
                ]
            )
            if not scatter_df.empty:
                st.markdown("<div class='mini-label'>Match score map</div>", unsafe_allow_html=True)
                st.scatter_chart(
                    scatter_df,
                    x="skill_overlap",
                    y="match_score",
                    size="skill_gap",
                    color="match_score",
                )

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
                breakdown = compute_breakdown(match)

                with st.container(border=True):
                    col1, col2, col3 = st.columns([3.1, 1.2, 1.2])

                    with col1:
                        st.markdown(
                            f"""
                            <div style="display:flex; align-items:center; justify-content:space-between; gap: 0.75rem; flex-wrap: wrap;">
                                <div>
                                    <div class="mini-label" style="margin-bottom: 0.25rem;">Priority role</div>
                                    <div style="font-size: 1.3rem; font-weight: 800;">{job.get('title', 'Unknown Job')}</div>
                                </div>
                                <span class="status-pill {'primary' if score >= 80 else 'warning' if score >= 60 else 'danger'}">{score:.0f}% fit</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.caption(f"{job.get('company', 'Unknown')} • {job.get('location', 'Remote')}")

                    with col2:
                        st.metric("Match", f"{score:.0f}%")

                    with col3:
                        if job.get("url"):
                            st.link_button(
                                "View Job",
                                url=job["url"],
                                use_container_width=True,
                            )

                    score_cols = st.columns(4)
                    for col, (label, value) in zip(score_cols, breakdown.items()):
                        with col:
                            st.markdown(
                                f"""
                                <div class="analytics-panel">
                                    <div class="mini-label">{label}</div>
                                    <div style="font-size: 1.25rem; font-weight: 800; margin-bottom: 0.5rem;">{value:.1f}</div>
                                    <div class="score-bar"><div style="width:{min(100, max(0, value))}%"></div></div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

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

                    if st.button(
                        "→ Prepare Application",
                        key=f"prepare_{job.get('id')}_{idx}",
                        use_container_width=True,
                    ):
                        st.session_state["selected_job_id"] = job.get("id")
                        st.session_state["selected_job"] = job
                        st.session_state["jobpilot_selected_page"] = "Applications"
                        st.rerun()
