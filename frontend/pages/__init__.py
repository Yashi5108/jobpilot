"""Page renderers for JobPilot Streamlit frontend."""

from frontend.pages.applications import render_applications
from frontend.pages.dashboard import render_dashboard
from frontend.pages.jobs import render_jobs
from frontend.pages.profile import render_profile
from frontend.pages.resumes import render_resumes

__all__ = [
    "render_applications",
    "render_dashboard",
    "render_jobs",
    "render_profile",
    "render_resumes",
]
