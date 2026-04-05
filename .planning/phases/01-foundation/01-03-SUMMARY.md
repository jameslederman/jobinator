---
phase: 01-foundation
plan: "03"
subsystem: budget-and-output
tags: [budget, output, tracker, decision-log, symlinks]
dependency_graph:
  requires: ["01-01"]
  provides: ["budget-tracker", "output-manager"]
  affects: ["03-llm", "04-materials"]
tech_stack:
  added: []
  patterns:
    - "BudgetTracker wraps SQLModel session with sum queries using func.coalesce for null-safe aggregation"
    - "UTC midnight boundaries via datetime.utcnow().replace(...) to match naive utcnow() stored datetimes"
    - "OutputManager uses Path.expanduser().resolve() for tilde expansion + absolute path normalization"
    - "latest symlink unlinked then re-created on each create_application_dir call (handles first-time and update)"
key_files:
  created:
    - src/jobinator/budget/tracker.py
    - src/jobinator/output/manager.py
    - tests/test_budget.py
    - tests/test_output.py
  modified:
    - src/jobinator/budget/__init__.py
    - src/jobinator/output/__init__.py
decisions:
  - "Use datetime.utcnow() boundaries (not date.today()) for daily_spend() to match naive utcnow() in SpendRecord.recorded_at"
  - "BudgetConfig as a standalone Pydantic BaseModel (not Settings subclass) to allow test overrides without config file"
  - "latest symlink points to absolute path of app_dir for reliable resolution regardless of cwd"
metrics:
  duration_minutes: 3
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_created: 4
  files_modified: 2
---

# Phase 01 Plan 03: Budget Tracking and Output Manager Summary

**One-liner:** SQLite-backed BudgetTracker with configurable daily/per-job hard-stop gates and DecisionLog auditability, plus OutputManager with company/role/timestamp directory structure and auto-updated `latest` symlinks.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | BudgetTracker with hard-stop gate and decision logging | 041dfbd | src/jobinator/budget/tracker.py, src/jobinator/budget/__init__.py, tests/test_budget.py |
| 2 | Output directory manager with structure and symlinks | 6b17459 | src/jobinator/output/manager.py, src/jobinator/output/__init__.py, tests/test_output.py |

## What Was Built

### BudgetTracker (`src/jobinator/budget/tracker.py`)

- `BudgetExceeded` exception — raised before any LLM call when limits are exceeded
- `BudgetConfig` — Pydantic BaseModel with `daily_limit_usd`, `per_job_limit_usd`, `warn_threshold`
- `BudgetTracker` — session-bound tracker with:
  - `daily_spend()` — sums `cost_usd` for today (UTC) using `func.coalesce(func.sum(...), 0.0)`
  - `job_spend(job_id)` — sums `cost_usd` per job
  - `is_near_limit()` — returns True at warn_threshold × daily_limit_usd
  - `assert_within_limits(job_id=None)` — hard gate, raises `BudgetExceeded` with descriptive messages
  - `record(spend)` — persists `SpendRecord` to DB
  - `log_decision(...)` — persists `DecisionLog` for agent auditability (INFR-06)

### OutputManager (`src/jobinator/output/manager.py`)

- `BUNDLE_FILES` — 9-file expected bundle list: resume.pdf, cover_letter.pdf, prep_brief.pdf, resume.md, cover_letter.md, prep_brief.md, job_description.md, scoring.json, metadata.json (D-11)
- `make_role_slug(title)` — filesystem-safe slug from job title
- `OutputManager` — base_dir-scoped manager with:
  - `create_application_dir(company_slug, role_slug, timestamp)` — creates `{base}/{company}/{role}/{ts}/` and updates `latest` symlink (D-10, D-12)
  - `get_bundle_manifest()` — returns `BUNDLE_FILES` copy
  - `write_metadata(app_dir, metadata)` — serializes metadata dict to `metadata.json`
  - `write_job_snapshot(app_dir, job_description)` — writes `job_description.md`

## Test Coverage

- 11 tests in `tests/test_budget.py` — all passing
- 7 tests in `tests/test_output.py` — all passing
- Total: 18 tests, 0 failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed UTC date boundary mismatch in daily_spend()**

- **Found during:** Task 1, GREEN phase
- **Issue:** `datetime.combine(date.today(), datetime.min.time())` uses the local system date (e.g., April 4 PDT), but `SpendRecord.recorded_at` defaults to `datetime.utcnow()` (UTC, e.g., April 5). The "today" window was computed in local time, causing records created at UTC midnight+N hours to fall outside the window on machines where UTC is ahead of local time.
- **Fix:** Changed `daily_spend()` to compute UTC midnight boundaries using `datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)`, consistent with the `utcnow()` default in `SpendRecord`.
- **Files modified:** `src/jobinator/budget/tracker.py`
- **Commit:** 041dfbd (included in GREEN phase commit)

## Known Stubs

None — all implemented functionality is fully wired. No placeholder data or hardcoded empty values.

## Self-Check: PASSED

- [x] `src/jobinator/budget/tracker.py` exists and contains `class BudgetTracker`, `class BudgetExceeded`, `def assert_within_limits`, `def daily_spend`, `def job_spend`, `def log_decision`, `def is_near_limit`
- [x] `src/jobinator/output/manager.py` exists and contains `class OutputManager`, `def create_application_dir`, `def write_metadata`, `BUNDLE_FILES` (9 items), `latest` symlink logic, `resume.pdf`, `metadata.json`
- [x] `tests/test_budget.py` contains 11 test functions (>= 8 required)
- [x] `tests/test_output.py` contains 7 test functions (>= 6 required)
- [x] `uv run pytest tests/test_budget.py tests/test_output.py` exits 0 — 18 passed
- [x] Commit e11fdc9 (test RED budget), 041dfbd (feat GREEN budget), 218a35f (test RED output), 6b17459 (feat GREEN output) all exist
