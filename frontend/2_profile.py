import streamlit as st

from frontend.api_client import ApiClient
from frontend.pages.profile import render_profile

st.set_page_config(page_title="JobPilot Profile", layout="wide", page_icon="👤")
st.title("JobPilot")
st.caption("AI Job Search & Application Assistant")

api_client = ApiClient()
render_profile(api_client)
