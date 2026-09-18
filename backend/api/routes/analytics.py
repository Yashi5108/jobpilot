from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.schemas.analytics import AnalyticsOverview
from backend.services.analytics_service import get_analytics_overview

router = APIRouter(prefix="/analytics")


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    summary="Analytics overview",
    description="Returns local read-only JobPilot analytics metrics.",
)
def read_analytics_overview(db: Session = Depends(get_db)) -> AnalyticsOverview:
    return get_analytics_overview(db)
