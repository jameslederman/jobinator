---
phase: 02-data-ingestion
plan: 01
subsystem: data-ingestion
tags: [adapters, greenhouse, lever, discovery-config, schema-migration]
dependency_graph:
  requires: []
  provides:
    - SourceAdapter Protocol (adapters/base.py)
    - GreenhouseAdapter (adapters/greenhouse.py)
    - LeverAdapter (adapters/lever.py)
    - DiscoveryConfig with get_discovery_config() (configs/settings.py)
    - NormalizedJob.is_stale field (models/job.py)
  affects:
    - All future source adapters (implement SourceAdapter Protocol)
    - Orchestrator / discovery pipeline (consumes GreenhouseAdapter, LeverAdapter)
    - DiscoveryConfig loaded by discovery orchestrator
tech_stack:
  added:
    - httpx>=0.28.1 (HTTP client for adapters)
    - beautifulsoup4>=4.14.3 (HTML stripping for Greenhouse descriptions)
    - lxml>=6.0.2 (BS4 parser backend)
    - tenacity>=9.1.4 (retry with exponential backoff)
    - python-dateutil>=2.9.0 (date parsing)
    - respx>=0.22.0 (dev: httpx mock router for adapter tests)
    - types-python-dateutil (dev: mypy stubs)
  patterns:
    - SourceAdapter: Protocol-based structural subtyping (no ABC inheritance needed)
    - DiscoveryConfig: standalone BaseModel (same pattern as FilterConfig, not Settings subclass)
    - Adapters: tenacity @retry decorator with wait_exponential + stop_after_attempt(3)
    - HTML stripping: BeautifulSoup(html, "lxml").get_text()
    - Pagination: Lever skip/limit loop, exit when len(page) < limit
key_files:
  created:
    - src/jobinator/adapters/__init__.py
    - src/jobinator/adapters/base.py
    - src/jobinator/adapters/greenhouse.py
    - src/jobinator/adapters/lever.py
    - alembic/versions/85b46b272be9_add_is_stale_to_normalized_job.py
    - tests/test_adapters.py
    - tests/fixtures/greenhouse_response.json
    - tests/fixtures/lever_response.json
  modified:
    - pyproject.toml (new runtime + dev deps)
    - uv.lock (dependency lockfile)
    - src/jobinator/models/job.py (is_stale field)
    - src/jobinator/configs/settings.py (DiscoveryConfig + get_discovery_config)
    - src/jobinator/pipelines/filter.py (type: ignore[no-redef] for tomllib)
    - .pre-commit-config.yaml (added alembic + types-python-dateutil to mypy deps)
decisions:
  - "DiscoveryConfig as standalone BaseModel (not Settings subclass) — consistent with FilterConfig pattern from Phase 1 Pitfall 7"
  - "GreenhouseAdapter: board token used as company name — user configures recognizable tokens, avoids extra API call for company name"
  - "LeverAdapter: posted_at=None always — Lever public API does not expose posting date (Pitfall 5 documented in RESEARCH)"
  - "tenacity @retry applied to inner _fetch_board/_fetch_page helpers, not the fetch() method — isolates per-board retry without aborting multi-company loops"
metrics:
  duration: 8 minutes
  completed: "2026-04-05"
  tasks: 2
  files: 14
---

# Phase 2 Plan 1: Adapters Foundation (Greenhouse + Lever) Summary

**One-liner:** SourceAdapter Protocol + GreenhouseAdapter (HTML-stripped, retry-backed) + LeverAdapter (paginated, salary passthrough) with DiscoveryConfig TOML loading and is_stale Alembic migration.

## What Was Built

### SourceAdapter Protocol (`src/jobinator/adapters/base.py`)

Defines the structural contract all adapters must implement:
- `source_id: str` — unique adapter identifier
- `fragile: bool` — True for scrapers at risk of breaking (Wellfound)
- `fetch() -> list[RawJobDict]` — returns raw job dicts for downstream normalization

Uses Python `Protocol` for structural subtyping — no ABC inheritance required. `AdapterBrokenError` exception for adapters to raise on structural breakage.

### GreenhouseAdapter (`src/jobinator/adapters/greenhouse.py`)

Fetches open jobs from `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`.

Key behaviors:
- HTML stripped from job content using BeautifulSoup + lxml parser
- tenacity retry: exponential backoff (min=2s, max=10s), 3 attempts per board
- 404 handling: logs warning, returns empty list for that board, continues
- 0.5s delay between board tokens (rate-limiting)
- Maps: title, company (=board_token), description (HTML-stripped), source_url, location_raw, posted_at

### LeverAdapter (`src/jobinator/adapters/lever.py`)

Fetches postings from `https://api.lever.co/v0/postings/{company}?mode=json`.

Key behaviors:
- Automatic pagination: 50 per page, loops until `len(page) < 50`
- tenacity retry: same config as Greenhouse
- HTTP error handling: logs warning, continues to next company
- salary_raw passed through as dict (currency, interval, min, max) when present
- posted_at always None (Lever public API limitation — Pitfall 5)
- Maps: title (=text), company, description (=descriptionPlain), source_url (=hostedUrl), location_raw (=categories.location)

### DiscoveryConfig (`src/jobinator/configs/settings.py`)

Standalone `BaseModel` (not a Settings subclass — Phase 1 Pitfall 7 pattern):
- `greenhouse: list[str]` — board tokens
- `lever: list[str]` — company slugs
- `wellfound_keywords: list[str]`, `wellfound_companies: list[str]`
- `stale_after_days: int = 14`
- `hn_months_back: int = 1`
- `rate_limit_delay_min/max: float`

`get_discovery_config(config_dir=None)` reads `[discovery]` section from config.toml, returns safe defaults if absent.

### NormalizedJob.is_stale Field

Added `is_stale: bool = Field(default=False)` to NormalizedJob. Alembic migration `85b46b272be9` adds the column to the SQLite database.

## Tests

26 tests in `tests/test_adapters.py`, all passing:
- 5 DiscoveryConfig default/loading tests
- 2 get_discovery_config tests (no file / reads TOML)
- 2 is_stale field tests
- 5 SourceAdapter Protocol / AdapterBrokenError tests
- 6 GreenhouseAdapter tests (fetch, multi-company, field mapping, HTML stripping, 404 handling, source_id/fragile)
- 6 LeverAdapter tests (fetch, field mapping, salary passthrough, pagination, HTTP error handling, source_id/fragile)

Full test suite: 80 tests, all passing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] Pre-commit mypy additional_dependencies**
- **Found during:** Task 1 commit attempt
- **Issue:** mypy pre-commit hook was failing on pre-existing files (alembic/versions/, filter.py tomllib, normalize.py dateutil stubs). While the alembic and tomllib errors were pre-existing, the dateutil stub error was introduced by adding python-dateutil as a dependency.
- **Fix:** Added `alembic` and `types-python-dateutil` to pre-commit mypy `additional_dependencies`; added `# type: ignore[no-redef]` to tomllib fallback import in both `filter.py` and `settings.py`
- **Files modified:** `.pre-commit-config.yaml`, `src/jobinator/pipelines/filter.py`
- **Commit:** 14babb1 (included in Task 1 commit)

## Known Stubs

None — all fields are wired to real data sources in tests. Adapters return real-structured dicts; no placeholder/hardcoded empty values flow to rendering.

## Self-Check: PASSED

Files verified to exist:
- `src/jobinator/adapters/__init__.py` ✓
- `src/jobinator/adapters/base.py` ✓
- `src/jobinator/adapters/greenhouse.py` ✓
- `src/jobinator/adapters/lever.py` ✓
- `alembic/versions/85b46b272be9_add_is_stale_to_normalized_job.py` ✓
- `tests/test_adapters.py` ✓
- `tests/fixtures/greenhouse_response.json` ✓
- `tests/fixtures/lever_response.json` ✓

Commits verified:
- Task 1: 14babb1 ✓
- Task 2: 92e9b72 ✓
