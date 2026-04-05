---
phase: 02-data-ingestion
verified: 2026-04-05T00:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
---

# Phase 2: Data Ingestion Verification Report

**Phase Goal:** Data ingestion — build adapters for Greenhouse, Lever, Wellfound, and HN Who's Hiring; implement the discovery pipeline with normalize/dedup/persist; wire to CLI discover command.
**Verified:** 2026-04-05
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

The must-haves below are drawn from the three plan frontmatter `truths` blocks (Plans 01, 02, 03), which cover requirements DISC-01, DISC-02, and DISC-03.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Greenhouse adapter fetches all open jobs from a configured board token and returns RawJobDict list | VERIFIED | `src/jobinator/adapters/greenhouse.py`: `GreenhouseAdapter.fetch()` iterates board tokens, calls `_fetch_board()` which hits `boards-api.greenhouse.io`, maps to `RawJobDict`. Tests pass. |
| 2 | Lever adapter fetches all open postings from a configured company slug and returns RawJobDict list | VERIFIED | `src/jobinator/adapters/lever.py`: `LeverAdapter.fetch()` paginates `api.lever.co`, maps via `_map_posting()`. Pagination exits when `len(page) < _PAGE_SIZE`. Tests pass. |
| 3 | Both adapters use tenacity retry with exponential backoff on HTTP errors | VERIFIED | Both files use `@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))` on their inner fetch helpers (`_fetch_board`, `_fetch_page`). |
| 4 | DiscoveryConfig loads from [discovery] section of config.toml with empty defaults | VERIFIED | `configs/settings.py`: `get_discovery_config()` reads `[discovery]` via tomllib, returns `DiscoveryConfig()` with empty-list defaults if section absent or file missing. |
| 5 | NormalizedJob has is_stale boolean field with Alembic migration applied | VERIFIED | `models/job.py` line 98: `is_stale: bool = Field(default=False, ...)`. Migration file `alembic/versions/85b46b272be9_add_is_stale_to_normalized_job.py` exists. |
| 6 | HN adapter finds the latest Who is Hiring thread via Algolia search API and parses top-level comments into RawJobDicts | VERIFIED | `hn_hiring.py`: `find_latest_hn_hiring_threads()` hits `hn.algolia.com/api/v1/search_by_date`, `fetch_thread_comments()` hits `items/{story_id}`. `parse_hn_comment()` returns `RawJobDict`. Tests pass. |
| 7 | HN adapter extracts company, title, location, and salary from pipe-delimited comment format where present | VERIFIED | `parse_hn_comment()` splits first line on `|`, extracts segments into company/title/location, scans for salary via `_SALARY_RE` regex. |
| 8 | Wellfound adapter extracts job listings from __NEXT_DATA__ JSON blob via keyword search and company pages | VERIFIED | `wellfound.py`: `extract_wellfound_next_data()` finds `script[id="__NEXT_DATA__"]`, `extract_job_nodes()` traverses `apolloState` for `JobListingSearchResult:` keys. Both keyword and company URL paths implemented in `fetch()`. Tests pass. |
| 9 | Wellfound adapter raises AdapterBrokenError immediately when __NEXT_DATA__ script tag is missing | VERIFIED | `extract_wellfound_next_data()`: raises `AdapterBrokenError("Wellfound __NEXT_DATA__ script tag not found. Adapter may be broken.")` when `script_tag is None`. |
| 10 | Wellfound adapter is marked fragile=True in code | VERIFIED | `wellfound.py` line 181: `fragile = True`. `FRAGILE_NOTICE` class attribute also present. |
| 11 | Running discover command fetches jobs from all configured sources, normalizes, deduplicates, and persists to SQLite | VERIFIED | `discover.py`: `run_discovery()` calls `build_adapters()`, loops adapters, calls `persist_jobs()` which calls `normalize_job()` and `is_duplicate()`, commits to SQLite. Integration tests confirm. |
| 12 | The same job posted on two sources appears once in the database after discovery | VERIFIED | `test_cross_source_dedup`: same `RawJobDict` from two adapters yields 1 `NormalizedJob` in DB. `result.total_duplicates == 1`. Test passes. |
| 13 | Jobs not re-sighted within stale_after_days TTL are marked is_stale=True | VERIFIED | `mark_stale_jobs()` uses `last_seen_at < cutoff AND is_stale == False` query, sets `is_stale = True`. `test_marks_old_jobs_as_stale` confirms. |
| 14 | discover --source greenhouse runs only the Greenhouse adapter | VERIFIED | `build_adapters()` filters by `source_id` when `source_filter` is provided. CLI `discover` passes `source_filter=source` to `run_discovery()`. Valid-source check at CLI validates the flag. |

**Score:** 14/14 truths verified

Additional truths from Plan 03 also confirmed:

- "A source returning zero results for 3 consecutive runs triggers a Rich warning in terminal output" — `fire_health_alerts()` prints `WARNING` when `consecutive_zeros >= 3`. `test_source_health_alert` passes.
- "A single source failing does not block other sources from completing" — `run_discovery()` wraps each adapter in `try/except Exception`, captures error in `SourceResult.error`. `test_run_discovery_error_isolation` confirms.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/jobinator/adapters/base.py` | SourceAdapter Protocol and AdapterBrokenError | VERIFIED | Contains `class SourceAdapter(Protocol)` and `class AdapterBrokenError(Exception)`. `fetch() -> list[RawJobDict]` defined. |
| `src/jobinator/adapters/greenhouse.py` | Greenhouse board API adapter | VERIFIED | `class GreenhouseAdapter`, `source_id = "greenhouse"`, `fragile = False`, hits `boards-api.greenhouse.io`, uses `@retry`, strips HTML via `BeautifulSoup`. |
| `src/jobinator/adapters/lever.py` | Lever postings API adapter | VERIFIED | `class LeverAdapter`, `source_id = "lever"`, hits `api.lever.co`, paginates with `skip/limit`, uses `@retry`. |
| `src/jobinator/adapters/hn_hiring.py` | HN Who's Hiring adapter | VERIFIED | `class HNHiringAdapter`, `source_id = "hn_hiring"`, `fragile = False`, hits `hn.algolia.com`, `parse_hn_comment()` present with pipe-delimiter logic. |
| `src/jobinator/adapters/wellfound.py` | Wellfound scraper adapter | VERIFIED | `class WellfoundAdapter`, `source_id = "wellfound"`, `fragile = True`, `__NEXT_DATA__` extraction, `AdapterBrokenError`, `FRAGILE_NOTICE`, `USER_AGENT`, `random.uniform`. |
| `src/jobinator/configs/settings.py` | DiscoveryConfig with all source fields | VERIFIED | `class DiscoveryConfig(BaseModel)` with `greenhouse`, `lever`, `wellfound_keywords`, `wellfound_companies`, `stale_after_days=14`, `hn_months_back=1`, `rate_limit_delay_min/max`. `get_discovery_config()` present. |
| `src/jobinator/pipelines/discover.py` | Discovery orchestrator | VERIFIED | `run_discovery`, `persist_jobs`, `mark_stale_jobs`, `build_adapters`, `load_source_health`, `save_source_health`, `fire_health_alerts` all present. |
| `src/jobinator/cli.py` | CLI discover command | VERIFIED | `def discover(...)` with `--source` and `--dry-run` options, calls `run_discovery()`, prints Rich table. |
| `tests/test_discover.py` | Integration tests for discovery pipeline | VERIFIED | Contains `test_cross_source_dedup`, `test_stale_marking`, `test_source_health_alert`, 13 tests total. |
| `alembic/versions/85b46b272be9_add_is_stale_to_normalized_job.py` | is_stale Alembic migration | VERIFIED | File exists. |
| `tests/fixtures/greenhouse_response.json` | Greenhouse API fixture | VERIFIED | File exists with valid JSON. |
| `tests/fixtures/lever_response.json` | Lever API fixture | VERIFIED | File exists with valid JSON. |
| `tests/fixtures/hn_thread.json` | HN Algolia thread fixture | VERIFIED | File exists with `whoishiring` content. |
| `tests/fixtures/wellfound_page.html` | Wellfound HTML fixture | VERIFIED | File exists with `__NEXT_DATA__` and `JobListingSearchResult` content. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `greenhouse.py` | `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` | `httpx.Client.get` with tenacity retry | WIRED | `_GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"`, called in `_fetch_board()` with `@retry` |
| `lever.py` | `https://api.lever.co/v0/postings/{company}` | `httpx.Client.get` with tenacity retry | WIRED | `_LEVER_API = "https://api.lever.co/v0/postings/{company}"`, called in `_fetch_page()` with `@retry` |
| `hn_hiring.py` | `https://hn.algolia.com/api/v1/search_by_date` | `httpx.Client.get` to find latest Who is Hiring thread | WIRED | `_ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"`, called in `find_latest_hn_hiring_threads()` |
| `wellfound.py` | `https://wellfound.com/role/` | `httpx.Client.get` + BeautifulSoup `__NEXT_DATA__` extraction | WIRED | `_KEYWORD_URL = "https://wellfound.com/role/l/{slug}/remote"`, fetched in `_fetch_page()`, parsed by `extract_wellfound_next_data()` |
| `discover.py` | `src/jobinator/adapters/` | `build_adapters()` instantiates all four adapter classes | WIRED | `build_adapters()` imports and instantiates `GreenhouseAdapter`, `LeverAdapter`, `HNHiringAdapter`, `WellfoundAdapter` based on `DiscoveryConfig` |
| `discover.py` | `pipelines/normalize.py` | `normalize_job(raw, source)` for each `RawJobDict` | WIRED | `from jobinator.pipelines.normalize import RawJobDict, normalize_job`. Called in `persist_jobs()`. |
| `discover.py` | `pipelines/dedup.py` | `is_duplicate()` and `get_existing_job_keys()` | WIRED | `from jobinator.pipelines.dedup import get_existing_job_keys, is_duplicate`. Both called in `persist_jobs()`. |
| `cli.py` | `pipelines/discover.py` | `discover` command calls `run_discovery()` | WIRED | `from jobinator.pipelines.discover import fire_health_alerts, load_source_health, run_discovery`. `run_discovery(session, config, settings.config_dir, source_filter=source)` called directly. |

---

### Data-Flow Trace (Level 4)

The adapters return `RawJobDict` lists, which flow to `normalize_job()` which returns `NormalizedJob` objects, which are persisted to SQLite. The data pipeline is fully connected:

| Component | Data Variable | Source | Produces Real Data | Status |
|-----------|---------------|--------|--------------------|--------|
| `GreenhouseAdapter.fetch()` | `jobs: list[RawJobDict]` | `boards-api.greenhouse.io` JSON response | Yes — parsed from `response.json()["jobs"]` | FLOWING |
| `LeverAdapter.fetch()` | `all_jobs: list[RawJobDict]` | `api.lever.co` JSON response | Yes — parsed from paginated `response.json()` | FLOWING |
| `HNHiringAdapter.fetch()` | `all_jobs: list[RawJobDict]` | Algolia `items/{id}` children | Yes — parsed from `response.json()["children"]` | FLOWING |
| `WellfoundAdapter.fetch()` | `all_jobs: list[RawJobDict]` | `__NEXT_DATA__` Apollo state | Yes — extracted from `JobListingSearchResult:` keys | FLOWING |
| `persist_jobs()` | `NormalizedJob` + `StatusEvent` | `normalize_job(raw, source)` output | Yes — written to SQLite with `session.commit()` | FLOWING |

Note: `--dry-run` flag is accepted by the CLI but does not currently skip persistence. This is a known deviation documented in the SUMMARY as intentional (flag defined for future use). It does not break any `must_have` truth since none required `--dry-run` to suppress persistence.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest tests/ -x -q` | 109 passed, 84 warnings | PASS |
| Adapter + discovery tests pass | `uv run pytest tests/test_adapters.py tests/test_discover.py -x -q` | 55 passed, 42 warnings | PASS |
| CLI `discover --help` shows correct options | `uv run python -m jobinator.cli discover --help` | Shows `--source`, `--dry-run`, `--help` | PASS |
| Ruff lint passes on all phase 2 files | `uv run ruff check src/jobinator/adapters/ ...` | All checks passed | PASS |

---

### Requirements Coverage

Requirements claimed by plans in this phase: DISC-01, DISC-02, DISC-03.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DISC-01 | Plans 02, 03 | User can discover jobs from Wellfound/AngelList with structured output | SATISFIED | `WellfoundAdapter` fetches from `wellfound.com`, extracts via `__NEXT_DATA__`, maps to `RawJobDict`, piped through `run_discovery()` to SQLite. `discover` CLI command exposes it. |
| DISC-02 | Plans 01, 03 | User can discover jobs from Greenhouse/Lever ATS career pages with structured output | SATISFIED | `GreenhouseAdapter` and `LeverAdapter` fetch from public JSON APIs, map to `RawJobDict`. Both instantiated by `build_adapters()`, accessible via `jobinator discover`. |
| DISC-03 | Plans 02, 03 | User can discover jobs from HN Who's Hiring threads with structured output | SATISFIED | `HNHiringAdapter` finds threads via Algolia, parses top-level comments into `RawJobDict`. Included unconditionally in `build_adapters()`. |

**Orphaned requirements check:** REQUIREMENTS.md Traceability table maps DISC-01, DISC-02, DISC-03 to Phase 2. All three are claimed in plan frontmatter and verified. No orphaned requirements.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `cli.py` | `--dry-run` flag accepted but `dry_run` variable is never used in the function body | Info | Flag has no effect; persistence always runs regardless of flag value. Documented intentional in SUMMARY. Does not break any must-have. |

No TODO/FIXME/placeholder patterns found in any phase 2 source files. No empty returns or hardcoded empty data flowing to rendering.

---

### Human Verification Required

None — all must-have truths are verifiable programmatically. The adapters make real HTTP requests (tested via respx mocks), the pipeline is fully wired, and the CLI help text confirms correct option registration.

One item of note for future manual testing:

**Test: Wellfound adapter against live site**
- **Test:** Run `jobinator discover --source wellfound` against a real config with Wellfound keywords
- **Expected:** Adapter either returns job listings or raises `AdapterBrokenError` if site structure has changed
- **Why human:** Requires live network access and a configured `config.toml`; cannot verify without running against real Wellfound pages

---

### Gaps Summary

No gaps. All 14 must-have truths are verified. All required artifacts exist, are substantive, and are wired. All key links are confirmed in source code. The full test suite (109 tests) passes. Requirements DISC-01, DISC-02, and DISC-03 are all satisfied.

The only notable item is the `--dry-run` flag being a no-op, which is explicitly documented in the SUMMARY as intentional deferral and does not constitute a gap against any stated must-have.

---

_Verified: 2026-04-05_
_Verifier: Claude (gsd-verifier)_
