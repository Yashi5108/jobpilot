import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.navigation import render_sidebar_navigation
from frontend.pages.applications import render_applications
from frontend.pages.dashboard import render_dashboard
from frontend.pages.jobs import render_jobs
from frontend.pages.profile import render_profile
from frontend.pages.resumes import render_resumes


def main() -> None:
    st.set_page_config(page_title="JobPilot", layout="wide", page_icon="JP")
    st.title("JobPilot")
    st.caption("AI Job Search & Application Assistant")

    api_client = ApiClient()
    selected_page = render_sidebar_navigation()

    if selected_page == "Dashboard":
        render_dashboard(api_client)
    elif selected_page == "Profile":
        render_profile(api_client)
    elif selected_page == "Resumes":
        render_resumes(api_client)
    elif selected_page == "Jobs":
        render_jobs(api_client)
    elif selected_page == "Applications":
        render_applications(api_client)
    else:
        st.error("Unknown page selected.")


if __name__ == "__main__":
    main()
