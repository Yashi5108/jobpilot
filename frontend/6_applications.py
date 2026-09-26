import streamlit as st

from frontend.api_client import ApiClient
from frontend.pages.applications import render_applications

st.set_page_config(page_title="JobPilot Applications", layout="wide", page_icon="📋")
st.title("JobPilot")
st.caption("AI Job Search & Application Assistant")

api_client = ApiClient()
render_applications(api_client)
