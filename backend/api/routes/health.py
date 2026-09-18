from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.database import get_db

router = APIRouter()


@router.get(
    "/health",
    summary="API health check",
    description="Checks API availability and database connectivity for API v1.",
)
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
