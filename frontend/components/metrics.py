from __future__ import annotations

import streamlit as st


def metric_row(items: list[tuple[str, int]]) -> None:
    columns = st.columns(len(items))
    for index, (label, value) in enumerate(items):
        columns[index].metric(label=label, value=value)
