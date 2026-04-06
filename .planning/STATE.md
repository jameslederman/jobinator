---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Phase complete — ready for verification
stopped_at: Completed 04-materials-generation 04-03-PLAN.md (awaiting human verify Task 3)
last_updated: "2026-04-06T19:10:53.550Z"
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 11
  completed_plans: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-04)

**Core value:** Surface high-fit opportunities I'd miss manually and generate application materials good enough to submit with minimal editing.
**Current focus:** Phase 04 — materials-generation

## Current Position

Phase: 04 (materials-generation) — EXECUTING
Plan: 3 of 3

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01-foundation P01 | 7 | 2 tasks | 19 files |
| Phase 01-foundation P03 | 3 | 2 tasks | 6 files |
| Phase 01-foundation P02 | 4 | 2 tasks | 8 files |
| Phase 02-data-ingestion P01 | 8 | 2 tasks | 14 files |
| Phase 02-data-ingestion P02 | 4 | 2 tasks | 6 files |
| Phase 02-data-ingestion P03 | 9 | 2 tasks | 5 files |
| Phase 03-llm-scoring P01 | 3 | 2 tasks | 10 files |
| Phase 03-llm-scoring P02 | 6 | 2 tasks | 9 files |
| Phase 04-materials-generation P01 | 7 | 2 tasks | 7 files |
| Phase 04-materials-generation P02 | 6 | 2 tasks | 8 files |
| Phase 04-materials-generation P03 | 35 | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Custom agent loop over framework — no lock-in, full budget/interruption control
- Multi-provider LLM — cheap models for scoring volume, strong for generation quality
- Build Budget Tracker in Phase 1 before any LLM wired — prevents cost overrun retrofitting
- [Phase 01-foundation]: uv_build replaced by hatchling as build backend for better ecosystem compatibility
- [Phase 01-foundation]: pydantic-settings TOML loading requires settings_customise_sources() with TomlConfigSettingsSource — toml_file shorthand silently ignored
- [Phase 01-foundation]: Alembic autogenerate migration files need import sqlmodel added (uses sqlmodel.sql.sqltypes.AutoString) — baked into script.py.mako template
- [Phase 01-foundation]: Use datetime.utcnow() boundaries in daily_spend() to match naive utcnow() stored in SpendRecord.recorded_at, avoiding timezone mismatch on machines where local time differs from UTC
- [Phase 01-foundation]: BudgetConfig as standalone Pydantic BaseModel (not Settings subclass) for test-overridable config without requiring config files
- [Phase 01-foundation]: Removed 'co' from company suffix list to prevent false positives in slug generation
- [Phase 01-foundation]: FilterConfig uses plain Pydantic BaseModel (not SQLModel) since it is a config object, not a DB table
- [Phase 02-data-ingestion]: DiscoveryConfig as standalone BaseModel (not Settings subclass) — consistent with FilterConfig pattern from Phase 1 Pitfall 7
- [Phase 02-data-ingestion]: Lever posted_at always None — Lever public API does not expose posting date
- [Phase 02-data-ingestion]: tenacity @retry on inner _fetch helpers, not fetch() method — isolates per-board retry without aborting multi-company loops
- [Phase 02-data-ingestion]: HNHiringAdapter fragile=False — Algolia API is officially provided by HN and long-stable
- [Phase 02-data-ingestion]: WellfoundAdapter fragile=True — __NEXT_DATA__ extraction will break on Next.js structure changes
- [Phase 02-data-ingestion]: Wellfound pagination: stop when page returns < 10 nodes (no explicit total count in Apollo state)
- [Phase 02-data-ingestion]: get_existing_job_keys() called once per persist_jobs() batch to avoid N+1 DB queries
- [Phase 02-data-ingestion]: In-memory extension of existing_keys list within persist_jobs() deduplicates same-batch duplicates without extra DB round-trips
- [Phase 02-data-ingestion]: Consecutive-zero health counter only incremented on successful 0-result runs, not on adapter errors
- [Phase 02-data-ingestion]: ruff pre-commit hook updated from v0.5.0 to v0.15.9 to match local ruff and resolve import ordering conflicts
- [Phase 03-llm-scoring]: Cost extraction via _hidden_params['response_cost'] not litellm.completion_cost() — known instructor#1330 bug where completion_cost() returns 0.0 through Instructor wrapper
- [Phase 03-llm-scoring]: ScoringConfig as standalone BaseModel (not Settings subclass) — consistent with FilterConfig and DiscoveryConfig patterns for test-overridable config
- [Phase 03-llm-scoring]: JobScoreOutput as plain Pydantic BaseModel not SQLModel table — Instructor response_model is separate from DB persistence model
- [Phase 03-llm-scoring]: Local priority score computation overrides LLM priority_score — LLM lacks recency/urgency context; local _compute_priority() uses configurable weights with 30-day recency decay and 14-day urgency decay
- [Phase 03-llm-scoring]: CLI tests use module-level monkey-patching instead of unittest.mock.patch() — lazy imports inside score() function body prevent patching at jobinator.cli module level
- [Phase 04-materials-generation]: MaterialsConfig as standalone BaseModel (not Settings subclass) — consistent with ScoringConfig/DiscoveryConfig pattern for test-overridable config without requiring config files
- [Phase 04-materials-generation]: Generation response models (ResumeContent, CoverLetterContent, PrepBriefContent) as plain Pydantic BaseModel not SQLModel — same pattern as JobScoreOutput, Instructor response_model separate from DB persistence model
- [Phase 04-materials-generation]: WeasyPrint macOS fix: sitecustomize.py in venv sets DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib at Python startup — requires brew install pango on fresh macOS setups
- [Phase 04-materials-generation]: MagicMock(spec=BudgetTracker) required for assert_within_limits — MagicMock treats assert_* attributes as pytest assertions without spec
- [Phase 04-materials-generation]: Prompt grounding rules embedded in system message with full profile JSON (not truncated) — satisfies MATL-02 verifiability
- [Phase 04-materials-generation]: confirm_callback injectable (default=typer.confirm) enables HITL gate unit testing without terminal interaction
- [Phase 04-materials-generation]: OutputManager.create_application_dir called AFTER user confirmation — no stale directories on cancel
- [Phase 04-materials-generation]: Each generator call individually budget-gated so BudgetExceeded stops mid-generation without partial files

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: Wellfound adapter has no public API — approach must be verified against current site structure before building
- Phase 3: LiteLLM pricing tables may lag actual provider pricing — verify before setting budget cap defaults
- Phase 4: WeasyPrint CSS compatibility gaps — render test PDF early before committing to it as PDF renderer

## Session Continuity

Last session: 2026-04-06T19:10:53.548Z
Stopped at: Completed 04-materials-generation 04-03-PLAN.md (awaiting human verify Task 3)
Resume file: None
