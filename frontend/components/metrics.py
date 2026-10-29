from __future__ import annotations

import streamlit as st


def metric_row(items: list[tuple[str, object]]) -> None:
    columns = st.columns(len(items))
    for index, (label, value) in enumerate(items):
        with columns[index]:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
