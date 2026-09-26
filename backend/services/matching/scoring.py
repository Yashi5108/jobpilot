from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import get_settings

DEFAULT_MATCH_WEIGHTS: dict[str, int] = {
    # Required skills are the strongest signal for deterministic fit.
    "required_skills": 50,
    # Preferred skills contribute, but less than required qualifications.
    "preferred_skills": 15,
    "experience": 20,
    "education": 5,
    "certification": 7,
    "domain": 3,
}

MATCH_WEIGHTS = DEFAULT_MATCH_WEIGHTS

UNKNOWN_SCORE = 0.5


@dataclass(frozen=True)
class ScoreBreakdown:
    final_score: int
    normalized_dimension_scores: dict[str, int | None]


def compute_final_score(dimension_scores: dict[str, float | None]) -> ScoreBreakdown:
    match_weights = _match_weights()
    applicable_total_weight = 0
    weighted_points = 0.0

    normalized_dimension_scores: dict[str, int | None] = {}

    for dimension, weight in match_weights.items():
        score = dimension_scores.get(dimension)
        if score is None:
            normalized_dimension_scores[dimension] = None
            continue

        applicable_total_weight += weight
        weighted_points += score * weight
        normalized_dimension_scores[dimension] = int(round(score * 100))

    if applicable_total_weight == 0:
        return ScoreBreakdown(
            final_score=0,
            normalized_dimension_scores=normalized_dimension_scores,
        )

    final = int(round((weighted_points / applicable_total_weight) * 100))
    final = max(0, min(100, final))
    return ScoreBreakdown(
        final_score=final,
        normalized_dimension_scores=normalized_dimension_scores,
    )


def _match_weights() -> dict[str, int]:
    settings = get_settings()
    return {
        "required_skills": settings.match_weight_required_skills,
        "preferred_skills": settings.match_weight_preferred_skills,
        "experience": settings.match_weight_experience,
        "education": settings.match_weight_education,
        "certification": settings.match_weight_certification,
        "domain": settings.match_weight_domain,
    }
