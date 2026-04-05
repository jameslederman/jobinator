"""Pipeline implementations for job normalization, dedup, and filtering."""

from jobinator.pipelines.dedup import get_existing_job_keys, is_duplicate
from jobinator.pipelines.filter import FilterConfig, FilterResult, apply_hard_filters
from jobinator.pipelines.normalize import (
    make_company_slug,
    make_description_hash,
    make_title_normalized,
    normalize_job,
)

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
]
