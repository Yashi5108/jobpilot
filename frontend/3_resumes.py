import streamlit as st

from frontend.api_client import ApiClient
from frontend.pages.resumes import render_resumes

st.set_page_config(page_title="JobPilot Resumes", layout="wide", page_icon="📄")
st.title("JobPilot")
st.caption("AI Job Search & Application Assistant")

api_client = ApiClient()
render_resumes(api_client)
