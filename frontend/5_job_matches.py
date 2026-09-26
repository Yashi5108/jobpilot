import streamlit as st

from frontend.api_client import ApiClient
from frontend.pages.job_matches import render_job_matches

st.set_page_config(page_title="JobPilot Job Matches", layout="wide", page_icon="⭐")
st.title("JobPilot")
st.caption("AI Job Search & Application Assistant")

api_client = ApiClient()
render_job_matches(api_client)
