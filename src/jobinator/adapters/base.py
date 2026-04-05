"""Adapter protocol and shared types for source adapters."""

from __future__ import annotations

from typing import Protocol

from jobinator.pipelines.normalize import RawJobDict


class AdapterBrokenError(Exception):
    """Raised when an adapter detects structural breakage (e.g. Wellfound layout change)."""


class SourceAdapter(Protocol):
    """Protocol for all job source adapters.

    All adapters must expose:
      - source_id: unique string identifier (e.g. "greenhouse", "lever")
      - fragile: True for adapters that rely on scraping (e.g. Wellfound) and
                 are at high risk of breaking on layout changes
      - fetch(): returns a list of raw job dicts for downstream normalization
    """

    source_id: str  # "greenhouse", "lever", "hn_hiring", "wellfound"
    fragile: bool  # True for Wellfound — signals health monitoring priority

    def fetch(self) -> list[RawJobDict]:
        """Return raw job dicts for all configured targets."""
        ...
