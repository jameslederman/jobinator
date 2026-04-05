"""BudgetTracker: hard-stop gate and decision logging for LLM API spend (INFR-06)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Session, func, select

from jobinator.models.budget import DecisionLog, SpendRecord


class BudgetExceeded(Exception):
    """Raised before an LLM call when budget limits would be exceeded."""


class BudgetConfig(BaseModel):
    """Configurable budget limits for API spend enforcement."""

    daily_limit_usd: float = 5.00
    per_job_limit_usd: float = 0.50
    warn_threshold: float = 0.80


class BudgetTracker:
    """Tracks API spend, enforces limits, and logs agent decisions.

    Call assert_within_limits() BEFORE every LLM call to prevent cost overruns.
    Call record() AFTER every LLM call to persist the spend.
    Call log_decision() for every agent decision (filter/score/apply) for auditability.
    """

    def __init__(self, config: BudgetConfig, session: Session) -> None:
        self.config = config
        self.session = session

    def daily_spend(self) -> float:
        """Sum of cost_usd for all SpendRecords where recorded_at is today (UTC).

        Uses UTC midnight boundaries to match the datetime.utcnow() default
        used by SpendRecord.recorded_at.
        """
        utcnow = datetime.utcnow()
        today_start = utcnow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        statement = select(
            func.coalesce(func.sum(SpendRecord.cost_usd), 0.0)
        ).where(
            SpendRecord.recorded_at >= today_start,
            SpendRecord.recorded_at < tomorrow_start,
        )
        result = self.session.exec(statement).one()
        return float(result)

    def job_spend(self, job_id: str) -> float:
        """Sum of cost_usd for all SpendRecords for a given job_id."""
        statement = select(
            func.coalesce(func.sum(SpendRecord.cost_usd), 0.0)
        ).where(SpendRecord.job_id == job_id)
        result = self.session.exec(statement).one()
        return float(result)

    def is_near_limit(self) -> bool:
        """Returns True if daily spend >= warn_threshold * daily_limit_usd."""
        return self.daily_spend() >= (
            self.config.warn_threshold * self.config.daily_limit_usd
        )

    def assert_within_limits(self, job_id: Optional[str] = None) -> None:
        """Call BEFORE every LLM call. Raises BudgetExceeded if over limit.

        Args:
            job_id: If provided, also checks the per-job spend limit.

        Raises:
            BudgetExceeded: When daily or per-job budget is exhausted.
        """
        spent = self.daily_spend()
        if spent >= self.config.daily_limit_usd:
            raise BudgetExceeded(
                f"Daily budget exhausted: ${spent:.4f} >= ${self.config.daily_limit_usd:.2f}"
            )
        if job_id is not None:
            job_spent = self.job_spend(job_id)
            if job_spent >= self.config.per_job_limit_usd:
                raise BudgetExceeded(
                    f"Per-job budget exhausted for {job_id}: "
                    f"${job_spent:.4f} >= ${self.config.per_job_limit_usd:.2f}"
                )

    def record(self, spend: SpendRecord) -> None:
        """Persist a SpendRecord to the database."""
        self.session.add(spend)
        self.session.commit()

    def log_decision(
        self,
        decision_type: str,
        decision: str,
        reason: str,
        job_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> DecisionLog:
        """Record an agent decision for auditability (per INFR-06).

        Args:
            decision_type: e.g. 'filter_reject', 'score_skip', 'budget_exceeded'
            decision: What was decided
            reason: Why the decision was made
            job_id: Associated job, if applicable
            context: Additional context as a dict (stored as JSON string)

        Returns:
            The persisted DecisionLog entry.
        """
        entry = DecisionLog(
            id=str(uuid4()),
            job_id=job_id,
            decision_type=decision_type,
            decision=decision,
            reason=reason,
            context_json=json.dumps(context) if context is not None else None,
        )
        self.session.add(entry)
        self.session.commit()
        return entry
