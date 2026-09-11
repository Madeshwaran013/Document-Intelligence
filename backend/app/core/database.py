"""
SQLAlchemy engine/session wiring.

Defaults to a local SQLite file (zero-setup persistence for the case
study / evaluation environment). Swap DATABASE_URL for Postgres or MySQL
in production — no application code changes are required because all
access goes through the repository layer.
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    # Ensure the parent directory for the sqlite file exists.
    db_path = settings.DATABASE_URL.split("///")[-1]
    if db_path and db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """Create tables if they do not exist yet."""
    from app.models import document  # noqa: F401 (register models)

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Context manager for use outside of FastAPI request handling."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
