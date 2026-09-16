from fastapi import FastAPI
from sqlalchemy import text

from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.database.database import engine

setup_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {"status": "ok", "database": "connected"}
