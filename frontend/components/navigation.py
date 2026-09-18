from __future__ import annotations

import streamlit as st

PAGES = ["Dashboard", "Profile", "Resumes", "Jobs", "Applications"]


def render_sidebar_navigation() -> str:
    with st.sidebar:
        st.title("JobPilot")
        st.caption("AI Job Search & Application Assistant")
        return st.radio("Navigate", options=PAGES, label_visibility="collapsed")
