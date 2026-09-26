from __future__ import annotations

from backend.core.config import PROJECT_ROOT, get_settings
from backend.services.matching.scoring import compute_final_score


def test_settings_defaults_are_cwd_independent(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RESUME_STORAGE_DIR", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.database_url.endswith("/data/jobpilot.db")
    assert settings.database_url.startswith("sqlite:///")
    assert settings.resume_storage_dir == str(PROJECT_ROOT / "data" / "resumes")


def test_matching_weights_can_be_configured(monkeypatch) -> None:
    monkeypatch.setenv("MATCH_WEIGHT_REQUIRED_SKILLS", "100")
    monkeypatch.setenv("MATCH_WEIGHT_PREFERRED_SKILLS", "0")
    monkeypatch.setenv("MATCH_WEIGHT_EXPERIENCE", "0")
    monkeypatch.setenv("MATCH_WEIGHT_EDUCATION", "0")
    monkeypatch.setenv("MATCH_WEIGHT_CERTIFICATION", "0")
    monkeypatch.setenv("MATCH_WEIGHT_DOMAIN", "0")
    get_settings.cache_clear()
    try:
        score = compute_final_score(
            {
                "required_skills": 0.25,
                "preferred_skills": 1.0,
                "experience": 1.0,
                "education": 1.0,
                "certification": 1.0,
                "domain": 1.0,
            }
        )
    finally:
        get_settings.cache_clear()

    assert score.final_score == 25
