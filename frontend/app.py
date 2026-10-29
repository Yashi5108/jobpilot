from __future__ import annotations

from pathlib import Path

import streamlit as st

from frontend.api_client import ApiClient
from frontend.components.navigation import render_sidebar_navigation
from frontend.renderers.applications import render_applications
from frontend.renderers.dashboard import render_dashboard
from frontend.renderers.job_matches import render_job_matches
from frontend.renderers.jobs import render_jobs
from frontend.renderers.profile import render_profile
from frontend.renderers.resumes import render_resumes


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-1: #09090f;
            --bg-2: #111827;
            --bg-3: #1a1035;
            --panel: rgba(15, 23, 42, 0.7);
            --panel-strong: rgba(17, 24, 39, 0.9);
            --border: rgba(148, 163, 184, 0.18);
            --text: #f8fafc;
            --muted: #b7c6de;
            --primary: #8b5cf6;
            --primary-soft: rgba(139, 92, 246, 0.18);
            --pink: #ec4899;
            --cyan: #22d3ee;
            --green: #34d399;
            --amber: #fbbf24;
            --red: #f87171;
            --glow: rgba(139,92,246,0.38);
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(139,92,246,0.25), transparent 26%),
                radial-gradient(circle at top right, rgba(34,211,238,0.18), transparent 22%),
                radial-gradient(circle at bottom left, rgba(236,72,153,0.15), transparent 25%),
                linear-gradient(180deg, var(--bg-1), var(--bg-2));
            color: var(--text);
        }

        [data-testid="stSidebar"] {
            background: rgba(17, 24, 39, 0.92);
            border-right: 1px solid var(--border);
            box-shadow: 0 0 0 1px rgba(148,163,184,0.08);
        }

        [data-testid="stSidebar"] .stRadio {
            gap: 10px;
        }

        [data-testid="stSidebar"] label {
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 14px;
            padding: 0.8rem 0.9rem;
            background: linear-gradient(180deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9));
            transition: 180ms ease;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }

        [data-testid="stSidebar"] label:hover {
            background: linear-gradient(180deg, rgba(124,58,237,0.14), rgba(15,23,42,0.95));
            border-color: rgba(139, 92, 246, 0.7);
            transform: translateY(-1px);
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 18px;
            border: 1px solid var(--border);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.8), rgba(15, 23, 42, 0.58));
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.24);
        }

        .stButton>button {
            border-radius: 12px;
            font-weight: 700;
            border: 1px solid rgba(148, 163, 184, 0.2);
            background: linear-gradient(180deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
            color: var(--text);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
            animation: floatCard 4.8s ease-in-out infinite;
        }

        .stButton>button:hover {
            border-color: rgba(124,58,237,0.9);
            box-shadow: 0 10px 28px rgba(124,58,237,0.18);
            transform: translateY(-2px);
            background: linear-gradient(135deg, rgba(139,92,246,0.32), rgba(34,211,238,0.15), rgba(15,23,42,0.92));
        }

        .stTabs [data-testid="stBaseButton-secondary"] {
            border-radius: 10px;
        }

        .metric-card {
            border-radius: 16px;
            padding: 1rem 1.1rem;
            background: linear-gradient(180deg, rgba(30,41,59,0.82), rgba(15,23,42,0.9));
            border: 1px solid var(--border);
            min-height: 112px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }

        .metric-card .metric-label {
            color: var(--muted);
            font-size: 0.72rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.45rem;
        }

        .metric-card .metric-value {
            color: var(--text);
            font-size: 1.9rem;
            font-weight: 800;
            line-height: 1.1;
        }

        .panel-card {
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.92), rgba(15, 23, 42, 0.72));
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
        }

        .status-pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.32rem 0.7rem;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            background: rgba(148, 163, 184, 0.14);
            color: var(--text);
        }

        .status-pill.primary { background: rgba(139, 92, 246, 0.18); color: #e9d5ff; }
        .status-pill.success { background: rgba(16, 185, 129, 0.15); color: #a7f3d0; }
        .status-pill.warning { background: rgba(251, 191, 36, 0.15); color: #fef3c7; }
        .status-pill.danger { background: rgba(248, 113, 113, 0.15); color: #fecaca; }

        .mini-label {
            color: var(--muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.3rem;
        }

        .creator-strip {
            position: relative;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
            padding: 0.95rem 1.1rem;
            border-radius: 22px;
            margin-bottom: 1rem;
            border: 1px solid rgba(148,163,184,0.18);
            background: linear-gradient(90deg, rgba(18,24,40,0.88), rgba(20,31,57,0.78), rgba(28,18,45,0.82));
            box-shadow: 0 18px 30px rgba(15,23,42,0.24);
        }

        .creator-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border-radius: 999px;
            padding: 0.36rem 0.8rem;
            background: linear-gradient(90deg, rgba(139,92,246,0.2), rgba(34,211,238,0.14));
            border: 1px solid rgba(167,139,250,0.5);
            color: #f5e8ff;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
        }

        .creator-pill-group {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            align-items: center;
            justify-content: flex-end;
        }

        .creator-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            border-radius: 999px;
            padding: 0.42rem 0.75rem;
            border: 1px solid rgba(148,163,184,0.20);
            background: rgba(15,23,42,0.72);
            color: var(--text);
            font-size: 0.74rem;
            font-weight: 700;
            animation: pulseGlow 3.6s ease-in-out infinite;
        }

        .creator-pill.primary {
            background: linear-gradient(90deg, rgba(139,92,246,0.18), rgba(34,211,238,0.12));
            border-color: rgba(139,92,246,0.42);
        }

        .creator-pill.success {
            background: linear-gradient(90deg, rgba(16,185,129,0.14), rgba(52,211,153,0.10));
            border-color: rgba(16,185,129,0.42);
        }

        .gradient-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 0.72rem 1rem;
            border: 0;
            border-radius: 14px;
            background: linear-gradient(90deg, rgba(139,92,246,0.95), rgba(34,211,238,0.8), rgba(236,72,153,0.8));
            color: white;
            font-weight: 800;
            letter-spacing: 0.02em;
            box-shadow: 0 12px 26px rgba(139,92,246,0.28);
            animation: shimmer 5.5s linear infinite;
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .gradient-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 18px 30px rgba(34,211,238,0.24);
        }

        .floating-card {
            position: relative;
            border-radius: 20px;
            border: 1px solid rgba(148,163,184,0.18);
            background: linear-gradient(180deg, rgba(15,23,42,0.88), rgba(17,24,39,0.72));
            padding: 0.9rem 1rem;
            min-height: 108px;
            box-shadow: 0 18px 32px rgba(15,23,42,0.18);
            animation: floatCard 5s ease-in-out infinite;
            overflow: hidden;
        }

        .floating-card::before {
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 120px;
            height: 120px;
            background: radial-gradient(circle, rgba(139,92,246,0.18), transparent 70%);
            pointer-events: none;
        }

        .hero-shell {
            position: relative;
            border-radius: 28px;
            border: 1px solid rgba(167, 139, 250, 0.28);
            background: linear-gradient(135deg, rgba(139,92,246,0.22), rgba(17,24,39,0.94) 42%, rgba(34,211,238,0.12));
            padding: 1.4rem 1.5rem;
            overflow: hidden;
            margin-bottom: 1rem;
            box-shadow: 0 22px 46px rgba(17, 24, 39, 0.36), 0 0 0 1px rgba(139,92,246,0.15);
            transform: translateZ(0);
        }

        .hero-shell::before {
            content: "";
            position: absolute;
            inset: -25% auto auto -10%;
            width: 220px;
            height: 220px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(236,72,153,0.22), transparent 70%);
            pointer-events: none;
            transform: translate3d(0, 0, 0);
            animation: driftSoft 12s ease-in-out infinite alternate;
        }

        .hero-shell::after {
            content: "";
            position: absolute;
            inset: auto -80px -80px auto;
            width: 260px;
            height: 260px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(34,211,238,0.20), transparent 70%);
            pointer-events: none;
            transform: translate3d(0, 0, 0);
            animation: driftSoftReverse 14s ease-in-out infinite alternate;
        }

        .hero-tag {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border-radius: 999px;
            background: rgba(139,92,246,0.14);
            color: #f5e8ff;
            border: 1px solid rgba(167,139,250,0.48);
            padding: 0.44rem 0.8rem;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.9rem;
            position: relative;
            z-index: 1;
        }

        .hero-title {
            color: var(--text);
            font-size: clamp(2.15rem, 3vw, 3.4rem);
            line-height: 1.02;
            font-weight: 900;
            margin: 0 0 0.7rem 0;
            letter-spacing: -0.05em;
            position: relative;
            z-index: 1;
        }

        .hero-subtitle {
            color: var(--muted);
            font-size: 1.02rem;
            line-height: 1.7;
            max-width: 760px;
            margin-bottom: 1rem;
            position: relative;
            z-index: 1;
        }

        .hero-actions {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-top: 0.75rem;
            position: relative;
            z-index: 1;
        }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.85rem;
            padding: 0.8rem 1rem;
            border-radius: 20px;
            background: rgba(15, 23, 42, 0.78);
            border: 1px solid rgba(148, 163, 184, 0.15);
            margin-bottom: 1rem;
            box-shadow: 0 18px 28px rgba(15, 23, 42, 0.18);
        }

        .brand-mark {
            display: inline-flex;
            align-items: center;
            gap: 0.72rem;
            font-weight: 900;
            letter-spacing: -0.05em;
            font-size: 1.2rem;
        }

        .brand-badge {
            width: 32px;
            height: 32px;
            border-radius: 12px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #8b5cf6, #22d3ee, #ec4899);
            box-shadow: 0 10px 22px rgba(139, 92, 246, 0.42);
            color: white;
            font-size: 0.72rem;
            font-weight: 900;
        }

        .nav-links {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            flex-wrap: wrap;
            color: var(--muted);
            font-size: 0.8rem;
        }

        .nav-pills {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
            background: rgba(148, 163, 184, 0.06);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 999px;
            padding: 0.3rem 0.5rem;
        }

        .nav-pills span {
            display: inline-flex;
            padding: 0.32rem 0.7rem;
            border-radius: 999px;
            background: linear-gradient(135deg, rgba(139,92,246,0.12), rgba(34,211,238,0.10));
            color: #e9d5ff;
            font-weight: 700;
            border: 1px solid rgba(139, 92, 246, 0.18);
        }

        .glass-card {
            background: linear-gradient(180deg, rgba(17,24,39,0.8), rgba(15,23,42,0.9));
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 22px;
            padding: 1rem 1.05rem;
            box-shadow: 0 18px 32px rgba(15, 23, 42, 0.18);
            transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .glass-card:hover {
            transform: translateY(-3px);
            border-color: rgba(139, 92, 246, 0.54);
            box-shadow: 0 22px 38px rgba(139, 92, 246, 0.12);
        }

        .match-score-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            border-radius: 999px;
            padding: 0.42rem 0.8rem;
            background: linear-gradient(90deg, rgba(139,92,246,0.18), rgba(34,211,238,0.14));
            border: 1px solid rgba(167, 139, 250, 0.4);
            color: #f5eaff;
            font-weight: 800;
            letter-spacing: 0.04em;
            font-size: 0.7rem;
            text-transform: uppercase;
        }

        .playful-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin: 0.75rem 0 1rem;
        }

        .compact-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.8rem;
            margin-top: 1rem;
        }

        .pill-list {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.75rem;
        }

        .chip {
            display: inline-flex;
            padding: 0.38rem 0.7rem;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.16);
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 600;
        }

        .analytics-shell {
            border-radius: 24px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.94), rgba(15, 23, 42, 0.78));
            padding: 1.15rem 1.1rem;
            margin-bottom: 1rem;
            box-shadow: 0 18px 36px rgba(15, 23, 42, 0.2);
        }

        .engagement-card {
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 0.35rem;
            min-height: 116px;
            padding: 0.9rem 1rem;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(15,23,42,0.86), rgba(17,24,39,0.76));
            border: 1px solid rgba(148, 163, 184, 0.16);
            box-shadow: 0 16px 30px rgba(15,23,42,0.18);
            animation: floatCard 6s ease-in-out infinite;
            overflow: hidden;
        }

        .engagement-card::before {
            content: "";
            position: absolute;
            inset: auto -30px -30px auto;
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(34,211,238,0.14), transparent 68%);
            pointer-events: none;
        }

        .engagement-label {
            color: var(--muted);
            font-size: 0.7rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .engagement-value {
            font-size: 1.8rem;
            font-weight: 900;
            letter-spacing: -0.06em;
            color: var(--text);
        }

        .engagement-note {
            color: #d9e3f6;
            font-size: 0.76rem;
            opacity: 0.9;
        }

        .content-grid {
            display: grid;
            grid-template-columns: 1.4fr 1fr;
            gap: 1rem;
            margin-top: 1rem;
            margin-bottom: 1rem;
        }

        .content-panel {
            border-radius: 22px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: linear-gradient(180deg, rgba(15,23,42,0.9), rgba(17,24,39,0.76));
            padding: 1rem 1.1rem;
            box-shadow: 0 20px 32px rgba(15,23,42,0.2);
        }

        .content-panel h4 {
            margin: 0 0 0.8rem 0;
            font-size: 0.8rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--muted);
        }

        .signal-row {
            display: flex;
            justify-content: space-between;
            gap: 0.7rem;
            align-items: center;
            padding: 0.72rem 0.8rem;
            border-radius: 16px;
            margin-bottom: 0.6rem;
            background: rgba(15,23,42,0.55);
            border: 1px solid rgba(148,163,184,0.12);
        }

        .signal-row strong {
            font-size: 0.96rem;
        }

        .signal-meta {
            color: var(--muted);
            font-size: 0.75rem;
        }

        .signal-tag {
            display: inline-flex;
            border-radius: 999px;
            padding: 0.3rem 0.6rem;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            border: 1px solid rgba(148,163,184,0.18);
        }

        .signal-tag.hot { background: rgba(236,72,153,0.12); color: #fbcfe8; }
        .signal-tag.cool { background: rgba(34,211,238,0.12); color: #cffafe; }
        .signal-tag.pulse { background: rgba(16,185,129,0.12); color: #bbf7d0; }

        @keyframes floatCard {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-4px); }
        }

        @keyframes driftSoft {
            0% { transform: translate3d(-10px, 8px, 0) scale(1); }
            100% { transform: translate3d(18px, -12px, 0) scale(1.12); }
        }

        @keyframes driftSoftReverse {
            0% { transform: translate3d(12px, -14px, 0) scale(1); }
            100% { transform: translate3d(-18px, 10px, 0) scale(1.1); }
        }

        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 rgba(139,92,246,0.0); }
            50% { box-shadow: 0 0 20px rgba(139,92,246,0.24); }
        }

        @keyframes shimmer {
            0% { background-position: 0% 50%; }
            100% { background-position: 100% 50%; }
        }

        .analytics-panel {
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(15, 23, 42, 0.7);
            padding: 0.9rem 1rem;
        }

        .analytics-tile {
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: linear-gradient(180deg, rgba(30, 41, 59, 0.82), rgba(15, 23, 42, 0.92));
            padding: 0.9rem 0.95rem;
            min-height: 120px;
        }

        .analytics-tile .kicker {
            color: var(--muted);
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.4rem;
        }

        .analytics-tile .value {
            font-size: 1.7rem;
            font-weight: 800;
            letter-spacing: -0.04em;
        }

        .score-bar {
            height: 10px;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(148, 163, 184, 0.12);
            border: 1px solid rgba(148, 163, 184, 0.12);
        }

        .score-bar > div {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #8b5cf6, #22d3ee);
        }

        @media (max-width: 768px) {
            .hero-shell {
                padding: 1rem 1rem 1.1rem;
            }

            .metric-card {
                min-height: 88px;
            }

            .metric-card .metric-value {
                font-size: 1.4rem;
            }

            .panel-card {
                padding: 0.85rem 0.9rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="JobPilot",
        page_icon="🚀",
        layout="wide",
    )
    _inject_theme()

    st.markdown(
        """
        <div class="topbar">
            <div class="brand-mark">
                <span class="brand-badge">JP</span>
                <span>JobPilot AI</span>
            </div>
            <div class="nav-links">
                <div class="nav-pills">
                    <span>LinkedIn</span>
                    <span>Naukri</span>
                    <span>Indeed</span>
                    <span>Auto-Apply AI</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-tag">AI hiring automation</div>
            <h2 class="hero-title">Apply smarter. Land faster.</h2>
            <div class="hero-subtitle">
                Discover roles that actually fit your profile, match your experience to live openings, and move through the application process with AI-powered guidance across LinkedIn, Naukri, Indeed, and more.
            </div>
            <div class="hero-actions">
                <span class="status-pill primary">Auto-match</span>
                <span class="status-pill success">AI review</span>
                <span class="status-pill warning">Smart apply</span>
                <span class="status-pill danger">Low drama</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    api_client = ApiClient()
    if "jobpilot_selected_page" not in st.session_state:
        st.session_state["jobpilot_selected_page"] = "Dashboard"
    if st.session_state.get("jobpilot_selected_page") == "Applications":
        selected_page = "Applications"
    else:
        selected_page = render_sidebar_navigation()

    if selected_page == "Dashboard":
        render_dashboard(api_client)
    elif selected_page == "Profile":
        render_profile(api_client)
    elif selected_page == "Resumes":
        render_resumes(api_client)
    elif selected_page == "Jobs":
        render_jobs(api_client)
    elif selected_page == "Job Matches":
        render_job_matches(api_client)
    elif selected_page == "Applications":
        render_applications(api_client)
    else:
        st.error("Unknown page selected.")


if __name__ == "__main__":
    main()
