---
phase: 03-llm-scoring
plan: "01"
subsystem: scoring-infrastructure
tags: [llm, scoring, sqlmodel, pydantic, instructor, litellm, alembic]
dependency_graph:
  requires:
    - 01-foundation (SQLModel, BudgetTracker, Settings)
    - 02-data-ingestion (NormalizedJob table exists for FK)
  provides:
    - JobScore SQLModel table (SQLite-persisted)
    - JobScoreOutput Pydantic model (Instructor response_model)
    - ScoringConfig standalone BaseModel
    - LLMClient wrapper (Instructor + LiteLLM)
    - LLMResult dataclass
  affects:
    - 03-02 (scoring pipeline consumes LLMClient, JobScore, ScoringConfig)
tech_stack:
  added:
    - litellm>=1.40
    - instructor>=1.4
    - anthropic>=0.28
    - openai>=1.30
    - tiktoken>=0.7
  patterns:
    - Instructor create_with_completion() for structured output + raw response access
    - Cost extraction from raw._hidden_params["response_cost"] (not completion_cost())
    - ScoringConfig as standalone BaseModel (same pattern as DiscoveryConfig / FilterConfig)
key_files:
  created:
    - src/jobinator/models/score.py
    - src/jobinator/scoring/client.py
    - alembic/versions/c17823771712_add_job_score_table.py
    - tests/test_scoring.py
    - tests/test_llm_client.py
  modified:
    - src/jobinator/models/__init__.py
    - src/jobinator/configs/settings.py
    - tests/conftest.py
    - pyproject.toml
    - uv.lock
decisions:
  - "Cost extraction via _hidden_params['response_cost'] not litellm.completion_cost() — known instructor#1330 bug where completion_cost() returns 0.0 through Instructor wrapper"
  - "ScoringConfig as standalone BaseModel (not Settings subclass) — consistent with FilterConfig and DiscoveryConfig patterns for test-overridable config"
  - "JobScoreOutput as plain Pydantic BaseModel, not SQLModel table — Instructor response_model is separate from DB persistence model"
  - "Optional import added to settings.py typing imports — required for Pydantic v2 to resolve Optional[str] in ScoringConfig.profile_path at runtime"
metrics:
  duration: "3 minutes"
  completed_date: "2026-04-06"
  tasks_completed: 2
  files_created: 5
  files_modified: 5
---

# Phase 3 Plan 01: LLM Scoring Infrastructure Summary

Installed Phase 3 LLM dependencies and created JobScore SQLModel table, JobScoreOutput Pydantic response model, ScoringConfig, Alembic migration, and Instructor+LiteLLM client wrapper that returns structured output with cost extraction from `_hidden_params["response_cost"]`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | JobScore model, ScoringConfig, Alembic migration | 66a19b7 | score.py, settings.py, __init__.py, conftest.py, test_scoring.py, migration |
| 2 | LLM client wrapper with Instructor+LiteLLM | aa2fe04 | client.py, scoring/__init__.py, test_llm_client.py, pyproject.toml |

## What Was Built

### JobScore SQLModel Table (`src/jobinator/models/score.py`)

SQLModel table with unique FK to `normalizedjob.id`, storing `fit_score`, `priority_score`, `strengths_json`, `gaps_json`, `reasoning`, `model_used`, optional `compensation_estimate`, and `scored_at` timestamp. The `unique=True` constraint on `job_id` enforces one score per job.

### JobScoreOutput Pydantic Model (`src/jobinator/models/score.py`)

Plain Pydantic `BaseModel` (not SQLModel) used as the Instructor `response_model`. Fields: `fit_score` (ge=0.0, le=1.0), `strengths_match`, `gaps`, `compensation_estimate` (default "unknown"), `priority_score` (ge=0.0, le=1.0), `reasoning`. This is the shape the LLM must produce; it gets serialized into a `JobScore` row by the pipeline in Plan 02.

### ScoringConfig (`src/jobinator/configs/settings.py`)

Standalone `BaseModel` following the same pattern as `DiscoveryConfig` and `FilterConfig`. Fields: `cheap_model`, `strong_model`, `score_batch_size`, `min_fit_score_threshold`, `profile_path`, `priority_weights`. The `get_scoring_config()` function reads the `[scoring]` section of `config.toml`, falling back to defaults when absent.

### LLMClient (`src/jobinator/scoring/client.py`)

Class wrapping `instructor.from_litellm(litellm.completion)`. The `score(messages)` method calls `create_with_completion()` to get both the structured `JobScoreOutput` and the raw `ModelResponse`. Cost is extracted from `raw._hidden_params["response_cost"]` — NOT `litellm.completion_cost()`, which returns 0.0 through the Instructor wrapper (instructor#1330). Token counts come from `raw.usage.prompt_tokens` / `completion_tokens`. `max_retries=2` is passed for automatic retry on validation failure.

### Alembic Migration

`c17823771712_add_job_score_table` — creates `jobscore` table with `ix_jobscore_job_id` index. Migration applies cleanly via `uv run alembic upgrade head`.

## Test Results

- `tests/test_scoring.py`: 17 tests — all pass
- `tests/test_llm_client.py`: 10 tests — all pass (mocked `create_with_completion`)
- Total: 27 tests, 0 failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing `Optional` import in settings.py**
- **Found during:** Task 1 GREEN phase (test run)
- **Issue:** `ScoringConfig.profile_path: Optional[str]` caused `PydanticUserError: ScoringConfig is not fully defined` at runtime because `Optional` was not in the `typing` import list
- **Fix:** Added `Optional` to `from typing import Optional, Tuple, Type` import in `settings.py`
- **Files modified:** `src/jobinator/configs/settings.py`
- **Commit:** 66a19b7

## Known Stubs

None. All fields are wired to real implementations. The `JobScoreOutput` model is not yet wired to the scoring pipeline — that is the explicit goal of Plan 02, not a stub here.

## Self-Check: PASSED
