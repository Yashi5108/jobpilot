import streamlit as st


def main() -> None:
    st.set_page_config(page_title="JobPilot", layout="wide")
    st.title("JobPilot")
    st.caption("AI Job Search & Application Assistant")

    st.subheader("Dashboard")
    st.write("Find Jobs")
    st.write("Applications")
    st.write("Resumes")
    st.write("Profile")
    st.write("Settings")


if __name__ == "__main__":
    main()
