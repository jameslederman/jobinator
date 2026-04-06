"""Pipeline implementations for job normalization, dedup, filtering, and scoring."""

from jobinator.pipelines.dedup import get_existing_job_keys, is_duplicate
from jobinator.pipelines.discover import DiscoveryResult, SourceResult, run_discovery
from jobinator.pipelines.filter import FilterConfig, FilterResult, apply_hard_filters
from jobinator.pipelines.normalize import (
    make_company_slug,
    make_description_hash,
    make_title_normalized,
    normalize_job,
)
from jobinator.pipelines.score import ScoringResult, get_unscored_jobs, load_profile, run_scoring

__all__ = [
    "normalize_job",
    "make_company_slug",
    "make_title_normalized",
    "make_description_hash",
    "is_duplicate",
    "get_existing_job_keys",
    "apply_hard_filters",
    "FilterConfig",
    "FilterResult",
    "run_discovery",
    "DiscoveryResult",
    "SourceResult",
    "run_scoring",
    "ScoringResult",
    "get_unscored_jobs",
    "load_profile",
]
