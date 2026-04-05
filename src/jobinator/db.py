"""SQLite engine creation, WAL mode configuration, and session factory."""

from __future__ import annotations

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from jobinator.configs.settings import get_settings


def get_engine(url: str | None = None):
    """Create and return a SQLAlchemy engine with WAL mode enabled.

    WAL (Write-Ahead Logging) mode improves concurrent read performance
    and reduces lock contention for SQLite databases.

    Args:
        url: SQLite connection URL. Defaults to value from settings.

    Returns:
        Configured SQLAlchemy engine.
    """
    db_url = url or get_settings().database_url

    # Ensure parent directory exists for file-based databases
    if db_url.startswith("sqlite:///") and db_url != "sqlite:///:memory:":
        import os

        db_path = db_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    engine = create_engine(db_url, echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[misc]
        """Enable WAL journal mode on every new connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def get_session(engine=None) -> Session:
    """Return a new SQLModel Session.

    Args:
        engine: SQLAlchemy engine to use. Defaults to engine from get_engine().

    Returns:
        A new Session — caller is responsible for closing it.
        Prefer using as a context manager: `with get_session() as session:`.
    """
    if engine is None:
        engine = get_engine()
    return Session(engine)


def init_db(engine=None) -> None:
    """Create all SQLModel tables in the database.

    Used for in-memory test databases and initial setup.
    For production use, prefer Alembic migrations via `alembic upgrade head`.

    Args:
        engine: SQLAlchemy engine to use. Defaults to engine from get_engine().
    """
    if engine is None:
        engine = get_engine()
    SQLModel.metadata.create_all(engine)
