"""Tests for the normalization pipeline (normalize.py)."""

from __future__ import annotations

import pytest

from jobinator.pipelines.normalize import (
    detect_location_type,
    make_company_slug,
    make_description_hash,
    make_title_normalized,
    normalize_job,
    parse_salary,
)


def test_normalize_basic_job():
    """Raw dict normalizes to NormalizedJob with expected fields."""
    raw = {
        "title": "Senior ML Engineer",
        "company": "Anthropic Inc.",
        "description": "Build the future of AI systems.",
        "source_url": "https://example.com/job/1",
        "salary_raw": "$150,000 - $200,000",
    }
    job = normalize_job(raw, source="test")
    assert job.title == "Senior ML Engineer"
    assert job.title_normalized == "senior ml engineer"
    assert job.company == "Anthropic Inc."
    assert job.company_slug == "anthropic"
    assert job.salary_source == "posted"
    assert job.source == "test"


def test_normalize_strips_company_suffixes():
    """Company suffixes are stripped to produce clean slugs."""
    assert make_company_slug("Acme Corp.") == "acme"
    assert make_company_slug("FooBar LLC") == "foobar"
    assert make_company_slug("Big Co Technologies") == "big-co"


def test_normalize_title_variants():
    """Title abbreviations are expanded before normalization."""
    assert make_title_normalized("Sr. Data Scientist") == "senior data scientist"
    assert make_title_normalized("Senior Data Scientist") == "senior data scientist"


def test_normalize_salary_parsing():
    """Salary string parses to integer min/max with salary_source=posted."""
    min_val, max_val, source = parse_salary("$150,000 - $200,000")
    assert min_val == 150000
    assert max_val == 200000
    assert source == "posted"


def test_normalize_salary_parsing_k_format():
    """Salary in k-shorthand parses correctly."""
    min_val, max_val, source = parse_salary("$150k-200k")
    assert min_val == 150000
    assert max_val == 200000
    assert source == "posted"


def test_normalize_salary_parsing_dict():
    """Salary dict format parses correctly."""
    min_val, max_val, source = parse_salary({"min": 150000, "max": 200000})
    assert min_val == 150000
    assert max_val == 200000
    assert source == "posted"


def test_normalize_missing_salary():
    """No salary info produces None fields with salary_source=unknown."""
    raw = {
        "title": "ML Engineer",
        "company": "Acme Corp",
        "description": "Some description.",
        "source_url": "https://example.com/job/2",
    }
    job = normalize_job(raw, source="test")
    assert job.salary_min is None
    assert job.salary_max is None
    assert job.salary_source == "unknown"


def test_normalize_location_detection():
    """Location strings detect remote, hybrid, and onsite correctly."""
    assert detect_location_type("Remote") == "remote"
    assert detect_location_type("Hybrid - NYC") == "hybrid"
    assert detect_location_type("San Francisco, CA") == "onsite"


def test_normalize_description_hash():
    """Same description produces same hash; different produces different; 16 hex chars."""
    text_a = "We are looking for a senior engineer."
    text_b = "Different description entirely."
    hash_a1 = make_description_hash(text_a)
    hash_a2 = make_description_hash(text_a)
    hash_b = make_description_hash(text_b)
    assert hash_a1 == hash_a2
    assert hash_a1 != hash_b
    assert len(hash_a1) == 16
    assert all(c in "0123456789abcdef" for c in hash_a1)


def test_normalize_generates_uuid_id():
    """normalize_job produces a valid UUID4 string id."""
    import re

    raw = {
        "title": "ML Engineer",
        "company": "Acme Corp",
        "description": "Some description.",
        "source_url": "https://example.com/job/3",
    }
    job = normalize_job(raw, source="test")
    uuid4_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    assert uuid4_pattern.match(job.id), f"Expected UUID4, got: {job.id}"


def test_normalize_camelcase_keys():
    """normalize_job handles camelCase key variants gracefully."""
    raw = {
        "jobTitle": "Data Scientist",
        "companyName": "TechCorp Inc",
        "description": "Great role.",
        "source_url": "https://example.com/job/4",
    }
    job = normalize_job(raw, source="test")
    assert job.title == "Data Scientist"
    assert job.company == "TechCorp Inc"
