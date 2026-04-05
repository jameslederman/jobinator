"""Tests for the heuristic hard filter pipeline (filter.py)."""

from __future__ import annotations

import pytest
from datetime import datetime

from jobinator.models.job import NormalizedJob
from jobinator.pipelines.filter import (
    FilterConfig,
    FilterResult,
    LocationFilter,
    OnMissing,
    SalaryFilter,
    TitleFilter,
    apply_hard_filters,
)


def _make_job(**overrides) -> NormalizedJob:
    """Create a minimal NormalizedJob for filter tests (no DB needed)."""
    defaults = {
        "id": "test-id",
        "source": "test",
        "source_url": "https://example.com/job/1",
        "title": "ML Engineer",
        "title_normalized": "ml engineer",
        "company": "Acme Corp",
        "company_slug": "acme",
        "description": "Great role building ML systems.",
        "description_hash": "abc123abc123abcd",
        "raw_json": "{}",
        "first_seen_at": datetime(2026, 1, 1),
        "last_seen_at": datetime(2026, 1, 1),
    }
    defaults.update(overrides)
    return NormalizedJob(**defaults)


def test_job_passes_all_filters():
    """Job meeting all criteria passes with a permissive default config."""
    job = _make_job(salary_max=200000, location_type="remote", title="ML Engineer")
    config = FilterConfig(
        salary=SalaryFilter(min_usd=150000),
        location=LocationFilter(allowed=["remote", "hybrid"]),
        title=TitleFilter(include=["ML"]),
    )
    result = apply_hard_filters(job, config)
    assert result.passed is True
    assert result.reason is None


def test_salary_below_floor_rejected():
    """Job with salary_max below floor is rejected with salary in reason."""
    job = _make_job(salary_max=100000)
    config = FilterConfig(salary=SalaryFilter(min_usd=150000))
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "salary" in result.reason.lower()


def test_salary_missing_on_missing_pass():
    """Job with no salary passes when on_missing=pass."""
    job = _make_job(salary_min=None, salary_max=None)
    config = FilterConfig(
        salary=SalaryFilter(min_usd=150000, on_missing=OnMissing.pass_)
    )
    result = apply_hard_filters(job, config)
    assert result.passed is True


def test_salary_missing_on_missing_fail():
    """Job with no salary is rejected when on_missing=fail with 'salary missing' in reason."""
    job = _make_job(salary_min=None, salary_max=None)
    config = FilterConfig(
        salary=SalaryFilter(min_usd=150000, on_missing=OnMissing.fail)
    )
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "salary missing" in result.reason.lower()


def test_location_not_in_allowed():
    """Job with location_type not in allowed list is rejected with location_type in reason."""
    job = _make_job(location_type="onsite")
    config = FilterConfig(location=LocationFilter(allowed=["remote", "hybrid"]))
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "location_type" in result.reason.lower()


def test_title_exclude_rejects():
    """Job title containing an exclude keyword is rejected with title_exclude in reason."""
    job = _make_job(title="Senior Manager of Engineering", title_normalized="senior manager of engineering")
    config = FilterConfig(title=TitleFilter(exclude=["manager"]))
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "title_exclude" in result.reason.lower()


def test_title_exclude_checked_before_include():
    """Exclude beats include (D-09): title matching both include and exclude is rejected."""
    job = _make_job(title="ML Manager", title_normalized="ml manager")
    config = FilterConfig(
        title=TitleFilter(include=["ML"], exclude=["manager"])
    )
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "title_exclude" in result.reason.lower()


def test_title_include_or_logic():
    """Any single keyword in include list causes pass (OR within group, D-07)."""
    job = _make_job(title="Data Science Lead", title_normalized="data science lead")
    config = FilterConfig(title=TitleFilter(include=["ML", "data science"]))
    result = apply_hard_filters(job, config)
    assert result.passed is True


def test_title_include_no_match():
    """Title matching no include keywords is rejected."""
    job = _make_job(title="Product Designer", title_normalized="product designer")
    config = FilterConfig(title=TitleFilter(include=["ML", "data science"]))
    result = apply_hard_filters(job, config)
    assert result.passed is False


def test_company_exclude():
    """Company slug matching an exclude keyword is rejected."""
    job = _make_job(company_slug="facebook-meta")
    config = FilterConfig(company_exclude=["facebook"])
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "company_exclude" in result.reason.lower()


def test_and_between_groups():
    """AND between filter groups: passing salary but failing location -> rejected."""
    job = _make_job(salary_max=200000, location_type="onsite")
    config = FilterConfig(
        salary=SalaryFilter(min_usd=150000),
        location=LocationFilter(allowed=["remote", "hybrid"]),
    )
    result = apply_hard_filters(job, config)
    assert result.passed is False
    assert "location_type" in result.reason.lower()


def test_empty_config_passes_all():
    """Default FilterConfig with no constraints passes every job."""
    job = _make_job(
        salary_min=None,
        salary_max=None,
        location_type=None,
        title="Something Random",
        title_normalized="something random",
    )
    config = FilterConfig()
    result = apply_hard_filters(job, config)
    assert result.passed is True
