"""Integration tests for the discovery orchestrator pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Any
from unittest.mock import patch

from jobinator.models.job import NormalizedJob, StatusEvent
from rich.console import Console
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

RawJobDict = dict[str, Any]


def make_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def _raw(company: str, title: str, description: str = "test desc") -> RawJobDict:
    return {
        "title": title,
        "company": company,
        "description": description,
        "source_url": f"https://example.com/{company}/{title.replace(' ', '-')}",
        "location_raw": "Remote",
    }


class MockAdapter:
    """Stub adapter that returns pre-configured raw jobs."""

    def __init__(self, source_id: str, jobs: list[RawJobDict], fragile: bool = False):
        self.source_id = source_id
        self.fragile = fragile
        self._jobs = jobs
        self.call_count = 0

    def fetch(self) -> list[RawJobDict]:
        self.call_count += 1
        return list(self._jobs)


class FailingAdapter:
    """Stub adapter that always raises an exception."""

    source_id = "failing_source"
    fragile = False

    def fetch(self) -> list[RawJobDict]:
        raise RuntimeError("Network failure")


# ---------------------------------------------------------------------------
# persist_jobs tests
# ---------------------------------------------------------------------------


class TestPersistJobs:
    def test_persist_new_jobs_adds_to_db(self):
        """persist_jobs() inserts new jobs into session."""
        from jobinator.pipelines.discover import persist_jobs

        engine = make_engine()
        with Session(engine) as session:
            raw_jobs = [_raw("Acme", "Data Scientist")]
            new_count, dup_count = persist_jobs(session, raw_jobs, "greenhouse")

        assert new_count == 1
        assert dup_count == 0

        with Session(engine) as session:
            jobs = session.query(NormalizedJob).all()
            assert len(jobs) == 1
            assert jobs[0].company == "Acme"

    def test_persist_new_job_creates_status_event(self):
        """persist_jobs() creates StatusEvent(status='discovered') for each new job."""
        from jobinator.pipelines.discover import persist_jobs

        engine = make_engine()
        with Session(engine) as session:
            raw_jobs = [_raw("Acme", "Data Scientist")]
            persist_jobs(session, raw_jobs, "greenhouse")

        with Session(engine) as session:
            events = session.query(StatusEvent).all()
            assert len(events) == 1
            assert events[0].status == "discovered"

    def test_persist_duplicate_updates_last_seen_at(self):
        """persist_jobs() updates last_seen_at on existing duplicate instead of inserting."""
        from jobinator.pipelines.discover import persist_jobs

        engine = make_engine()

        # First insert
        with Session(engine) as session:
            persist_jobs(session, [_raw("Acme", "Data Scientist")], "greenhouse")

        with Session(engine) as session:
            job = session.query(NormalizedJob).first()
            original_last_seen = job.last_seen_at

        # Second insert — same company + title = duplicate
        import time

        time.sleep(0.01)  # ensure clock advances
        with Session(engine) as session:
            new_count, dup_count = persist_jobs(session, [_raw("Acme", "Data Scientist")], "lever")

        assert new_count == 0
        assert dup_count == 1

        with Session(engine) as session:
            jobs = session.query(NormalizedJob).all()
            assert len(jobs) == 1  # not inserted twice
            assert jobs[0].last_seen_at >= original_last_seen

    def test_persist_jobs_deduplicates_within_single_run(self):
        """persist_jobs() deduplicates within a single batch (same job from two sources)."""
        from jobinator.pipelines.discover import persist_jobs

        engine = make_engine()
        raw_jobs = [
            _raw("Acme", "Data Scientist"),
            _raw("Acme", "Data Scientist"),  # duplicate within same batch
        ]
        with Session(engine) as session:
            new_count, dup_count = persist_jobs(session, raw_jobs, "greenhouse")

        assert new_count == 1
        assert dup_count == 1

        with Session(engine) as session:
            jobs = session.query(NormalizedJob).all()
            assert len(jobs) == 1


# ---------------------------------------------------------------------------
# mark_stale_jobs tests
# ---------------------------------------------------------------------------


class TestMarkStaleJobs:
    def _insert_job(self, session: Session, last_seen_at: datetime) -> str:
        """Helper: insert a job with specific last_seen_at."""
        from jobinator.pipelines.normalize import normalize_job

        raw = _raw("Stale Corp", "Old Role")
        job = normalize_job(raw, "greenhouse")
        job.last_seen_at = last_seen_at
        session.add(job)
        session.commit()
        return job.id

    def test_marks_old_jobs_as_stale(self):
        """mark_stale_jobs() sets is_stale=True for jobs older than TTL."""
        from jobinator.pipelines.discover import mark_stale_jobs

        engine = make_engine()
        old_date = datetime.utcnow() - timedelta(days=30)

        with Session(engine) as session:
            self._insert_job(session, old_date)

        with Session(engine) as session:
            stale_count = mark_stale_jobs(session, stale_after_days=14)

        assert stale_count == 1

        with Session(engine) as session:
            jobs = session.query(NormalizedJob).all()
            assert jobs[0].is_stale is True

    def test_does_not_mark_recent_jobs_as_stale(self):
        """mark_stale_jobs() does NOT mark jobs seen recently."""
        from jobinator.pipelines.discover import mark_stale_jobs

        engine = make_engine()
        recent_date = datetime.utcnow() - timedelta(days=5)

        with Session(engine) as session:
            self._insert_job(session, recent_date)

        with Session(engine) as session:
            stale_count = mark_stale_jobs(session, stale_after_days=14)

        assert stale_count == 0

        with Session(engine) as session:
            jobs = session.query(NormalizedJob).all()
            assert jobs[0].is_stale is False


# ---------------------------------------------------------------------------
# run_discovery tests
# ---------------------------------------------------------------------------


class TestRunDiscovery:
    def test_run_discovery_calls_all_adapters(self, tmp_path):
        """run_discovery() calls fetch() on all adapters."""
        from jobinator.configs.settings import DiscoveryConfig
        from jobinator.pipelines.discover import run_discovery

        adapter_a = MockAdapter("source_a", [_raw("Acme", "Role A")])
        adapter_b = MockAdapter("source_b", [_raw("Beta", "Role B")])

        engine = make_engine()
        with Session(engine) as session:
            with patch(
                "jobinator.pipelines.discover.build_adapters",
                return_value=[adapter_a, adapter_b],
            ):
                result = run_discovery(
                    session,
                    DiscoveryConfig(),
                    str(tmp_path),
                    source_filter=None,
                )

        assert adapter_a.call_count == 1
        assert adapter_b.call_count == 1
        assert result.total_new == 2
        assert len(result.sources) == 2

    def test_run_discovery_error_isolation(self, tmp_path):
        """run_discovery() isolates adapter failures — one failure does not block others."""
        from jobinator.configs.settings import DiscoveryConfig
        from jobinator.pipelines.discover import run_discovery

        good_adapter = MockAdapter("good_source", [_raw("Acme", "Data Scientist")])
        bad_adapter = FailingAdapter()

        engine = make_engine()
        with Session(engine) as session:
            with patch(
                "jobinator.pipelines.discover.build_adapters",
                return_value=[bad_adapter, good_adapter],
            ):
                result = run_discovery(
                    session,
                    DiscoveryConfig(),
                    str(tmp_path),
                )

        # good adapter should still produce results
        assert result.total_new == 1
        # failed source should be recorded
        failed = [s for s in result.sources if s.error is not None]
        assert len(failed) == 1
        assert "failing_source" in [s.source_id for s in failed]

    def test_cross_source_dedup(self, tmp_path):
        """Same job from two adapters is stored once in DB."""
        from jobinator.configs.settings import DiscoveryConfig
        from jobinator.pipelines.discover import run_discovery

        same_job = _raw("Acme", "Data Scientist", "Same description text")
        adapter_a = MockAdapter("greenhouse", [same_job])
        adapter_b = MockAdapter("lever", [same_job])

        engine = make_engine()
        with Session(engine) as session:
            with patch(
                "jobinator.pipelines.discover.build_adapters",
                return_value=[adapter_a, adapter_b],
            ):
                result = run_discovery(
                    session,
                    DiscoveryConfig(),
                    str(tmp_path),
                )

        with Session(engine) as session:
            jobs = session.query(NormalizedJob).all()
            assert len(jobs) == 1

        assert result.total_new == 1
        assert result.total_duplicates == 1

    def test_stale_marking(self, tmp_path):
        """Jobs not re-sighted within stale_after_days TTL are marked is_stale=True."""
        from jobinator.configs.settings import DiscoveryConfig
        from jobinator.pipelines.discover import run_discovery
        from jobinator.pipelines.normalize import normalize_job

        engine = make_engine()
        old_date = datetime.utcnow() - timedelta(days=30)

        # Insert an old job directly
        with Session(engine) as session:
            old_raw = _raw("Old Corp", "Ancient Role")
            old_job = normalize_job(old_raw, "greenhouse")
            old_job.last_seen_at = old_date
            session.add(old_job)
            session.commit()

        # Run discovery with no new jobs from adapters
        with Session(engine) as session:
            with patch(
                "jobinator.pipelines.discover.build_adapters",
                return_value=[MockAdapter("greenhouse", [])],
            ):
                result = run_discovery(
                    session,
                    DiscoveryConfig(stale_after_days=14),
                    str(tmp_path),
                )

        assert result.stale_marked >= 1

        with Session(engine) as session:
            old_job = (
                session.query(NormalizedJob).filter(NormalizedJob.company == "Old Corp").first()
            )
            assert old_job is not None
            assert old_job.is_stale is True


# ---------------------------------------------------------------------------
# Source health tracking tests
# ---------------------------------------------------------------------------


class TestSourceHealth:
    def test_health_tracker_increments_consecutive_zeros(self, tmp_path):
        """Health tracker increments consecutive_zeros when adapter returns 0 jobs."""
        from jobinator.configs.settings import DiscoveryConfig
        from jobinator.pipelines.discover import load_source_health, run_discovery

        empty_adapter = MockAdapter("empty_source", [])

        engine = make_engine()
        with Session(engine) as session:
            with patch(
                "jobinator.pipelines.discover.build_adapters",
                return_value=[empty_adapter],
            ):
                run_discovery(session, DiscoveryConfig(), str(tmp_path))

        health = load_source_health(str(tmp_path))
        assert health.get("empty_source", 0) == 1

    def test_health_tracker_resets_on_results(self, tmp_path):
        """Health tracker resets consecutive_zeros counter when adapter returns > 0 jobs."""
        from jobinator.configs.settings import DiscoveryConfig
        from jobinator.pipelines.discover import (
            load_source_health,
            run_discovery,
            save_source_health,
        )

        # Pre-seed health with 2 consecutive zeros
        save_source_health(str(tmp_path), {"my_source": 2})

        jobs_adapter = MockAdapter("my_source", [_raw("Acme", "ML Engineer")])

        engine = make_engine()
        with Session(engine) as session:
            with patch(
                "jobinator.pipelines.discover.build_adapters",
                return_value=[jobs_adapter],
            ):
                run_discovery(session, DiscoveryConfig(), str(tmp_path))

        health = load_source_health(str(tmp_path))
        assert health.get("my_source", 99) == 0

    def test_source_health_alert(self, tmp_path):
        """fire_health_alerts() prints warning when consecutive_zeros >= 3."""
        from jobinator.pipelines.discover import fire_health_alerts

        output = StringIO()
        console = Console(file=output, force_terminal=True, no_color=True)

        health = {"slow_source": 3, "ok_source": 1}
        fire_health_alerts(health, console)

        result = output.getvalue()
        assert "slow_source" in result
        assert "WARNING" in result.upper() or "warning" in result.lower()
        # ok_source has only 1 consecutive zero — should NOT warn
        assert "ok_source" not in result
