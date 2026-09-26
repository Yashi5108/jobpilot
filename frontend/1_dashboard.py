import streamlit as st

from frontend.api_client import ApiClient
from frontend.pages.dashboard import render_dashboard

st.set_page_config(page_title="JobPilot Dashboard", layout="wide", page_icon="📊")
st.title("JobPilot")
st.caption("AI Job Search & Application Assistant")

api_client = ApiClient()
render_dashboard(api_client)
