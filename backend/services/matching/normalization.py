from __future__ import annotations

import re

_SKILL_ALIASES: dict[str, str] = {
    "python3": "python",
    "py": "python",
    "fast api": "fastapi",
    "postgre sql": "postgresql",
    "postgres": "postgresql",
    "amazon web services": "aws",
}


def normalize_text(value: str) -> str:
    lowered = value.strip().lower()
    collapsed = re.sub(r"\s+", " ", lowered)
    return collapsed


def normalize_skill_name(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace("-", " ")
    canonical = _SKILL_ALIASES.get(normalized, normalized)
    return canonical.replace(" ", "")


def normalize_free_text(value: str) -> str:
    return normalize_text(value).replace("-", " ")
