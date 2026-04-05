"""Heuristic hard filter for job postings.

Implements rule-based rejection before any LLM budget is spent.

Filter semantics (D-06 through D-09):
- AND between filter groups (salary AND location AND title_include)
- OR within groups (any keyword in title_include matches = pass)
- Exclude lists are checked before include lists (D-09: reject beats include)
- on_missing controls behavior when the filtered field is absent
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from jobinator.models.job import NormalizedJob


class OnMissing(str, Enum):
    """What to do when a filtered field is absent from the job posting."""

    pass_ = "pass"
    fail = "fail"
    estimate = "estimate"  # Reserved for future salary estimation feature


class SalaryFilter(BaseModel):
    """Filter jobs by minimum salary floor."""

    min_usd: int | None = None
    on_missing: OnMissing = OnMissing.pass_


class LocationFilter(BaseModel):
    """Filter jobs by allowed location types."""

    allowed: list[str] = ["remote", "hybrid"]
    on_missing: OnMissing = OnMissing.pass_


class TitleFilter(BaseModel):
    """Filter jobs by title keywords.

    include: OR-logic — job title must match at least one keyword (if non-empty)
    exclude: checked before include — any match rejects the job (D-09)
    """

    include: list[str] = []
    exclude: list[str] = []


class FilterConfig(BaseModel):
    """Top-level filter configuration.

    Can be loaded from a TOML config file under [filter.*] sections.

    Example TOML:
        [filter.salary]
        min_usd = 150000
        on_missing = "pass"

        [filter.location]
        allowed = ["remote", "hybrid"]

        [filter.title]
        include = ["ML", "machine learning", "data science", "AI"]
        exclude = ["manager", "director", "VP"]

        [filter]
        company_exclude = []
    """

    salary: SalaryFilter = SalaryFilter()
    location: LocationFilter = LocationFilter()
    title: TitleFilter = TitleFilter()
    company_exclude: list[str] = []


class FilterResult(BaseModel):
    """Result of applying hard filters to a job."""

    passed: bool
    reason: str | None = None


def apply_hard_filters(job: NormalizedJob, config: FilterConfig) -> FilterResult:
    """Apply rule-based hard filters to a job posting.

    Filter order (AND between groups, short-circuits on first failure):
    1. Title exclude (D-09: reject beats include)
    2. Company exclude
    3. Salary floor
    4. Location type
    5. Title include

    Args:
        job: Normalized job to evaluate
        config: Filter configuration with thresholds and keyword lists

    Returns:
        FilterResult with passed=True or passed=False and a rejection reason
    """
    title_lower = (job.title or "").lower()
    company_slug_lower = (job.company_slug or "").lower()

    # --- 1. Title exclude (D-09: checked before include) ---
    for keyword in config.title.exclude:
        if keyword.lower() in title_lower:
            return FilterResult(passed=False, reason=f"title_exclude: '{keyword}'")

    # --- 2. Company exclude ---
    for keyword in config.company_exclude:
        if keyword.lower() in company_slug_lower:
            return FilterResult(passed=False, reason=f"company_exclude: '{keyword}'")

    # --- 3. Salary filter ---
    if config.salary.min_usd is not None:
        effective_salary = job.salary_max or job.salary_min
        if effective_salary is None:
            if config.salary.on_missing == OnMissing.fail:
                return FilterResult(
                    passed=False,
                    reason="salary missing (on_missing=fail)",
                )
            # on_missing=pass or estimate: continue to next filter
        elif effective_salary < config.salary.min_usd:
            return FilterResult(
                passed=False,
                reason=f"salary {effective_salary} < floor {config.salary.min_usd}",
            )

    # --- 4. Location filter ---
    if config.location.allowed:
        if job.location_type is None:
            if config.location.on_missing == OnMissing.fail:
                return FilterResult(
                    passed=False,
                    reason="location_type missing (on_missing=fail)",
                )
            # on_missing=pass: continue
        elif job.location_type not in config.location.allowed:
            return FilterResult(
                passed=False,
                reason=f"location_type {job.location_type!r} not in allowed",
            )

    # --- 5. Title include (OR within group, D-07) ---
    if config.title.include:
        matched = any(kw.lower() in title_lower for kw in config.title.include)
        if not matched:
            return FilterResult(
                passed=False,
                reason="title matches none of title_include list",
            )

    return FilterResult(passed=True)


def load_filter_config(config_dir: str) -> FilterConfig:
    """Load FilterConfig from the [filter] section of config.toml.

    Falls back to default FilterConfig if the file doesn't exist or
    has no [filter] section.

    Args:
        config_dir: Path to the directory containing config.toml

    Returns:
        FilterConfig instance
    """
    import os

    toml_path = os.path.join(config_dir, "config.toml")
    if not os.path.exists(toml_path):
        return FilterConfig()

    try:
        import tomllib  # stdlib in Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]  # fallback for older Python
        except ImportError:
            return FilterConfig()

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    filter_data = data.get("filter", {})
    return FilterConfig(**filter_data)
