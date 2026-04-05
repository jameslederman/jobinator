"""Tests for BudgetTracker: daily/per-job spend tracking, hard-stop gate, decision logging."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session

from jobinator.budget import BudgetConfig, BudgetExceeded, BudgetTracker
from jobinator.models.budget import DecisionLog, SpendRecord


def _spend(
    cost_usd: float,
    job_id: str | None = None,
    recorded_at: datetime | None = None,
) -> SpendRecord:
    """Helper: create a SpendRecord with sensible defaults."""
    kwargs: dict = dict(
        model_name="test-model",
        provider="test",
        operation="test_op",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost_usd,
    )
    if job_id is not None:
        kwargs["job_id"] = job_id
    if recorded_at is not None:
        kwargs["recorded_at"] = recorded_at
    return SpendRecord(**kwargs)


def _tracker(session: Session, **config_kwargs) -> BudgetTracker:
    """Helper: create BudgetTracker with given config overrides."""
    config = BudgetConfig(**config_kwargs)
    return BudgetTracker(config=config, session=session)


# ---------------------------------------------------------------------------
# daily_spend
# ---------------------------------------------------------------------------


def test_daily_spend_empty(session: Session) -> None:
    """No records -> daily_spend() returns 0.0."""
    tracker = _tracker(session)
    assert tracker.daily_spend() == 0.0


def test_daily_spend_sums_today(session: Session) -> None:
    """3 SpendRecords for today -> daily_spend() returns their sum."""
    tracker = _tracker(session)
    for cost in [0.10, 0.20, 0.30]:
        record = _spend(cost)
        session.add(record)
    session.commit()

    assert abs(tracker.daily_spend() - 0.60) < 1e-9


def test_daily_spend_ignores_yesterday(session: Session) -> None:
    """SpendRecord with recorded_at=yesterday -> daily_spend() returns 0.0."""
    tracker = _tracker(session)
    yesterday = datetime.utcnow() - timedelta(days=1)
    record = _spend(0.50, recorded_at=yesterday)
    session.add(record)
    session.commit()

    assert tracker.daily_spend() == 0.0


# ---------------------------------------------------------------------------
# job_spend
# ---------------------------------------------------------------------------


def test_job_spend_sums_for_job(session: Session) -> None:
    """2 SpendRecords for 'j1' and 1 for 'j2' -> job_spend('j1') returns j1 sum only."""
    tracker = _tracker(session)
    for cost in [0.10, 0.15]:
        session.add(_spend(cost, job_id="j1"))
    session.add(_spend(0.20, job_id="j2"))
    session.commit()

    assert abs(tracker.job_spend("j1") - 0.25) < 1e-9
    assert abs(tracker.job_spend("j2") - 0.20) < 1e-9


# ---------------------------------------------------------------------------
# assert_within_limits
# ---------------------------------------------------------------------------


def test_assert_within_limits_passes(session: Session) -> None:
    """daily_spend < limit -> no exception raised."""
    tracker = _tracker(session, daily_limit_usd=1.00, per_job_limit_usd=0.50)
    session.add(_spend(0.50))
    session.commit()

    # Should not raise
    tracker.assert_within_limits()


def test_assert_within_limits_daily_exceeded(session: Session) -> None:
    """daily_spend >= daily_limit_usd -> BudgetExceeded with 'Daily budget' in message."""
    tracker = _tracker(session, daily_limit_usd=0.10)
    session.add(_spend(0.15))
    session.commit()

    with pytest.raises(BudgetExceeded, match="Daily budget"):
        tracker.assert_within_limits()


def test_assert_within_limits_per_job_exceeded(session: Session) -> None:
    """job_spend >= per_job_limit_usd -> BudgetExceeded with 'Per-job budget' in message."""
    tracker = _tracker(session, per_job_limit_usd=0.10)
    session.add(_spend(0.15, job_id="j1"))
    session.commit()

    with pytest.raises(BudgetExceeded, match="Per-job budget"):
        tracker.assert_within_limits(job_id="j1")


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


def test_record_persists_spend(session: Session) -> None:
    """tracker.record(SpendRecord) -> row queryable from session."""
    tracker = _tracker(session)
    record = _spend(0.05)
    record_id = record.id
    tracker.record(record)

    from sqlmodel import select

    found = session.exec(
        select(SpendRecord).where(SpendRecord.id == record_id)
    ).first()
    assert found is not None
    assert abs(found.cost_usd - 0.05) < 1e-9


# ---------------------------------------------------------------------------
# log_decision
# ---------------------------------------------------------------------------


def test_log_decision_persists(session: Session) -> None:
    """tracker.log_decision() -> DecisionLog entry queryable from session."""
    tracker = _tracker(session)
    entry = tracker.log_decision(
        decision_type="filter_reject",
        decision="skip",
        reason="salary too low",
        job_id=None,
        context={"min_salary": 150000},
    )

    from sqlmodel import select

    found = session.exec(
        select(DecisionLog).where(DecisionLog.id == entry.id)
    ).first()
    assert found is not None
    assert found.decision_type == "filter_reject"
    assert found.reason == "salary too low"
    assert found.context_json is not None
    assert "150000" in found.context_json


# ---------------------------------------------------------------------------
# is_near_limit
# ---------------------------------------------------------------------------


def test_warn_threshold(session: Session) -> None:
    """daily_spend at 80% of limit -> is_near_limit() returns True."""
    tracker = _tracker(
        session, daily_limit_usd=1.00, warn_threshold=0.80
    )
    session.add(_spend(0.80))
    session.commit()

    assert tracker.is_near_limit() is True


def test_warn_threshold_below(session: Session) -> None:
    """daily_spend at 79% of limit -> is_near_limit() returns False."""
    tracker = _tracker(
        session, daily_limit_usd=1.00, warn_threshold=0.80
    )
    session.add(_spend(0.79))
    session.commit()

    assert tracker.is_near_limit() is False
