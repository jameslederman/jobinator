# Roadmap: Jobinator

## Overview

Jobinator is built bottom-up along its own dependency graph. The state layer and core schemas come first because every other component reads or writes to them. Source adapters come second, giving the pipeline real job data to work with. LLM scoring activates third, sitting on top of the now-validated ingestion and budget infrastructure. Materials generation comes fourth — it requires scored jobs, the strong model tier, and the output layer. The CLI surface and application tracking round out the final phase, wrapping the full pipeline in usable commands. Five phases, each delivering a complete, verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Database schema, normalization pipeline, heuristic filtering, budget tracker infrastructure, and output directory conventions (completed 2026-04-05)
- [ ] **Phase 2: Data Ingestion** - Source adapters for Wellfound, Greenhouse/Lever, and HN Hiring with deduplication and freshness tracking
- [x] **Phase 3: LLM Scoring** - Multi-provider LLM abstraction, semantic fit scoring with reasoning, and live budget enforcement (completed 2026-04-06)
- [ ] **Phase 4: Materials Generation** - Tailored resume, cover letter, and interview prep brief generation with human-in-the-loop review
- [ ] **Phase 5: Application Pipeline and CLI** - Application status tracking, decision logging, feedback loop, and complete CLI surface

## Phase Details

### Phase 1: Foundation
**Goal**: The data layer and pipeline skeleton exist — every downstream component has typed interfaces to target, normalized schemas to write into, and budget rails to run under
**Depends on**: Nothing (first phase)
**Requirements**: DISC-04, DISC-05, DISC-06, SCOR-01, INFR-04, INFR-06
**Success Criteria** (what must be TRUE):
  1. A SQLite database initializes on first run with all required tables and Alembic migrations applied cleanly
  2. A raw job dict can be passed through the normalization pipeline and emerge as a fully typed NormalizedJob with salary, location, and company slug parsed deterministically
  3. A job failing hard filter criteria (salary floor, location type, title keywords) is rejected by the heuristic filter with a logged reason — no LLM called
  4. The output directory is created at the configured path and a placeholder materials folder is written with correct company/role/timestamp structure
  5. Attempting an LLM call against a mock budget at its daily limit raises a hard stop before any external call is made
**Plans:** 3/3 plans complete

Plans:
- [x] 01-01-PLAN.md — Project scaffold, SQLModel tables, DB engine, Alembic, settings
- [x] 01-02-PLAN.md — Normalization pipeline, deduplication, heuristic filter
- [x] 01-03-PLAN.md — Budget tracker infrastructure, output directory manager

### Phase 2: Data Ingestion
**Goal**: The discover command pulls real jobs from all three sources, deduplicates them cross-source, and persists normalized records to SQLite
**Depends on**: Phase 1
**Requirements**: DISC-01, DISC-02, DISC-03
**Success Criteria** (what must be TRUE):
  1. Running `discover` returns real job records from at least two live sources (HN Hiring, Greenhouse/Lever) stored in SQLite
  2. The same job posted on two different sources appears once in the database, not twice
  3. A job not re-sighted within the configured TTL window is marked stale and deprioritized in queries
  4. A source returning zero results across three consecutive runs triggers a health alert visible in terminal output
**Plans:** 2/3 plans executed

Plans:
- [x] 02-01-PLAN.md — Dependencies, schema migration, DiscoveryConfig, adapter Protocol, Greenhouse + Lever adapters
- [x] 02-02-PLAN.md — HN Who's Hiring adapter, Wellfound adapter
- [x] 02-03-PLAN.md — Discovery orchestrator, stale marking, health tracking, CLI discover command

### Phase 3: LLM Scoring
**Goal**: Discovered jobs are scored for fit using cheap LLM models with full structured reasoning, and every call is gated and logged against configurable budget limits
**Depends on**: Phase 2
**Requirements**: SCOR-02, SCOR-03, SCOR-04, SCOR-05, INFR-01, INFR-02, INFR-03
**Success Criteria** (what must be TRUE):
  1. Running `score` on a discovered job produces a 0-1 fit score with strengths match, gaps analysis, compensation estimate, and priority score
  2. Each scored job includes a human-readable reasoning paragraph explaining why the job scored as it did
  3. LLM calls for scoring route to the cheap model tier (Haiku or GPT-4o-mini), not the strong tier
  4. Every LLM call records token count and dollar cost to SQLite, and a daily spend total is queryable
  5. When the configured daily budget is hit, the `score` command stops and reports spend before making any further LLM calls
**Plans:** 2/2 plans complete

Plans:
- [x] 03-01-PLAN.md — JobScore model, ScoringConfig, LLM client wrapper (Instructor + LiteLLM), Alembic migration
- [x] 03-02-PLAN.md — Scoring prompt builder, scorer, pipeline orchestrator, CLI score command with budget gating

### Phase 4: Materials Generation
**Goal**: For any above-threshold job, the system generates a tailored resume, cover letter, and interview prep brief grounded strictly in the user's profile — and requires human confirmation before writing outputs
**Depends on**: Phase 3
**Requirements**: MATL-01, MATL-02, MATL-03, MATL-04, MATL-05, MATL-06
**Success Criteria** (what must be TRUE):
  1. Running `apply <job_id>` generates a resume, cover letter, and prep brief tailored to the specific role, all saved to the configured output directory under `<company>/<role>/<timestamp>/`
  2. The generated resume contains no claims (metrics, dates, skills) that are not traceable to the user's JSON Resume profile
  3. All three materials are rendered to PDF and the files are present on disk after generation
  4. The user is shown a preview of generated materials and must explicitly confirm before any file is written — the system does not write outputs silently
  5. Re-running `apply` for the same job creates a new versioned folder rather than overwriting the previous run
**Plans:** 1/3 plans executed

Plans:
- [x] 04-01-PLAN.md — GeneratedMaterial model, response models, MaterialsConfig, Alembic migration, dependencies
- [ ] 04-02-PLAN.md — Prompt builders, MaterialsGenerator, Jinja2 templates, WeasyPrint renderer
- [ ] 04-03-PLAN.md — Apply pipeline orchestrator, CLI apply command, end-to-end verification

### Phase 5: Application Pipeline and CLI
**Goal**: The full pipeline is wired into a complete, usable CLI — application status is tracked end-to-end, every decision is logged with reasoning, and outcome data is captured for future feedback
**Depends on**: Phase 4
**Requirements**: APPL-01, APPL-02, APPL-03, APPL-04, APPL-05, INFR-05
**Success Criteria** (what must be TRUE):
  1. Every CLI command (`discover`, `score`, `apply`, `run --auto`, `review`, `status`) runs without error and produces readable Rich-formatted output
  2. A job's status transitions correctly through the pipeline stages (discovered → scored → applied → phone_screen / rejected / offer) and the current state is visible via `status`
  3. Attempting to apply to a job already in `applied` state is blocked with a clear message — no duplicate application is created
  4. The `review` command displays scored jobs and their materials in an interactive queue requiring explicit approval before any apply action proceeds
  5. Running `status` shows response rate, interview rate, and offer rate broken down by source and role type, reflecting all recorded outcomes
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete   | 2026-04-05 |
| 2. Data Ingestion | 2/3 | In Progress|  |
| 3. LLM Scoring | 2/2 | Complete   | 2026-04-06 |
| 4. Materials Generation | 1/3 | In Progress|  |
| 5. Application Pipeline and CLI | 0/TBD | Not started | - |
