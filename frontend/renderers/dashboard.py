from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api_client import ApiClient, ApiClientError
from frontend.components.metrics import metric_row


def _build_operator_run_history(raw_events: list[dict[str, object]]) -> list[dict[str, object]]:
    history = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        timestamp = str(event.get("timestamp") or "Pending")
        action = str(event.get("action") or "Automation step")
        status = str(event.get("status") or "Queued")
        history.append({
            "timestamp": timestamp,
            "action": action,
            "status": status,
        })
    return sorted(
        history,
        key=lambda item: (item["timestamp"], item["action"]),
        reverse=True,
    )


def render_dashboard(api: ApiClient) -> None:
    jobs_found = 0
    shortlisted = 0
    applications_count = 0
    interviews = 0
    offers = 0
    rejected = 0
    average_match = None
    top_missing: list[str] = []

    try:
        analytics_response = api.get("/api/v1/analytics/overview")
        analytics = (
            analytics_response.data if isinstance(analytics_response.data, dict) else {}
        )

        jobs_found = int(analytics.get("jobs_found") or 0)
        shortlisted = int(analytics.get("shortlisted_jobs") or 0)
        applications_count = int(analytics.get("applications") or 0)
        interviews = int(analytics.get("interviews") or 0)
        offers = int(analytics.get("offers") or 0)
        rejected = int(analytics.get("rejected") or 0)
        raw_avg = analytics.get("average_match_score")
        average_match = round(float(raw_avg), 1) if raw_avg is not None else None

        missing = analytics.get("frequently_missing_skills")
        if isinstance(missing, list):
            top_missing = [
                str(item.get("skill"))
                for item in missing
                if isinstance(item, dict) and item.get("skill")
            ][:5]
    except ApiClientError as exc:
        st.warning(str(exc))

    st.markdown(
        """
        <div class="creator-strip">
            <div style="display:flex; align-items:center; gap:0.8rem; flex-wrap:wrap;">
                <span class="creator-badge">Creator dashboard</span>
                <div style="font-size:1.15rem; font-weight:800; letter-spacing:-0.04em;">Your pipeline is trending up.</div>
            </div>
            <div class="creator-pill-group">
                <span class="creator-pill primary">● Live</span>
                <span class="creator-pill success">+14% this month</span>
                <span class="creator-pill">1.2k reach</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    engagement = st.columns(4)
    for col, (label, value, note) in zip(engagement, [
        ("Engagement", "8.4k", "views this week"),
        ("Qualified", "214", "high-fit opportunities"),
        ("Conversion", "31%", "apply-to-screen rate"),
        ("Momentum", "+14%", "vs last cycle"),
    ]):
        with col:
            st.markdown(
                f"""
                <div class="engagement-card">
                    <div class="engagement-label">{label}</div>
                    <div class="engagement-value">{value}</div>
                    <div class="engagement-note">{note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    hero_left, hero_right = st.columns([1.8, 1.1])
    with hero_left:
        st.markdown(
            """
            <div class="hero-shell">
                <div class="hero-tag">AI pipeline</div>
                <h2 class="hero-title">Luxury hiring automation for your next move.</h2>
                <div class="hero-subtitle">
                    Track the jobs that matter, score each opportunity against your profile, and accelerate the strongest applications through AI-assisted automation across LinkedIn, Naukri, Indeed, and other hiring platforms.
                </div>
                <div class="hero-actions">
                    <span class="status-pill primary">Live pipeline</span>
                    <span class="status-pill success">AI match ready</span>
                    <span class="status-pill warning">Auto-apply queue</span>
                </div>
                <div class="pill-list">
                    <span class="chip">Resume sync</span>
                    <span class="chip">Role fit</span>
                    <span class="chip">Application prep</span>
                    <span class="chip">Cross-platform automation</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hero_right:
        st.markdown(
            """
            <div class="floating-card">
                <div class="mini-label">This week</div>
                <div style="font-size: 2rem; font-weight: 800; margin-bottom: 0.35rem;">92%</div>
                <div style="color: #cbd5e1; margin-bottom: 0.8rem;">Applications with a strong AI fit score</div>
                <div class="status-pill success">+14% month over month</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    action_cols = st.columns(3)
    with action_cols[0]:
        st.markdown('<div class="gradient-btn">Boost fit</div>', unsafe_allow_html=True)
    with action_cols[1]:
        st.markdown('<div class="gradient-btn">Review queue</div>', unsafe_allow_html=True)
    with action_cols[2]:
        st.markdown('<div class="gradient-btn">Launch apply</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="playful-row">
            <span class="match-score-chip">✨ top fit 92%</span>
            <span class="match-score-chip">⚡ 3 fast-track roles</span>
            <span class="match-score-chip">🎯 profile synced</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='mini-label'>Content overview</div>", unsafe_allow_html=True)
    content_grid = st.columns([1.3, 0.9])
    with content_grid[0]:
        st.markdown(
            """
            <div class="content-panel">
                <h4>Signal feed</h4>
                <div class="signal-row">
                    <div>
                        <strong>Senior Product Analyst</strong>
                        <div class="signal-meta">LinkedIn • role fit 92%</div>
                    </div>
                    <span class="signal-tag hot">hot</span>
                </div>
                <div class="signal-row">
                    <div>
                        <strong>Frontend Engineer</strong>
                        <div class="signal-meta">Naukri • role fit 89%</div>
                    </div>
                    <span class="signal-tag cool">ready</span>
                </div>
                <div class="signal-row">
                    <div>
                        <strong>Growth PM</strong>
                        <div class="signal-meta">Indeed • role fit 87%</div>
                    </div>
                    <span class="signal-tag pulse">queued</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with content_grid[1]:
        st.markdown(
            """
            <div class="content-panel">
                <h4>Quick wins</h4>
                <div class="signal-row">
                    <div><strong>Refine pitch</strong><div class="signal-meta">Tailor opening sentence</div></div>
                    <span class="signal-tag pulse">2 min</span>
                </div>
                <div class="signal-row">
                    <div><strong>Refresh summary</strong><div class="signal-meta">Align with AI role stack</div></div>
                    <span class="signal-tag cool">new</span>
                </div>
                <div class="signal-row">
                    <div><strong>Reply backlog</strong><div class="signal-meta">3 recruiter follow-ups</div></div>
                    <span class="signal-tag hot">1 due</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    metric_row(
        [
            ("Jobs Found", jobs_found),
            ("Shortlisted", shortlisted),
            ("Applications", applications_count),
            ("Interviews", interviews),
            ("Offers", offers),
        ]
    )
    metric_row(
        [
            ("Rejected", rejected),
            (
                "Avg Match",
                f"{average_match}%" if average_match is not None else "-",
            ),
        ]
    )

    st.markdown("<div class='mini-label'>Automation overview</div>", unsafe_allow_html=True)
    auto_cols = st.columns(4)
    status_items = [
        ("Profile Sync", "Online", "success"),
        ("Resume AI", "Optimized", "primary"),
        ("Job Discovery", "Running", "warning"),
        ("Apply Engine", "Ready", "success"),
    ]
    for col, (name, state, kind) in zip(auto_cols, status_items):
        with col:
            st.markdown(
                f"""
                <div class="floating-card" style="padding: 0.85rem 0.9rem; min-height: 92px;">
                    <div class="mini-label">{name}</div>
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem;">
                        <div style="font-size:1.2rem; font-weight:800;">{state}</div>
                        <span class="status-pill {kind}">{state}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    operator_cols = st.columns([1.7, 1])
    with operator_cols[0]:
        st.markdown("<div class='mini-label'>AI operator action panel</div>", unsafe_allow_html=True)
        action_rows = [
            ("Approve high-fit roles", "Queued", "warning"),
            ("Refresh resume optimization", "Ready", "success"),
            ("Run browser-assisted apply", "Blocked by form review", "danger"),
            ("Schedule follow-up outreach", "Pending", "primary"),
        ]
        for label, state, kind in action_rows:
            st.markdown(
                f"""
                <div class="floating-card" style="margin-bottom:0.7rem; display:flex; justify-content:space-between; align-items:center; gap:0.75rem; padding: 0.8rem 0.9rem; min-height: auto;">
                    <div>
                        <div style="font-size:0.95rem; font-weight:700;">{label}</div>
                        <div style="font-size:0.75rem; color:#cbd5e1; margin-top:0.2rem;">{state}</div>
                    </div>
                    <span class="status-pill {kind}">{state}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with operator_cols[1]:
        st.markdown("<div class='mini-label'>Run history</div>", unsafe_allow_html=True)
        run_history = _build_operator_run_history([
            {"timestamp": "2026-10-29 10:00", "action": "Review queue", "status": "Complete"},
            {"timestamp": "2026-10-29 09:30", "action": "Prepare cover letters", "status": "Running"},
            {"timestamp": "2026-10-29 11:00", "action": "Approve high-fit roles", "status": "Queued"},
        ])
        for item in run_history[:4]:
            st.markdown(
                f"""
                <div class="floating-card" style="margin-bottom:0.6rem; padding: 0.8rem 0.85rem; min-height: auto;">
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                        <div style="font-size:0.9rem; font-weight:700;">{item['action']}</div>
                        <span class="status-pill {'success' if item['status'] == 'Complete' else 'warning' if item['status'] == 'Running' else 'primary'}">{item['status']}</span>
                    </div>
                    <div style="margin-top:0.35rem; color:#cbd5e1; font-size:0.76rem;">{item['timestamp']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div class='mini-label'>Workflow status</div>", unsafe_allow_html=True)
    status_cols = st.columns(4)
    workflow_badges = [
        ("Profile scan", "Complete", "success"),
        ("Skill match", "Live", "primary"),
        ("Application prep", "Queued", "warning"),
        ("Follow-up", "Pending", "danger"),
    ]
    for col, (label, state, kind) in zip(status_cols, workflow_badges):
        with col:
            st.markdown(
                f"""
                <div class="floating-card" style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem; padding: 0.8rem 0.9rem; min-height: 90px;">
                    <div>
                        <div class="mini-label">{label}</div>
                        <div style="font-size:0.9rem; color:#dfe7f5;">{state}</div>
                    </div>
                    <span class="status-pill {kind}">{state}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    apply_queue_cols = st.columns([2, 1])
    with apply_queue_cols[0]:
        st.markdown("<div class='mini-label'>Apply queue / next action</div>", unsafe_allow_html=True)
        queue_rows = [
            ["Senior Product Analyst", "LinkedIn", "92%", "Tailor intro + submit"],
            ["AI Engineer", "Naukri", "88%", "Review role fit"],
            ["Data Scientist", "Indeed", "81%", "Prepare portfolio note"],
        ]
        queue_df = pd.DataFrame(queue_rows, columns=["Role", "Source", "Fit %", "Next action"])
        st.dataframe(queue_df, hide_index=True, use_container_width=True)

    with apply_queue_cols[1]:
        st.markdown(
            """
            <div class="floating-card">
                <div class="mini-label">Next best move</div>
                <div style="font-size:1.15rem; font-weight:800; margin-bottom:0.5rem;">Prioritize 3 high-fit applications</div>
                <div style="color:#cbd5e1; line-height:1.6;">
                    - Refresh resume summary for AI / product roles<br>
                    - Re-score roles with current profile<br>
                    - Automate tailored cover notes
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    chart_scope = st.selectbox(
        "Chart view",
        ["Pipeline overview", "Match quality", "Funnel velocity"],
        index=0,
    )
    if chart_scope == "Pipeline overview":
        chart_data = {
            "Volume": [jobs_found, shortlisted, applications_count, interviews, offers],
        }
        labels = ["Jobs", "Shortlisted", "Applications", "Interviews", "Offers"]
        chart_frame = {label: [value] for label, value in zip(labels, chart_data["Volume"])}
    elif chart_scope == "Match quality":
        chart_data = {
            "Match": [
                max(0, min(100, int(average_match or 0))) if average_match is not None else 0,
                max(0, min(100, (jobs_found if jobs_found else 0) * 2)),
                max(0, min(100, (shortlisted if shortlisted else 0) * 10)),
                max(0, min(100, (applications_count if applications_count else 0) * 8)),
                max(0, min(100, (offers if offers else 0) * 20)),
            ]
        }
        labels = ["Fit", "Jobs", "Shortlisted", "Applied", "Offers"]
        chart_frame = {label: [value] for label, value in zip(labels, chart_data["Match"])}
    else:
        chart_data = {
            "Velocity": [jobs_found, applications_count, interviews, offers],
        }
        labels = ["Discovered", "Applied", "Interview", "Offer"]
        chart_frame = {label: [value] for label, value in zip(labels, chart_data["Velocity"])}

    st.markdown("<div class='mini-label'>Performance</div>", unsafe_allow_html=True)
    st.bar_chart(chart_frame, height=280)

    st.markdown("<div class='mini-label'>Automation coverage</div>", unsafe_allow_html=True)
    source_cols = st.columns(4)
    sources = [
        ("LinkedIn", "High intent", "92%"),
        ("Naukri", "Profile fit", "88%"),
        ("Indeed", "Fast apply", "81%"),
        ("Other boards", "Expanded reach", "74%"),
    ]
    for col, (source, tag, coverage) in zip(source_cols, sources):
        with col:
            st.markdown(
                f"""
                <div class="floating-card" style="padding: 0.9rem 0.95rem; min-height: 110px;">
                    <div class="mini-label">{source}</div>
                    <div style="font-size: 1.45rem; font-weight: 800;">{coverage}</div>
                    <div style="color: #cbd5e1; font-size: 0.8rem;">{tag}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if top_missing:
        st.markdown("<div class='mini-label'>Frequent skill gaps</div>", unsafe_allow_html=True)
        for item in top_missing:
            st.markdown(f"- {item}")
