from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.router import api_router
from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.database.database import get_db

setup_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))

    return {"status": "ok", "database": "connected"}
