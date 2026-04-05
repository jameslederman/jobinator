"""Deduplication logic for job postings.

Two-layer dedup strategy (D-05):
  1. Exact match: compound key {company_slug}::{title_normalized}
  2. Fuzzy match: rapidfuzz ratio on company_slug + title_normalized
  3. Hash match: description_hash match (catches copy-paste reposts)
"""

from __future__ import annotations

from rapidfuzz import fuzz
from sqlmodel import Session, select

from jobinator.models.job import NormalizedJob


def is_duplicate(
    company_slug: str,
    title_normalized: str,
    description_hash: str,
    existing_jobs: list[dict],
    fuzzy_threshold: int = 90,
) -> tuple[bool, str | None]:
    """Check whether a job already exists in the existing set.

    Detection layers (in order):
    1. Exact compound key match: {company_slug}::{title_normalized}
    2. Fuzzy match: rapidfuzz ratio on both company_slug AND title_normalized
       must both exceed fuzzy_threshold
    3. Description hash match against any existing job

    Args:
        company_slug: Normalized company slug of the candidate job
        title_normalized: Normalized title of the candidate job
        description_hash: Hash of candidate job's description
        existing_jobs: List of dicts with keys: company_slug, title_normalized,
            description_hash — typically from get_existing_job_keys()
        fuzzy_threshold: Minimum rapidfuzz ratio (0-100) for a fuzzy match

    Returns:
        (is_dup, reason) where reason is one of:
        - "exact_match": same company_slug and title_normalized
        - "fuzzy_match": both slugs fuzzy-match above threshold
        - "description_hash_match": same description_hash
        - None: no match found
    """
    candidate_key = f"{company_slug}::{title_normalized}"

    for existing in existing_jobs:
        existing_key = f"{existing['company_slug']}::{existing['title_normalized']}"

        # Layer 1: Exact compound key match
        if candidate_key == existing_key:
            return (True, "exact_match")

    # Layer 2: Fuzzy match across all existing
    for existing in existing_jobs:
        company_ratio = fuzz.ratio(company_slug, existing["company_slug"])
        title_ratio = fuzz.ratio(title_normalized, existing["title_normalized"])
        if company_ratio >= fuzzy_threshold and title_ratio >= fuzzy_threshold:
            return (True, "fuzzy_match")

    # Layer 3: Description hash match
    for existing in existing_jobs:
        if description_hash == existing["description_hash"]:
            return (True, "description_hash_match")

    return (False, None)


def get_existing_job_keys(session: Session) -> list[dict]:
    """Query NormalizedJob table for dedup key fields.

    Returns a list of dicts containing company_slug, title_normalized,
    and description_hash for all existing jobs. Used to build the
    existing_jobs list for is_duplicate().

    Args:
        session: Active SQLModel session

    Returns:
        List of dicts with keys: company_slug, title_normalized, description_hash
    """
    statement = select(
        NormalizedJob.company_slug,
        NormalizedJob.title_normalized,
        NormalizedJob.description_hash,
    )
    rows = session.exec(statement).all()
    return [
        {
            "company_slug": row[0],
            "title_normalized": row[1],
            "description_hash": row[2],
        }
        for row in rows
    ]
