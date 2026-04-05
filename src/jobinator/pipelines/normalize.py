"""Raw job dict normalization pipeline.

Transforms arbitrary raw job dicts (from any source adapter) into a fully
typed NormalizedJob instance with deterministic slugs, hashes, and parsed
salary/location fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from jobinator.models.job import NormalizedJob

# Type alias for incoming raw data
RawJobDict = dict[str, Any]

# Company name suffixes to strip (case-insensitive, optional trailing period)
_COMPANY_SUFFIXES = [
    "technologies",
    "technology",
    "holdings",
    "company",
    "group",
    "corp",
    "inc",
    "llc",
    "ltd",
    "tech",
]

# Pattern: comma/space-separated suffix list, each word followed by optional period
_SUFFIX_PATTERN = re.compile(
    r"\s*\b(?:" + "|".join(_COMPANY_SUFFIXES) + r")\.?\s*$",
    re.IGNORECASE,
)

# Title abbreviation normalization mappings (applied in order)
_TITLE_REPLACEMENTS = [
    (re.compile(r"\bsr\.?\b", re.IGNORECASE), "senior"),
    (re.compile(r"\bjr\.?\b", re.IGNORECASE), "junior"),
    (re.compile(r"\beng\.?\b", re.IGNORECASE), "engineer"),
]

# City/state pattern heuristic: e.g. "San Francisco, CA"
_CITY_STATE_PATTERN = re.compile(r"[A-Za-z\s]+,\s*[A-Z]{2}")


def make_company_slug(name: str) -> str:
    """Generate a deterministic slug from a company name.

    Strips common legal suffixes (Inc, LLC, Corp, etc.), lowercases,
    removes non-alphanumeric characters except hyphens, collapses spaces
    to hyphens, and truncates to 40 characters.

    Examples:
        "Anthropic Inc." -> "anthropic"
        "FooBar LLC" -> "foobar"
        "Big Co Technologies" -> "big-co"
    """
    slug = name.strip()

    # Strip trailing suffixes iteratively (handles multiple, e.g. "Corp Inc")
    prev = None
    while prev != slug:
        prev = slug
        slug = _SUFFIX_PATTERN.sub("", slug).strip()

    # Lowercase
    slug = slug.lower()
    # Keep only alphanumeric, spaces, hyphens
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    # Collapse whitespace to single hyphen
    slug = re.sub(r"\s+", "-", slug.strip())
    # Collapse consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate to 40 characters
    return slug[:40]


def make_title_normalized(title: str) -> str:
    """Normalize a job title for dedup and comparison.

    Expands common abbreviations (Sr. -> senior, Jr. -> junior, Eng. -> engineer),
    lowercases, removes non-alphanumeric except spaces, and collapses whitespace.

    Examples:
        "Sr. Data Scientist" -> "senior data scientist"
        "Senior Data Scientist" -> "senior data scientist"
    """
    result = title
    for pattern, replacement in _TITLE_REPLACEMENTS:
        result = pattern.sub(replacement, result)
    result = result.lower()
    result = re.sub(r"[^a-z0-9\s]", " ", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def make_description_hash(description: str) -> str:
    """SHA256 of first 500 characters of description, truncated to 16 hex digits.

    Used as a secondary dedup signal (D-05).
    """
    return hashlib.sha256(description[:500].encode("utf-8")).hexdigest()[:16]


def parse_salary(
    raw: str | dict | None,
) -> tuple[int | None, int | None, str]:
    """Parse salary information into typed min/max integers.

    Handles:
    - String: "$150,000 - $200,000", "$150k-200k", "150000-200000"
    - Dict: {"min": 150000, "max": 200000}
    - None or unrecognized: returns (None, None, "unknown")

    Returns:
        (salary_min, salary_max, salary_source) where salary_source is
        "posted" if values found, "unknown" if not.
    """
    if raw is None:
        return (None, None, "unknown")

    if isinstance(raw, dict):
        min_val = raw.get("min") or raw.get("minimum") or raw.get("salary_min")
        max_val = raw.get("max") or raw.get("maximum") or raw.get("salary_max")
        if min_val is not None or max_val is not None:
            return (
                int(min_val) if min_val is not None else None,
                int(max_val) if max_val is not None else None,
                "posted",
            )
        return (None, None, "unknown")

    if isinstance(raw, str):
        # Remove currency symbols, spaces, commas for easier parsing
        cleaned = raw.strip()

        # Pattern: $150k-200k or $150K - $200K
        k_pattern = re.compile(
            r"\$?([\d,]+)k\s*[-–—to]+\s*\$?([\d,]+)k", re.IGNORECASE
        )
        m = k_pattern.search(cleaned)
        if m:
            min_val = int(m.group(1).replace(",", "")) * 1000
            max_val = int(m.group(2).replace(",", "")) * 1000
            return (min_val, max_val, "posted")

        # Single k value: $150k
        single_k = re.compile(r"\$?([\d,]+)k", re.IGNORECASE)
        m = single_k.search(cleaned)
        if m:
            val = int(m.group(1).replace(",", "")) * 1000
            return (val, val, "posted")

        # Pattern: $150,000 - $200,000 or 150000-200000
        range_pattern = re.compile(
            r"\$?([\d,]+)\s*[-–—to]+\s*\$?([\d,]+)"
        )
        m = range_pattern.search(cleaned)
        if m:
            min_val = int(m.group(1).replace(",", ""))
            max_val = int(m.group(2).replace(",", ""))
            return (min_val, max_val, "posted")

        # Single value: $150,000
        single_pattern = re.compile(r"\$?([\d,]+)")
        m = single_pattern.search(cleaned)
        if m:
            val = int(m.group(1).replace(",", ""))
            if val > 1000:  # Sanity: must look like a salary, not a count
                return (val, val, "posted")

    return (None, None, "unknown")


def detect_location_type(location_raw: str | None) -> str:
    """Classify a location string as remote, hybrid, onsite, or unknown.

    Detection order (first match wins):
    1. "remote" keyword -> "remote"
    2. "hybrid" keyword -> "hybrid"
    3. "onsite"/"on-site"/"in-office" keyword OR city/state pattern -> "onsite"
    4. Otherwise -> "unknown"
    """
    if location_raw is None:
        return "unknown"

    text = location_raw.lower()

    if "remote" in text:
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    if "onsite" in text or "on-site" in text or "in-office" in text:
        return "onsite"
    # Heuristic: "City, ST" pattern implies onsite
    if _CITY_STATE_PATTERN.search(location_raw):
        return "onsite"

    return "unknown"


# Key mapping for flexible raw dict ingestion
_KEY_ALIASES: dict[str, list[str]] = {
    "title": ["title", "jobTitle", "job_title", "position", "name"],
    "company": ["company", "companyName", "company_name", "employer", "organization"],
    "description": ["description", "jobDescription", "job_description", "body", "content"],
    "source_url": ["source_url", "url", "jobUrl", "job_url", "applyUrl", "apply_url", "link"],
    "location_raw": ["location_raw", "location", "jobLocation", "job_location", "city"],
    "salary_raw": [
        "salary_raw",
        "salary",
        "salaryRange",
        "salary_range",
        "compensation",
        "pay",
    ],
    "requirements_raw": [
        "requirements_raw",
        "requirements",
        "qualifications",
        "skills",
    ],
    "posted_at": ["posted_at", "postedAt", "posted_date", "datePosted", "date"],
}


def _extract_field(raw: RawJobDict, field: str) -> Any:
    """Extract a field value from a raw dict using alias lookup."""
    aliases = _KEY_ALIASES.get(field, [field])
    for alias in aliases:
        if alias in raw and raw[alias] is not None:
            return raw[alias]
    return None


def normalize_job(raw: RawJobDict, source: str) -> NormalizedJob:
    """Transform a raw job dict from any source into a typed NormalizedJob.

    Applies:
    - Flexible key mapping (camelCase and snake_case variants)
    - Company slug normalization
    - Title normalization
    - Description hash generation
    - Salary parsing
    - Location type detection
    - UUID generation
    - Timestamp assignment

    Args:
        raw: Raw job dict from a source adapter
        source: Name of the source adapter (e.g. "greenhouse", "lever", "hn")

    Returns:
        NormalizedJob instance (not yet persisted to DB)
    """
    title = _extract_field(raw, "title") or ""
    company = _extract_field(raw, "company") or ""
    description = _extract_field(raw, "description") or ""
    source_url = _extract_field(raw, "source_url") or ""
    location_raw = _extract_field(raw, "location_raw")
    salary_raw = _extract_field(raw, "salary_raw")
    requirements_raw = _extract_field(raw, "requirements_raw")
    posted_at_raw = _extract_field(raw, "posted_at")

    # Normalize derived fields
    company_slug = make_company_slug(company) if company else ""
    title_normalized = make_title_normalized(title) if title else ""
    description_hash = make_description_hash(description)
    location_type = detect_location_type(location_raw)
    salary_min, salary_max, salary_source = parse_salary(salary_raw)

    # Parse posted_at if present
    posted_at = None
    if posted_at_raw:
        if isinstance(posted_at_raw, datetime):
            posted_at = posted_at_raw
        else:
            try:
                from dateutil import parser as dateutil_parser

                posted_at = dateutil_parser.parse(str(posted_at_raw))
            except Exception:
                pass

    now = datetime.utcnow()

    return NormalizedJob(
        id=str(uuid4()),
        source=source,
        source_url=source_url,
        title=title,
        title_normalized=title_normalized,
        company=company,
        company_slug=company_slug,
        location_raw=location_raw,
        location_type=location_type,
        salary_min=salary_min,
        salary_max=salary_max,
        estimated_salary_min=None,
        estimated_salary_max=None,
        salary_source=salary_source,
        description=description,
        requirements_raw=requirements_raw,
        description_hash=description_hash,
        posted_at=posted_at,
        first_seen_at=now,
        last_seen_at=now,
        raw_json=json.dumps(raw),
    )
