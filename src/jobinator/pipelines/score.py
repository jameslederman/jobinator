"""Scoring pipeline orchestrator.

Queries unscored jobs, runs each through JobScorer with budget gating,
persists JobScore + StatusEvent per job, and stops cleanly on BudgetExceeded.
Mirrors the discover.py pattern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from jobinator.budget.tracker import BudgetExceeded
from jobinator.models.job import NormalizedJob, StatusEvent
from jobinator.models.score import JobScore

if TYPE_CHECKING:
    from jobinator.budget.tracker import BudgetTracker
    from jobinator.configs.settings import ScoringConfig
    from jobinator.scoring.scorer import JobScorer

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScoringResult:
    """Aggregated result from a scoring run."""

    scored: int = 0
    skipped: int = 0
    budget_stopped: bool = False
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


def load_profile(profile_path: str | None) -> dict | None:
    """Load JSON Resume profile from disk.

    Args:
        profile_path: Path to JSON Resume file. If None, returns None.

    Returns:
        Parsed JSON dict, or None if path is None or file doesn't exist.
    """
    if not profile_path:
        return None
    path = Path(profile_path).expanduser()
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_unscored_jobs(session: Session, limit: int) -> list[NormalizedJob]:
    """Return non-stale jobs that have no JobScore yet.

    Uses a subquery to find job_ids that already have a JobScore, then
    excludes those from the result. Also excludes stale jobs.

    Args:
        session: Active SQLModel session.
        limit: Maximum number of jobs to return.

    Returns:
        List of NormalizedJob instances to score.
    """
    scored_ids = select(JobScore.job_id)
    stmt = (
        select(NormalizedJob)
        .where(NormalizedJob.id.notin_(scored_ids))  # type: ignore[attr-defined]
        .where(NormalizedJob.is_stale == False)  # noqa: E712
        .limit(limit)
    )
    return list(session.exec(stmt))


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_scoring(
    session: Session,
    budget_tracker: "BudgetTracker",
    scorer: "JobScorer",
    config: "ScoringConfig",
) -> ScoringResult:
    """Score unscored jobs using the LLM scorer.

    Iterates unscored jobs up to config.score_batch_size. For each job:
    - Calls scorer.score_job() (which gates budget before LLM call)
    - Persists JobScore and StatusEvent
    - Stops cleanly if BudgetExceeded is raised
    - Records per-job errors without aborting the whole run

    Args:
        session: Active SQLModel session.
        budget_tracker: BudgetTracker for budget gate and decision logging.
        scorer: JobScorer orchestrating per-job LLM calls.
        config: ScoringConfig with batch size and profile path.

    Returns:
        ScoringResult with counts of scored/skipped/errors and budget flag.
    """
    result = ScoringResult()

    # Validate profile first — fail fast before querying jobs
    profile_data = load_profile(config.profile_path)
    if profile_data is None:
        result.errors.append(
            f"Profile not found at {config.profile_path or 'None (not configured)'}. "
            "Set [scoring] profile_path in config.toml or set "
            "JOBINATOR_SCORING_PROFILE_PATH."
        )
        return result

    jobs = get_unscored_jobs(session, config.score_batch_size)

    for job in jobs:
        try:
            job_score = scorer.score_job(job, profile_data)
            session.add(job_score)
            event = StatusEvent(
                job_id=job.id,
                status="scored",
                reason=(
                    f"fit_score={job_score.fit_score:.2f}, "
                    f"priority={job_score.priority_score:.2f}"
                ),
            )
            session.add(event)
            session.commit()
            result.scored += 1

            log.info(
                "Scored job %s: fit=%.2f priority=%.2f",
                job.id,
                job_score.fit_score,
                job_score.priority_score,
            )

        except BudgetExceeded:
            result.budget_stopped = True
            budget_tracker.log_decision(
                decision_type="budget_exceeded",
                decision="stop_scoring",
                reason=f"Daily spend: ${budget_tracker.daily_spend():.4f}",
                job_id=job.id,
            )
            log.warning(
                "Budget exceeded at job %s. Stopping scoring run. "
                "Daily spend: $%.4f",
                job.id,
                budget_tracker.daily_spend(),
            )
            break

        except Exception as e:  # noqa: BLE001
            err_msg = f"Error scoring {job.id}: {e}"
            result.errors.append(err_msg)
            log.error(err_msg)
            session.rollback()

    return result
