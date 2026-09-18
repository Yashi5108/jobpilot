from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings


class Base(DeclarativeBase):
    """Base declarative class for all ORM models."""


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    if not _is_sqlite_url(database_url):
        return

    db_url = make_url(database_url)
    database_path = db_url.database
    if not database_path or database_path == ":memory:":
        return

    db_file = Path(database_path)
    if not db_file.is_absolute():
        db_file = Path.cwd() / db_file
    db_file.parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    database_url = get_settings().database_url
    _ensure_sqlite_parent_dir(database_url)

    connect_args: dict[str, object] = {}
    if _is_sqlite_url(database_url):
        connect_args["check_same_thread"] = False

    engine_instance = create_engine(
        database_url,
        connect_args=connect_args,
        future=True,
    )

    if _is_sqlite_url(database_url):
        _enable_sqlite_foreign_keys(engine_instance)

    return engine_instance


def _enable_sqlite_foreign_keys(engine_instance: Engine) -> None:
    @event.listens_for(engine_instance, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables for the configured database.

    Safe to call repeatedly.
    """
    from backend.database import models  # noqa: F401

    _ensure_sqlite_parent_dir(get_settings().database_url)
    Base.metadata.create_all(bind=engine)
