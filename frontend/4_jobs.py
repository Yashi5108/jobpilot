import streamlit as st

from frontend.api_client import ApiClient
from frontend.pages.jobs import render_jobs

st.set_page_config(page_title="JobPilot Jobs", layout="wide", page_icon="💼")
st.title("JobPilot")
st.caption("AI Job Search & Application Assistant")

api_client = ApiClient()
render_jobs(api_client)
