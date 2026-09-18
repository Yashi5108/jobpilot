from __future__ import annotations

import streamlit as st

from frontend.api_client import ApiClient, ApiClientError


def _parse_optional_float(value: str) -> float | None:
    if not value:
        return None
    return float(value)


def _profile_payload(
    prefix: str,
    defaults: dict | None = None,
) -> dict[str, str | float | None]:
    defaults = defaults or {}

    years_value = st.text_input(
        "Years of experience",
        value=str(defaults.get("years_of_experience") or ""),
        key=f"{prefix}_yoe",
    )
    salary_value = st.text_input(
        "Minimum salary",
        value=str(defaults.get("minimum_salary") or ""),
        key=f"{prefix}_salary",
    )

    return {
        "name": st.text_input(
            "Name",
            value=defaults.get("name") or "",
            key=f"{prefix}_name",
        )
        or None,
        "email": st.text_input(
            "Email",
            value=defaults.get("email") or "",
            key=f"{prefix}_email",
        )
        or None,
        "phone": st.text_input(
            "Phone",
            value=defaults.get("phone") or "",
            key=f"{prefix}_phone",
        )
        or None,
        "location": st.text_input(
            "Location",
            value=defaults.get("location") or "",
            key=f"{prefix}_location",
        )
        or None,
        "years_of_experience": _parse_optional_float(years_value),
        "notice_period": st.text_input(
            "Notice period",
            value=defaults.get("notice_period") or "",
            key=f"{prefix}_notice",
        )
        or None,
        "minimum_salary": _parse_optional_float(salary_value),
        "remote_preference": st.text_input(
            "Remote preference",
            value=defaults.get("remote_preference") or "",
            key=f"{prefix}_remote",
        )
        or None,
        "work_authorization": st.text_input(
            "Work authorization",
            value=defaults.get("work_authorization") or "",
            key=f"{prefix}_authorization",
        )
        or None,
    }


def render_profile(api: ApiClient) -> None:
    st.header("Profile")

    try:
        response = api.get("/api/v1/profile")
        profile = response.data
    except ApiClientError as exc:
        if exc.status_code == 404:
            profile = None
        else:
            st.error(str(exc))
            return

    if profile is None:
        st.info("No profile found yet. Create your JobPilot profile to get started.")
        with st.form("create_profile_form"):
            payload = _profile_payload("create")
            submitted = st.form_submit_button("Create Profile")
            if submitted:
                try:
                    api.post("/api/v1/profile", payload)
                    st.success("Profile created.")
                    st.rerun()
                except ValueError:
                    st.error("Years of experience and minimum salary must be numbers.")
                except ApiClientError as exc:
                    st.error(str(exc))
        return

    st.subheader("Current Profile")
    st.json(profile)

    with st.form("update_profile_form"):
        st.caption("Update profile")
        payload = _profile_payload("update", defaults=profile)
        submitted = st.form_submit_button("Save Changes")
        if submitted:
            try:
                api.put("/api/v1/profile", payload)
                st.success("Profile updated.")
                st.rerun()
            except ValueError:
                st.error("Years of experience and minimum salary must be numbers.")
            except ApiClientError as exc:
                st.error(str(exc))
