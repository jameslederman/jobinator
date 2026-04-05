---
phase: 01-foundation
plan: 02
subsystem: pipelines
tags: [normalization, dedup, filter, pipeline, tdd]
dependency_graph:
  requires: ["01-01"]
  provides: ["pipeline-normalize", "pipeline-dedup", "pipeline-filter"]
  affects: ["02-discovery", "03-scoring"]
tech_stack:
  added: ["rapidfuzz"]
  patterns: ["TDD red-green", "Pydantic config objects", "deterministic slug generation"]
key_files:
  created:
    - src/jobinator/pipelines/normalize.py
    - src/jobinator/pipelines/dedup.py
    - src/jobinator/pipelines/filter.py
    - tests/test_normalize.py
    - tests/test_dedup.py
    - tests/test_filter.py
  modified:
    - src/jobinator/pipelines/__init__.py
    - src/jobinator/configs/settings.py
decisions:
  - "Removed 'co' from company suffix strip list to prevent false positives (Big Co Technologies -> big-co, not big)"
  - "FilterConfig is a plain Pydantic BaseModel (not SQLModel) — config objects, not DB tables"
  - "load_filter_config uses stdlib tomllib (Python 3.11+) with tomli fallback — no extra dependency"
  - "get_filter_config added to settings.py using lazy import to avoid circular imports"
metrics:
  duration_minutes: 4
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_created: 6
  files_modified: 2
---

# Phase 01 Plan 02: Normalization, Dedup, and Heuristic Filter Summary

**One-liner:** Three-layer normalization pipeline with rapidfuzz dedup and AND/OR/on_missing heuristic filter, TDD with 29 passing tests.

## What Was Built

### Task 1: Normalization Pipeline + Deduplication Logic

**`src/jobinator/pipelines/normalize.py`**

Transforms arbitrary raw job dicts (from any source adapter) into fully typed `NormalizedJob` instances:

- `make_company_slug(name)`: Strips common legal suffixes (Inc, LLC, Corp, Technologies, Holdings, etc.), lowercases, removes non-alphanumeric except hyphens, truncates to 40 chars. Handles multi-suffix names like "Acme Corp Inc".
- `make_title_normalized(title)`: Expands abbreviations (Sr./sr -> senior, Jr./jr -> junior, Eng./eng -> engineer), lowercases, removes non-alphanumeric, collapses whitespace.
- `make_description_hash(description)`: SHA256 of first 500 chars, returns 16 hex chars for dedup.
- `parse_salary(raw)`: Handles "$150,000-$200,000", "$150k-200k", `{"min": 150000, "max": 200000}`, and None. Returns `(min, max, salary_source)` where source is "posted" or "unknown".
- `detect_location_type(location_raw)`: Priority-order classification — remote > hybrid > onsite (keyword or city/state pattern) > unknown.
- `normalize_job(raw, source)`: Full pipeline with flexible camelCase/snake_case key aliasing, UUID generation, timestamp assignment.

**`src/jobinator/pipelines/dedup.py`**

Three-layer duplicate detection:
1. Exact compound key match: `{company_slug}::{title_normalized}`
2. Fuzzy match: rapidfuzz ratio on both company_slug AND title_normalized must exceed `fuzzy_threshold` (default 90)
3. Description hash match across all existing jobs

Also provides `get_existing_job_keys(session)` for loading the existing set from the DB.

### Task 2: Heuristic Hard Filter

**`src/jobinator/pipelines/filter.py`**

Implements D-06 through D-09 filter semantics:

```
AND between groups: salary AND location AND title_include must all pass
OR within groups: any keyword in title_include = pass
Exclude before include (D-09): title_exclude and company_exclude checked first
on_missing: per-filter control (pass/fail/estimate) for absent fields
```

Models: `FilterConfig`, `SalaryFilter`, `LocationFilter`, `TitleFilter`, `OnMissing` (enum), `FilterResult`.

`apply_hard_filters(job, config)` evaluation order:
1. title.exclude — immediate reject if any keyword matches
2. company_exclude — immediate reject if any keyword matches company_slug
3. salary floor — with on_missing handling
4. location.allowed — with on_missing handling
5. title.include — OR logic, reject if no keyword matches

`load_filter_config(config_dir)` reads `[filter.*]` TOML sections. `get_filter_config()` added to settings.py for app-level access.

## Tests Written (29 total, all passing)

- `test_normalize.py`: 11 tests covering basic normalization, suffix stripping, title variants, salary parsing (3 formats), missing salary, location detection, description hash, UUID generation, camelCase keys
- `test_dedup.py`: 6 tests covering exact match, different company, fuzzy match (above/below threshold), hash match, empty existing set
- `test_filter.py`: 12 tests covering all D-06 through D-09 filter semantics

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed "co" from company suffix list to prevent false positives**

- **Found during:** Task 1 test execution (RED->GREEN cycle)
- **Issue:** "Big Co Technologies" normalized to "big" instead of "big-co" because the suffix stripping loop stripped "Technologies" first, then "Co" as a trailing word, leaving only "Big"
- **Fix:** Removed "co" from `_COMPANY_SUFFIXES` — "co" is too short/ambiguous to safely strip. "Corp", "Inc", "LLC" etc. are unambiguous abbreviations that are safe to strip.
- **Files modified:** `src/jobinator/pipelines/normalize.py`
- **Impact:** "Acme Corp." still strips to "acme" (Corp is unambiguous); "Big Co Technologies" correctly strips to "big-co"
- **Commit:** c8db47e

## Known Stubs

None — all pipeline functions are fully implemented with real logic.

## Self-Check: PASSED
