"""pytest fixtures for Jobinator test suite."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Import all models to register them with SQLModel.metadata
from jobinator.models import DecisionLog, JobScore, NormalizedJob, SpendRecord, StatusEvent  # noqa: F401


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """SQLModel session backed by in-memory engine."""
    with Session(engine) as session:
        yield session
