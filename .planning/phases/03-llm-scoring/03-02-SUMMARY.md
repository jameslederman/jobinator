---
phase: 03-llm-scoring
plan: "02"
subsystem: scoring-pipeline
tags: [llm, scoring, pipeline, cli, budget, prompt, sqlmodel, typer, rich]
dependency_graph:
  requires:
    - 03-01 (LLMClient, JobScore, JobScoreOutput, ScoringConfig)
    - 01-foundation (BudgetTracker, SpendRecord, StatusEvent)
    - 02-data-ingestion (NormalizedJob table populated by discovery)
  provides:
    - build_scoring_prompt() — formats job+profile into LLM messages
    - JobScorer — budget-gated LLM scorer with local priority computation
    - run_scoring() — pipeline orchestrator with error isolation and budget stop
    - score CLI command — end-to-end scoring with API key + profile validation
    - ScoringResult dataclass — aggregated result from scoring run
    - get_unscored_jobs() — query helper excluding scored and stale jobs
    - load_profile() — JSON Resume loader with graceful None handling
  affects:
    - 04-materials-generation (scored jobs feed into material generation phase)
tech_stack:
  added: []
  patterns:
    - Lazy imports inside CLI command (consistent with discover command pattern)
    - Module-level monkey-patching for CLI test isolation (lazy imports can't use patch())
    - Local priority score computation overrides LLM-provided value (LLM lacks recency/urgency context)
    - Budget gate called BEFORE LLM call (assert_within_limits first, then score)
    - SpendRecord persisted immediately after LLM call via budget_tracker.record()
    - ScoringResult mirrors DiscoveryResult pattern (dataclass, error list, counts)
key_files:
  created:
    - src/jobinator/scoring/prompt.py
    - src/jobinator/scoring/scorer.py
    - src/jobinator/pipelines/score.py
    - tests/fixtures/sample_resume.json
    - tests/test_scoring_pipeline.py
    - tests/test_score_cli.py
  modified:
    - src/jobinator/scoring/__init__.py
    - src/jobinator/pipelines/__init__.py
    - src/jobinator/cli.py
decisions:
  - "Local priority score computation overrides LLM priority_score — LLM doesn't have recency/urgency context, local _compute_priority() uses configurable weights with recency (30-day decay) and urgency (14-day first_seen decay)"
  - "Module-level monkey-patching for CLI tests — lazy imports inside score() function body prevent standard unittest.mock.patch() from working at jobinator.cli level; patching source module attributes directly is the correct approach"
  - "ScoringResult mirrors DiscoveryResult pattern — dataclass with scored/skipped/budget_stopped/errors, consistent with existing pipeline return type conventions"
  - "run_scoring() validates profile before querying jobs — fail fast on config error, no DB queries wasted when profile is unconfigured"
metrics:
  duration: "6 minutes"
  completed_date: "2026-04-06"
  tasks_completed: 2
  files_created: 6
  files_modified: 3
---

# Phase 3 Plan 02: Scoring Pipeline and CLI Command Summary

Implemented complete LLM scoring pipeline: prompt builder formats job+JSON Resume profile into structured messages, JobScorer gates budget before each LLM call and computes priority locally, run_scoring orchestrates unscored job iteration with error isolation and budget stop, and the `score` CLI command validates API keys and profile before invoking the pipeline with Rich output.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Prompt builder, JobScorer, and scoring pipeline orchestrator | da9ab61 | prompt.py, scorer.py, pipelines/score.py, scoring/__init__.py, pipelines/__init__.py, sample_resume.json, test_scoring_pipeline.py |
| 2 | CLI score command with budget gating and Rich output | 8835ab5 | cli.py, test_score_cli.py |

## What Was Built

### Prompt Builder (`src/jobinator/scoring/prompt.py`)

`build_scoring_prompt(job, profile_data)` returns a two-message list (system + user) suitable for `LLMClient.score()`. The system message instructs the LLM to produce a structured fit assessment. The user message formats the job posting (title, company, location, salary as "150k-200k" range, description truncated to 3000 chars, requirements) and candidate profile (name, label, summary, skills, up to 3 work entries with highlights). Helper `_format_salary()` handles all salary field combinations; `_format_profile()` extracts JSON Resume basics/skills/work.

### JobScorer (`src/jobinator/scoring/scorer.py`)

`JobScorer.score_job(job, profile_data)` implements the full per-job lifecycle:
1. `budget_tracker.assert_within_limits(job_id=job.id)` — hard stop BEFORE LLM call
2. `build_scoring_prompt()` — format messages
3. `llm_client.score()` — structured LLM call
4. `_compute_priority()` — local weighted computation (fit 0.6 + recency 0.2 + urgency 0.2), overrides LLM-provided priority_score
5. Build `JobScore` with `json.dumps()` for strengths/gaps arrays
6. `budget_tracker.record()` — persist `SpendRecord` immediately
7. `budget_tracker.log_decision()` — audit trail entry

`_recency_score()` returns 1.0 for today's jobs, decays linearly to 0.0 over 30 days, 0.5 for unknown. `_urgency_score()` decays over 14 days from `first_seen_at`.

### Scoring Pipeline (`src/jobinator/pipelines/score.py`)

`run_scoring(session, budget_tracker, scorer, config)` mirrors the `run_discovery()` pattern:
- Validates profile first (fail fast before any DB queries)
- Calls `get_unscored_jobs(session, batch_size)` — subquery excludes already-scored and stale jobs
- Per-job: score, persist `JobScore` + `StatusEvent(status="scored")`, commit
- `BudgetExceeded` → set `budget_stopped=True`, log decision, break
- Other exceptions → append to `errors`, rollback, continue

### CLI `score` Command (`src/jobinator/cli.py`)

Added `score` command with `--limit` (default 10) and `--dry-run` options:
- API key check first (fail fast before DB work)
- Profile validation before scoring loop
- `--dry-run` shows unscored jobs table (ID, Title, Company, Source) without calling LLM
- Budget exceeded: prints spend amount in red, exits 1
- Success: prints scored/skipped/errors summary

## Test Results

- `tests/test_scoring_pipeline.py`: 35 tests — all pass
- `tests/test_score_cli.py`: 14 tests — all pass (+ 27 from Plan 01 = 76 Phase 3 total)
- Full suite: 185 tests, 0 failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CLI test patch targets corrected for lazy imports**
- **Found during:** Task 2 GREEN phase (test run)
- **Issue:** Tests written to `patch("jobinator.cli.get_settings", ...)` failed with `AttributeError: module 'jobinator.cli' does not have the attribute 'get_settings'` — because lazy imports inside the function body don't create module-level attributes
- **Fix:** Rewrote CLI tests to use module-level monkey-patching (saving/restoring original functions on source modules `jobinator.configs.settings`, `jobinator.db`, etc.) rather than `unittest.mock.patch()` targeting `jobinator.cli`
- **Files modified:** `tests/test_score_cli.py`
- **Commit:** 8835ab5

## Known Stubs

None. All fields are wired to real implementations. The `score` command creates real `JobScore` and `StatusEvent` records. The priority score formula is fully implemented. No placeholder data flows to output.

## Self-Check: PASSED
