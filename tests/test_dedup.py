"""Tests for deduplication logic (dedup.py)."""

from __future__ import annotations

import pytest

from jobinator.pipelines.dedup import is_duplicate


def _make_existing(company_slug: str, title_normalized: str, description_hash: str) -> dict:
    return {
        "company_slug": company_slug,
        "title_normalized": title_normalized,
        "description_hash": description_hash,
    }


def test_exact_slug_match_is_duplicate():
    """Same company_slug + title_normalized is detected as an exact match."""
    existing = [_make_existing("anthropic", "senior ml engineer", "abc123")]
    duplicate, reason = is_duplicate("anthropic", "senior ml engineer", "xyz999", existing)
    assert duplicate is True
    assert reason == "exact_match"


def test_different_company_not_duplicate():
    """Same title but different company_slug is not a duplicate."""
    existing = [_make_existing("anthropic", "senior ml engineer", "abc123")]
    duplicate, reason = is_duplicate("openai", "senior ml engineer", "xyz999", existing)
    assert duplicate is False
    assert reason is None


def test_fuzzy_company_match():
    """Near-identical company slugs with same title trigger fuzzy match."""
    existing = [_make_existing("anthropic", "senior ml engineer", "abc123")]
    # "anthropic" vs "anthropic-ai" — ratio should be > 85
    duplicate, reason = is_duplicate(
        "anthropic-ai", "senior ml engineer", "xyz999", existing, fuzzy_threshold=85
    )
    assert duplicate is True
    assert reason == "fuzzy_match"


def test_fuzzy_below_threshold_not_duplicate():
    """Dissimilar company slugs stay below threshold."""
    existing = [_make_existing("acme", "senior ml engineer", "abc123")]
    duplicate, reason = is_duplicate("zenith", "senior ml engineer", "xyz999", existing)
    assert duplicate is False
    assert reason is None


def test_description_hash_secondary():
    """Same description_hash with same company_slug but different title is flagged."""
    existing = [_make_existing("anthropic", "senior ml engineer", "abc123abc123abcd")]
    # Different title but same description_hash — should match on hash layer
    duplicate, reason = is_duplicate("anthropic", "staff engineer", "abc123abc123abcd", existing)
    assert duplicate is True
    assert reason == "description_hash_match"


def test_empty_existing_no_duplicate():
    """Empty existing list never reports a duplicate."""
    duplicate, reason = is_duplicate("anthropic", "senior ml engineer", "abc123", [])
    assert duplicate is False
    assert reason is None
