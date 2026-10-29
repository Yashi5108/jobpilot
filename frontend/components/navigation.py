from __future__ import annotations

import streamlit as st

PAGES = [
    "Dashboard",
    "Profile",
    "Resumes",
    "Jobs",
    "Job Matches",
    "Applications",
]


def render_sidebar_navigation() -> str:
    default_page = st.session_state.get("jobpilot_selected_page", "Dashboard")
    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 0.5rem 0.2rem 0.8rem;">
                <div style="display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.4rem;">
                    <div style="width: 34px; height: 34px; border-radius: 12px; background: linear-gradient(135deg, #8b5cf6, #22d3ee, #ec4899); display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 0.8rem; color: white;">JP</div>
                    <div>
                        <div style="font-weight: 900; letter-spacing: -0.04em; font-size: 1.2rem;">JobPilot</div>
                        <div style="color: #b7c6de; font-size: 0.72rem;">job mode: on</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("AI job search + application flow")
        st.markdown("---")
        selected = st.radio(
            "Navigate",
            options=PAGES,
            index=PAGES.index(default_page) if default_page in PAGES else 0,
            label_visibility="collapsed",
            horizontal=False,
            key="jobpilot_navigation",
        )
        st.session_state["jobpilot_selected_page"] = selected
        return selected
