from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.models import Application, ApplicationStatus, Job, JobMatch
from backend.schemas.analytics import (
    AnalyticsOverview,
    SkillCount,
    StatusCount,
    TimeBucketCount,
)


def get_analytics_overview(db: Session) -> AnalyticsOverview:
    jobs_found = db.scalar(select(func.count()).select_from(Job)) or 0
    applications = db.scalar(select(func.count()).select_from(Application)) or 0

    status_counts = list(
        db.execute(
            select(Application.status, func.count())
            .group_by(Application.status)
            .order_by(Application.status.asc())
        ).all()
    )

    status_map = {status.value: int(count) for status, count in status_counts}

    timeline = list(
        db.execute(
            select(func.date(Application.created_at), func.count())
            .group_by(func.date(Application.created_at))
            .order_by(func.date(Application.created_at).asc())
        ).all()
    )

    avg_score = db.scalar(
        select(func.avg(JobMatch.match_score)).where(JobMatch.match_score.is_not(None))
    )

    matched_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()
    matches = list(db.scalars(select(JobMatch)).all())
    for row in matches:
        if isinstance(row.matching_skills, list):
            matched_counter.update(
                str(item) for item in row.matching_skills if str(item).strip()
            )
        if isinstance(row.missing_skills, list):
            missing_counter.update(
                str(item) for item in row.missing_skills if str(item).strip()
            )

    return AnalyticsOverview(
        jobs_found=int(jobs_found),
        shortlisted_jobs=status_map.get(ApplicationStatus.SHORTLISTED.value, 0),
        applications=int(applications),
        interviews=status_map.get(ApplicationStatus.INTERVIEW.value, 0),
        offers=status_map.get(ApplicationStatus.OFFER.value, 0),
        rejected=status_map.get(ApplicationStatus.REJECTED.value, 0),
        applications_by_status=[
            StatusCount(status=status.value, count=status_map.get(status.value, 0))
            for status in ApplicationStatus
        ],
        applications_over_time=[
            TimeBucketCount(date=str(day), count=int(count))
            for day, count in timeline
            if day
        ],
        average_match_score=(float(avg_score) if avg_score is not None else None),
        top_matched_skills=[
            SkillCount(skill=skill, count=count)
            for skill, count in matched_counter.most_common(10)
        ],
        frequently_missing_skills=[
            SkillCount(skill=skill, count=count)
            for skill, count in missing_counter.most_common(10)
        ],
    )
