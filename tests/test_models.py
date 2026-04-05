"""Tests for SQLModel table definitions and database behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from jobinator.models import NormalizedJob, SpendRecord, StatusEvent
from jobinator.models.budget import DecisionLog
from jobinator.models.job import JobStatus, LocationType, SalarySource


def make_job(
    source_url: str = "https://boards.greenhouse.io/acme/jobs/123",
    company: str = "Acme Corp",
    title: str = "Senior ML Engineer",
) -> NormalizedJob:
    """Helper: construct a NormalizedJob with all required fields."""
    description = (
        "We are looking for a Senior ML Engineer with Python experience. "
        "You will work on recommendation systems, experimentation platforms, "
        "and forecasting models at scale."
    )
    return NormalizedJob(
        source="greenhouse",
        source_url=source_url,
        title=title,
        title_normalized=title.lower(),
        company=company,
        company_slug="acme-corp",
        location_raw="Remote (US)",
        location_type=LocationType.remote,
        salary_min=180_000,
        salary_max=240_000,
        estimated_salary_min=175_000,
        estimated_salary_max=230_000,
        salary_source=SalarySource.posted,
        description=description,
        requirements_raw="5+ years Python, ML system design experience",
        description_hash=NormalizedJob.make_description_hash(description),
        posted_at=datetime(2026, 3, 15, 12, 0, 0),
        raw_json=json.dumps({"id": "123", "title": title}),
    )


class TestNormalizedJob:
    def test_create_normalized_job(self, session: Session) -> None:
        """Insert a NormalizedJob with all required fields and read it back (D-01, D-02, DISC-06)."""
        job = make_job()
        session.add(job)
        session.commit()

        retrieved = session.get(NormalizedJob, job.id)
        assert retrieved is not None
        assert retrieved.source == "greenhouse"
        assert retrieved.source_url == "https://boards.greenhouse.io/acme/jobs/123"
        assert retrieved.title == "Senior ML Engineer"
        assert retrieved.title_normalized == "senior ml engineer"
        assert retrieved.company == "Acme Corp"
        assert retrieved.company_slug == "acme-corp"

        # Salary quad (D-01)
        assert retrieved.salary_min == 180_000
        assert retrieved.salary_max == 240_000
        assert retrieved.estimated_salary_min == 175_000
        assert retrieved.estimated_salary_max == 230_000
        assert retrieved.salary_source == SalarySource.posted

        # Location fields (D-02)
        assert retrieved.location_raw == "Remote (US)"
        assert retrieved.location_type == LocationType.remote

        # Description hash (D-05)
        assert retrieved.description_hash is not None
        assert len(retrieved.description_hash) == 16

        # Freshness metadata (DISC-06)
        assert retrieved.first_seen_at is not None
        assert retrieved.last_seen_at is not None
        assert retrieved.posted_at == datetime(2026, 3, 15, 12, 0, 0)

    def test_job_unique_source_url(self, session: Session) -> None:
        """Two jobs with the same source_url should raise IntegrityError."""
        url = "https://boards.greenhouse.io/dupe/jobs/999"
        job1 = make_job(source_url=url)
        job2 = make_job(source_url=url)

        session.add(job1)
        session.commit()

        session.add(job2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_freshness_metadata(self, session: Session) -> None:
        """first_seen_at and last_seen_at are populated automatically (DISC-06)."""
        before = datetime.utcnow()
        job = make_job(source_url="https://boards.greenhouse.io/fresh/jobs/1")
        session.add(job)
        session.commit()
        after = datetime.utcnow()

        retrieved = session.get(NormalizedJob, job.id)
        assert retrieved is not None
        assert before <= retrieved.first_seen_at <= after
        assert before <= retrieved.last_seen_at <= after


class TestStatusEvent:
    def test_create_status_event(self, session: Session) -> None:
        """Insert NormalizedJob, append two StatusEvents, verify ordering (D-03)."""
        job = make_job(source_url="https://boards.greenhouse.io/acme/jobs/456")
        session.add(job)
        session.commit()

        event1 = StatusEvent(job_id=job.id, status=JobStatus.discovered, reason="First seen")
        session.add(event1)
        session.commit()

        event2 = StatusEvent(job_id=job.id, status=JobStatus.scored, reason="Score completed")
        session.add(event2)
        session.commit()

        from sqlmodel import select

        events = session.exec(
            select(StatusEvent)
            .where(StatusEvent.job_id == job.id)
            .order_by(StatusEvent.created_at)
        ).all()

        assert len(events) == 2
        assert events[0].status == JobStatus.discovered
        assert events[1].status == JobStatus.scored


class TestSpendRecord:
    def test_create_spend_record(self, session: Session) -> None:
        """Insert SpendRecord and verify cost_usd and token counts."""
        record = SpendRecord(
            model_name="claude-3-haiku-20240307",
            provider="anthropic",
            operation="score",
            input_tokens=1500,
            output_tokens=300,
            cost_usd=0.00045,
        )
        session.add(record)
        session.commit()

        retrieved = session.get(SpendRecord, record.id)
        assert retrieved is not None
        assert retrieved.model_name == "claude-3-haiku-20240307"
        assert retrieved.provider == "anthropic"
        assert retrieved.operation == "score"
        assert retrieved.input_tokens == 1500
        assert retrieved.output_tokens == 300
        assert abs(retrieved.cost_usd - 0.00045) < 1e-9


class TestDecisionLog:
    def test_create_decision_log(self, session: Session) -> None:
        """Insert DecisionLog with filter_reject type and verify fields (INFR-06)."""
        log = DecisionLog(
            decision_type="filter_reject",
            decision="reject",
            reason="Salary below floor: posted $120k, floor $150k",
            context_json=json.dumps({"salary_min": 120_000, "floor": 150_000}),
        )
        session.add(log)
        session.commit()

        retrieved = session.get(DecisionLog, log.id)
        assert retrieved is not None
        assert retrieved.decision_type == "filter_reject"
        assert retrieved.decision == "reject"
        assert "120k" in retrieved.reason
        assert retrieved.context_json is not None
        ctx = json.loads(retrieved.context_json)
        assert ctx["salary_min"] == 120_000


class TestAlembicMigration:
    def test_alembic_upgrade_head(self, tmp_path: pytest.TempPathFactory) -> None:
        """Test the Alembic migration path end-to-end (INFR-04).

        Creates a fresh SQLite file DB, runs 'alembic upgrade head' against it,
        then inspects the resulting schema to verify all 4 tables were created.
        """
        # Project root is two levels up from this test file (tests/ -> project root)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_file = tmp_path / "test.db"
        db_url = f"sqlite:///{db_file}"

        env = os.environ.copy()
        env["DATABASE_URL"] = db_url

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root,  # run from project root so alembic.ini is found
        )

        # Connect and verify tables exist
        from sqlalchemy import create_engine as sa_create_engine

        engine = sa_create_engine(db_url)
        table_names = inspect(engine).get_table_names()

        assert "normalizedjob" in table_names, f"normalizedjob missing from {table_names}"
        assert "statusevent" in table_names, f"statusevent missing from {table_names}"
        assert "spendrecord" in table_names, f"spendrecord missing from {table_names}"
        assert "decisionlog" in table_names, f"decisionlog missing from {table_names}"
