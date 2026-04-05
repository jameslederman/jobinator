"""Discovery orchestrator pipeline.

Coordinates all source adapters, normalizes and deduplicates raw jobs,
persists new jobs to SQLite, marks stale jobs, and tracks source health.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from sqlmodel import Session, select

from jobinator.adapters.base import SourceAdapter
from jobinator.models.job import NormalizedJob, StatusEvent
from jobinator.pipelines.dedup import get_existing_job_keys, is_duplicate
from jobinator.pipelines.normalize import RawJobDict, normalize_job

if TYPE_CHECKING:
    from jobinator.configs.settings import DiscoveryConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SourceResult:
    """Per-adapter result summary."""

    source_id: str
    new_jobs: int = 0
    duplicate_jobs: int = 0
    error: str | None = None


@dataclass
class DiscoveryResult:
    """Aggregated result from a full discovery run."""

    sources: list[SourceResult] = field(default_factory=list)
    stale_marked: int = 0
    total_new: int = 0
    total_duplicates: int = 0


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def build_adapters(
    config: DiscoveryConfig,
    source_filter: str | None = None,
) -> list[SourceAdapter]:
    """Instantiate source adapters from DiscoveryConfig.

    Args:
        config: DiscoveryConfig with source-specific settings.
        source_filter: If provided, return only the adapter with this source_id.

    Returns:
        List of SourceAdapter instances.
    """
    from jobinator.adapters.greenhouse import GreenhouseAdapter
    from jobinator.adapters.hn_hiring import HNHiringAdapter
    from jobinator.adapters.lever import LeverAdapter
    from jobinator.adapters.wellfound import WellfoundAdapter

    adapters: list[SourceAdapter] = []

    if config.greenhouse:
        adapters.append(GreenhouseAdapter(config.greenhouse))

    if config.lever:
        adapters.append(LeverAdapter(config.lever))

    # HN Hiring always included — no per-company config needed
    adapters.append(HNHiringAdapter(config.hn_months_back))

    if config.wellfound_keywords or config.wellfound_companies:
        adapters.append(
            WellfoundAdapter(
                config.wellfound_keywords,
                config.wellfound_companies,
                config.rate_limit_delay_min,
                config.rate_limit_delay_max,
            )
        )

    if source_filter is not None:
        adapters = [a for a in adapters if a.source_id == source_filter]

    return adapters


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def update_last_seen(
    session: Session,
    company_slug: str,
    title_normalized: str,
) -> None:
    """Update last_seen_at for an existing job identified by compound key.

    Args:
        session: Active SQLModel session.
        company_slug: Normalized company slug.
        title_normalized: Normalized job title.
    """
    statement = select(NormalizedJob).where(
        NormalizedJob.company_slug == company_slug,
        NormalizedJob.title_normalized == title_normalized,
    )
    job = session.exec(statement).first()
    if job is not None:
        job.last_seen_at = datetime.utcnow()
        session.add(job)


def persist_jobs(
    session: Session,
    raw_jobs: list[RawJobDict],
    source: str,
) -> tuple[int, int]:
    """Normalize and persist raw jobs to the database.

    Fetches existing job keys ONCE (avoids N+1 queries), then for each raw
    job: normalizes, checks for duplicates, and either inserts a new job +
    StatusEvent or updates last_seen_at on the existing record.

    Args:
        session: Active SQLModel session.
        raw_jobs: List of raw job dicts from a source adapter.
        source: Source adapter identifier (e.g. "greenhouse").

    Returns:
        (new_count, dup_count) tuple.
    """
    existing_keys = get_existing_job_keys(session)
    new_count = 0
    dup_count = 0

    for raw in raw_jobs:
        normalized = normalize_job(raw, source)

        is_dup, _reason = is_duplicate(
            normalized.company_slug,
            normalized.title_normalized,
            normalized.description_hash,
            existing_keys,
        )

        if is_dup:
            update_last_seen(session, normalized.company_slug, normalized.title_normalized)
            dup_count += 1
        else:
            session.add(normalized)
            session.add(
                StatusEvent(
                    job_id=normalized.id,
                    status="discovered",
                )
            )
            # Track in-memory so within-run duplicates are detected immediately
            existing_keys.append(
                {
                    "company_slug": normalized.company_slug,
                    "title_normalized": normalized.title_normalized,
                    "description_hash": normalized.description_hash,
                }
            )
            new_count += 1

    session.commit()
    return (new_count, dup_count)


# ---------------------------------------------------------------------------
# Stale marking
# ---------------------------------------------------------------------------


def mark_stale_jobs(session: Session, stale_after_days: int) -> int:
    """Mark jobs as stale when not re-sighted within the TTL window.

    Args:
        session: Active SQLModel session.
        stale_after_days: Days before an unseen job is considered stale.

    Returns:
        Count of newly stale jobs.
    """
    cutoff = datetime.utcnow() - timedelta(days=stale_after_days)
    statement = select(NormalizedJob).where(
        NormalizedJob.last_seen_at < cutoff,
        NormalizedJob.is_stale == False,  # noqa: E712
    )
    jobs = session.exec(statement).all()

    for job in jobs:
        job.is_stale = True
        session.add(job)

    session.commit()
    return len(jobs)


# ---------------------------------------------------------------------------
# Source health tracking
# ---------------------------------------------------------------------------


def load_source_health(config_dir: str) -> dict[str, int]:
    """Load consecutive-zero-result counters from JSON sidecar file.

    Args:
        config_dir: Path to the directory containing source_health.json.

    Returns:
        Dict mapping source_id -> consecutive zero-result run count.
    """
    path = Path(config_dir) / "source_health.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_source_health(config_dir: str, health: dict[str, int]) -> None:
    """Persist source health counters to JSON sidecar file.

    Args:
        config_dir: Path to the directory containing source_health.json.
        health: Dict mapping source_id -> consecutive zero-result run count.
    """
    path = Path(config_dir) / "source_health.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(health, indent=2))


def fire_health_alerts(health: dict[str, int], console: Console) -> None:
    """Print Rich warnings for sources with 3+ consecutive zero-result runs.

    Args:
        health: Dict mapping source_id -> consecutive zero-result run count.
        console: Rich Console instance for output.
    """
    for source_id, consecutive_zeros in health.items():
        if consecutive_zeros >= 3:
            console.print(
                f"[bold yellow]WARNING[/bold yellow] Source '{source_id}' "
                f"returned 0 results for {consecutive_zeros} consecutive runs. "
                "Check adapter health or configuration.",
                style="yellow",
            )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_discovery(
    session: Session,
    config: DiscoveryConfig,
    config_dir: str,
    source_filter: str | None = None,
) -> DiscoveryResult:
    """Run discovery against all configured source adapters.

    Executes adapters sequentially (D-10), pipes results through normalize/dedup,
    persists new jobs, marks stale jobs, and updates source health counters.

    Per D-09: a failing adapter does NOT abort the run — its error is recorded
    in SourceResult.error and other adapters continue normally.

    Args:
        session: Active SQLModel session.
        config: DiscoveryConfig with adapter settings and TTL.
        config_dir: Path to directory for source_health.json sidecar.
        source_filter: If provided, only run the adapter with this source_id.

    Returns:
        DiscoveryResult with per-source summaries and aggregate counts.
    """
    adapters = build_adapters(config, source_filter=source_filter)
    health = load_source_health(config_dir)
    result = DiscoveryResult()

    for adapter in adapters:
        try:
            raw_jobs = adapter.fetch()
            new_count, dup_count = persist_jobs(session, raw_jobs, adapter.source_id)

            result.sources.append(
                SourceResult(
                    source_id=adapter.source_id,
                    new_jobs=new_count,
                    duplicate_jobs=dup_count,
                )
            )
            result.total_new += new_count
            result.total_duplicates += dup_count

            # Update health counter: increment on 0 results, reset on > 0
            if len(raw_jobs) == 0:
                health[adapter.source_id] = health.get(adapter.source_id, 0) + 1
            else:
                health[adapter.source_id] = 0

        except Exception as exc:  # noqa: BLE001
            log.warning("Source %s failed: %s", adapter.source_id, exc)
            result.sources.append(SourceResult(source_id=adapter.source_id, error=str(exc)))
            # Do NOT increment consecutive_zeros on errors — only on successful 0-result runs

    result.stale_marked = mark_stale_jobs(session, config.stale_after_days)
    save_source_health(config_dir, health)

    return result
