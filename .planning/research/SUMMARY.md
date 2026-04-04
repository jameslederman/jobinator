# Project Research Summary

**Project:** Jobinator — Local-first job search automation pipeline
**Domain:** CLI-based AI agent pipeline for job discovery, scoring, and application materials generation
**Researched:** 2026-04-04
**Confidence:** MEDIUM (no live web access during research; training data cutoff August 2025)

## Executive Summary

Jobinator is a local-first, single-user CLI tool that automates the job search pipeline: discovering postings from multiple sources, scoring fit using LLMs, and generating tailored application materials (resume, cover letter, interview prep brief). The expert approach treats this as a **pipeline system with an embedded agent loop**, not a monolithic LLM agent. The overwhelming majority of work — normalization, deduplication, heuristic filtering, file I/O — is deterministic Python with no LLM involvement. The LLM layer sits on top of a solid data pipeline and is invoked only where semantic judgment is required. This separation keeps the system testable, debuggable, and cost-controlled.

The recommended stack centers on Pydantic v2 as the canonical type system threading through the entire pipeline: SQLModel for database schema and ORM, Instructor for structured LLM output, and pydantic-settings for typed configuration. LiteLLM provides a unified multi-provider interface enabling the critical architecture decision of routing cheap models (Haiku, GPT-4o-mini) for high-volume scoring and strong models (Claude Sonnet, GPT-4o) only for low-volume materials generation. This tiering delivers an estimated 10-20x cost reduction versus using frontier models throughout. Typer + Rich handles the CLI layer with minimal ceremony.

The dominant risks in this domain are well-documented: scraper fragility at the data ingestion layer, LLM cost overruns if budget enforcement is not baked in from day one, and hallucination in generated materials if grounding constraints are not enforced in prompts. Competitive analysis of existing tools (AIHawk, Jobscan, LazyApply, Teal) reveals a consistent failure pattern — over-automation erodes application quality. Jobinator's core differentiator is quality-over-volume: a human-in-the-loop default, transparent scoring with reasoning, and per-role tailored materials grounded strictly in the user's actual profile.

## Key Findings

### Recommended Stack

The stack is cohesive around Pydantic v2 integration as the core design principle. SQLModel eliminates the impedance mismatch between ORM and validation that plagues SQLAlchemy-only setups. Instructor eliminates the need to manually parse and retry malformed LLM JSON. pydantic-settings eliminates raw `os.environ` access. This means the same typed model can describe a database row, a validated LLM response, and a config value — no translation layers. LiteLLM + tiktoken handle multi-provider routing and pre-call token cost estimation. Alembic handles schema migrations from day one, preventing the schema debt that breaks single-user tools when requirements evolve. WeasyPrint provides pure-Python HTML-to-PDF without binary system dependencies.

**Core technologies:**
- **Typer + Rich:** CLI framework — Click under the hood, type-annotation-driven, integrates with Rich for readable terminal output
- **SQLModel + Alembic + SQLite:** ORM + migrations + storage — single model class is both DB schema and Pydantic validator; Alembic handles evolution
- **LiteLLM + Instructor + tiktoken:** Multi-provider LLM — unified API, built-in cost tracking, structured output enforcement, pre-call token counting
- **httpx + BeautifulSoup4 + tenacity:** HTTP ingestion — async-capable client, HTML parsing, exponential backoff retry
- **Jinja2 + WeasyPrint:** Materials rendering — template engine for resume/cover letter, pure-Python PDF from HTML
- **pydantic-settings + python-dotenv + PyYAML:** Configuration — typed config loading from .env + YAML, no raw `os.environ` access
- **uv + ruff + mypy + pre-commit:** Dev tooling — fast package management, linting, type checking enforced on commit

### Expected Features

**Must have (table stakes):**
- Multi-source job discovery (Wellfound, Greenhouse, Lever, HN Hiring) — single source creates blind spots
- Structured normalization to a consistent schema — raw scraped data is unusable without this
- Multi-signal deduplication — cross-source posting of the same role is near-universal
- Persistent job state machine (`seen → scored → applied → rejected`) — required for all downstream logic
- Hard filter evaluation (remote/location, salary floor, title keywords) — cheap first-pass before any LLM cost
- LLM fit scoring with per-job reasoning (strengths, gaps, comp estimate) — core value over manual search
- Resume tailoring per role — generic resume is table stakes failure mode
- Cover letter generation per role — highest-friction artifact in applications
- Apply tracking with status pipeline — the "CRM layer" every user needs
- Token spend tracking and daily budget enforcement — must not be deferred

**Should have (competitive differentiators):**
- Interview prep brief per role — no commercial tool generates this; high value, low incremental complexity
- Priority scoring (fit × recency × preference) — makes actionable queue rather than a raw list
- Decision logging with full reasoning — audit trail for debugging and improving scoring
- Human-in-the-loop review mode — show materials, require approval before any application action
- Source health monitoring — detect when an adapter silently breaks

**Defer (v2+):**
- Feedback loop / outcome tracking by score tier (requires weeks of outcome data)
- Form-filling assist (high complexity, lower priority than quality materials)
- Company research enrichment via external APIs
- ATS score simulation (Jobscan-style keyword matching)
- Salary intelligence engine
- Browser automation of any kind
- LinkedIn integration (legal and technical non-starter)

### Architecture Approach

Jobinator is structured as a layered pipeline with 10 discrete components: CLI → Orchestrator/Agent Loop → four pipeline stages (Source Adapters, Normalization, Score, Generation) → LLM Provider Abstraction + Budget Tracker → State Layer (SQLite) → Output Layer (filesystem). Components communicate through typed interfaces; business logic never lives in the agent loop itself. The two-stage scoring design (heuristic filter at no cost, then cheap-model LLM scoring only on passing jobs, then strong-model generation only for above-threshold jobs) is the critical architectural decision for keeping costs bounded at scale. Structured output via Instructor is enforced at every LLM call boundary — no free-form text parsing anywhere.

**Major components:**
1. **CLI Layer (Typer)** — command parsing and human-in-the-loop confirmation gates; no business logic
2. **Orchestrator / Agent Loop** — sequences pipeline stages, manages LLM conversation context, enforces budget gate before every LLM call
3. **Source Adapters (per-source)** — fetch and return `RawJob` objects; independently testable, implement shared `SourceAdapter` Protocol
4. **Normalization Pipeline** — deterministic `RawJob → NormalizedJob` transformation; no LLM; handles salary parsing, location extraction, company slug generation
5. **Score Pipeline** — two-stage: (1) heuristic filter (no cost), (2) LLM scoring with cheap model; produces `JobScore` with structured reasoning
6. **Generation Pipeline** — strong-model LLM generates resume (JSON Resume format), cover letter, and prep brief in a shared context window; writes to Output Layer
7. **LLM Provider Abstraction** — routes `cheap` vs `strong` tier calls to appropriate models; normalizes usage/cost across providers
8. **Budget Tracker** — pre-call gate (`assert_within_limits`) + post-call spend recording to SQLite; enforces daily and per-job caps
9. **State Layer (SQLite + SQLModel)** — seven tables covering jobs, scores, materials, applications, spend, decisions, outcomes; Alembic migrations
10. **Output Layer (filesystem)** — writes materials to `~/jobinator-output/<company>/<role>/<timestamp>/` with versioning

### Critical Pitfalls

1. **Scraper fragility as load-bearing dependency** — build source adapters behind a shared Protocol interface so any adapter can be replaced without touching the pipeline; emit source health alerts when a source returns 0 results 3 runs in a row; prefer Greenhouse/Lever JSON APIs over HTML scraping; treat Wellfound as fragile by design
2. **LLM cost overruns** — implement Budget Tracker with hard per-job ($0.50) and daily ($5.00) caps before any LLM calls are wired; use cheap models for high-volume scoring; circuit-break agent loop retries at 2-3 attempts maximum; truncate job descriptions to a token budget before LLM calls
3. **Hallucination in generated materials** — enforce strict grounding in generation prompt ("only use information from the provided profile"); run a post-generation fact-check LLM pass flagging claims not traceable to profile JSON; never auto-submit without human review
4. **Duplicate applications from poor deduplication** — match on `(company_name_normalized, title_normalized)` compound key, not URL alone; secondary signal on description content hash; canonical job record with source URL provenance
5. **Stale job data leading to wasted generation cost** — track `first_seen_at` / `last_seen_at`; TTL-mark jobs not re-sighted within 3 days; do a cheap URL liveness check before triggering expensive materials generation

## Implications for Roadmap

Based on the combined research, the architecture's own dependency graph defines the build order unambiguously. The State Layer must exist before anything that writes state. The LLM abstraction must exist before any scoring or generation. The CLI wraps everything last. This yields five natural phases.

### Phase 1: Foundation
**Rationale:** Everything else depends on this. State Layer, core Pydantic schemas, normalization logic, Alembic migrations, budget tracker infrastructure, and output directory conventions must all exist before any external calls or LLM integration. These are pure Python with no external dependencies — fast to build, fast to test.
**Delivers:** SQLite database with all 7 tables, Pydantic/SQLModel models for all domain entities, Alembic migration setup, normalization pipeline (deterministic, unit-testable), Score Pipeline Stage 1 (heuristic filter, no LLM), Output Layer filesystem writer, Budget Tracker (DB persistence + limit enforcement, no LLM calls yet)
**Addresses:** Persistent job state, hard filter evaluation, schema migration debt avoidance (Pitfall 9)
**Avoids:** Agent loop runaway (Pitfall 10) — build circuit breaker structure here; output directory sprawl (Pitfall 14)

### Phase 2: Data Ingestion
**Rationale:** Source adapters are the supply side of the pipeline. With the State Layer and Normalization Pipeline in place, adapters have somewhere to write. Build in ascending complexity order: HN Hiring (Algolia API, no auth, most stable) → Greenhouse → Lever → Wellfound (highest fragility risk).
**Delivers:** Working `discover` command that pulls real jobs from 2+ sources, deduplicates cross-source, and stores normalized records in SQLite. Source health monitoring. Rate limiting and retry logic via tenacity.
**Uses:** httpx, BeautifulSoup4, tenacity, python-dateutil
**Avoids:** Scraper fragility (Pitfall 1) — source health checks built in; rate limiting / IP bans (Pitfall 2) — conservative defaults; deduplication failures (Pitfall 6); stale job TTL (Pitfall 5)
**Research flag:** Wellfound adapter may require phase-specific research — unofficial API status can change

### Phase 3: LLM Integration and Scoring
**Rationale:** With a working ingestion pipeline producing normalized jobs, LLM scoring becomes meaningful. Budget Tracker infrastructure from Phase 1 is activated here. Cheap-model scoring runs on all jobs passing the heuristic filter.
**Delivers:** Working `score` command — heuristic pre-filter + LLM semantic scoring with reasoning output (strengths, gaps, comp estimate, priority). LLM Provider Abstraction with model tier routing. Spend logged to SQLite after every call.
**Uses:** LiteLLM, Instructor, tiktoken, pydantic-settings, anthropic SDK, openai SDK
**Implements:** Score Pipeline Stage 2, LLM Provider Abstraction, Budget Tracker activation
**Avoids:** Cost overruns (Pitfall 4) — hard caps enforced; ATS keyword gaming (Pitfall 8) — semantic LLM scoring not keyword overlap; score calibration drift (Pitfall 13) — few-shot examples in prompt

### Phase 4: Materials Generation and Agent Loop
**Rationale:** Generation is the highest-value, highest-cost pipeline stage. It depends on scoring (needs `JobScore` as input), the LLM abstraction (strong model tier), and the output layer. The Agent Loop / Orchestrator is built here as the coordinator, after all pipeline components it sequences exist.
**Delivers:** Working `apply <job_id>` command — generates tailored resume (JSON Resume + PDF via WeasyPrint), cover letter, and interview prep brief in a shared LLM context window. Human-in-the-loop review step before any output is finalized. Decision log written to DB.
**Uses:** Jinja2, WeasyPrint, Instructor (strong model tier), Generation Pipeline
**Avoids:** Hallucination (Pitfall 3) — grounding prompt + post-generation fact-check pass; over-automation (Pitfall 7) — human-in-the-loop is the default mode, not `--auto`; profile schema drift (Pitfall 12)

### Phase 5: CLI Polish and Run Mode
**Rationale:** The CLI layer is built last because it wraps the Orchestrator, which wraps everything else. The `run --auto` full pipeline mode and `review` interactive mode require all upstream components to be stable first.
**Delivers:** Complete CLI surface (`discover`, `score`, `apply`, `run --auto`, `review`, `status`). Rich-formatted output tables for scored job queue. Interactive review mode for human-in-the-loop approval. `status` command showing pipeline state, spend summary, and recent outcomes.
**Uses:** Typer, Rich
**Implements:** CLI Layer (Component 1)

### Phase Ordering Rationale

- State Layer first is non-negotiable — every other component reads or writes state, and Alembic migrations must be in place before any schema divergence occurs
- Normalization Pipeline before Source Adapters mirrors the data flow: adapters produce `RawJob`, normalization consumes it — building normalization first means adapters have a tested interface to target
- Budget Tracker infrastructure in Phase 1 (even without LLM calls) prevents retrofitting cost enforcement after LLM calls are already wired — the two most expensive failure modes (cost overruns, runaway retries) are designed out before any LLM is added
- Scoring before Generation reflects the feature dependency chain: generation only runs on jobs above the score threshold
- CLI last reflects the principle that wiring up commands to non-existent components is wasted work

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Wellfound adapter):** Unofficial API status and scraping approach should be verified against current Wellfound site structure before implementation
- **Phase 3 (LLM pricing and model availability):** LiteLLM pricing tables, current Haiku/GPT-4o-mini model IDs, and actual per-token costs should be verified — pricing changes frequently and cost assumptions drive budget cap defaults
- **Phase 4 (WeasyPrint CSS compatibility):** Should validate that WeasyPrint produces acceptable resume PDF output before committing to it — CSS support has known gaps; a test render with a sample JSON Resume profile is recommended early in this phase

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** SQLModel + Alembic + SQLite setup is thoroughly documented; Pydantic v2 model patterns are well-established; no research needed
- **Phase 5 (CLI):** Typer + Rich patterns are stable and well-documented; no novel integration challenges

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core technologies (Typer, SQLModel, Pydantic, httpx) are HIGH confidence; LiteLLM and Instructor evolve rapidly and version pinning should be verified against current PyPI before locking; WeasyPrint PDF quality should be validated before committing |
| Features | MEDIUM | Must-have features and anti-features are HIGH confidence (consistent signal across competitive tools and user complaint patterns); differentiator priority ordering is MEDIUM (validated by gap analysis of existing tools but not by user research with actual target users) |
| Architecture | HIGH | All recommended patterns are well-established: pipeline separation, Protocol-based adapters, two-stage scoring, structured LLM output — none are experimental; dependency graph is deterministic |
| Pitfalls | HIGH | Critical pitfalls (scraper fragility, cost overruns, hallucination, deduplication, stale data) are extensively documented across open-source projects and community sources; all have clear, implementable mitigations |

**Overall confidence:** MEDIUM — architecture and pitfalls are HIGH confidence; stack version specifics and feature prioritization need validation against current library state and real user feedback

### Gaps to Address

- **LiteLLM cost accuracy:** LiteLLM ships pricing tables that may lag provider changes. During Phase 3 planning, verify `completion_cost()` accuracy against current Anthropic and OpenAI pricing pages before setting budget cap defaults.
- **Greenhouse and Lever API stability:** These are unofficial public APIs. During Phase 2 planning, verify endpoints are still live and response schemas match documented structure before building adapters.
- **Wellfound approach:** No public API exists. During Phase 2, research current Wellfound site structure to determine whether the unofficial API approach still works or if HTML scraping is required. May need to be deprioritized if access is blocked.
- **WeasyPrint PDF quality:** CSS support gaps could affect resume rendering. During Phase 4, render a test JSON Resume profile to PDF early and verify output meets quality bar before committing WeasyPrint as the PDF renderer.
- **Score calibration:** LLM scoring prompt quality is unknowable until tested against real job postings and a real user profile. Plan for a calibration iteration at the end of Phase 3 — score distribution review and prompt adjustment before advancing to Generation.

## Sources

### Primary (HIGH confidence)
- SQLModel documentation (sqlmodel.tiangolo.com) — ORM patterns, SQLite integration, Alembic migration setup
- Anthropic / OpenAI official documentation — structured output (tool-use-as-JSON), function calling patterns
- JSON Resume schema (jsonresume.org) — portable resume format spec
- HN Algolia API (hn.algolia.com/api) — long-stable, official HN search API for Who's Hiring thread discovery
- uv documentation (docs.astral.sh/uv) — packaging and venv management
- pydantic-settings documentation (docs.pydantic.dev) — typed config loading

### Secondary (MEDIUM confidence)
- LiteLLM documentation (docs.litellm.ai) — multi-provider routing, cost tracking via `completion_cost()`
- Instructor documentation (python.useinstructor.com) — structured LLM output, Pydantic model enforcement
- Greenhouse Jobs API (developers.greenhouse.io) — public job board API endpoint structure
- Lever Postings API (hire.lever.co/developer/postings) — public job board API endpoint structure
- WeasyPrint documentation (doc.courtbouillon.org/weasyprint) — HTML-to-PDF rendering
- Open-source job automation projects: JobSpy, AIHawk (feder-cr/Jobs_Applier_AI_Agent), py-jobberwocky — competitive feature analysis and pitfall documentation
- Reddit (r/jobsearchhacks, r/cscareerquestions) and HN threads — user complaint patterns for existing tools

### Tertiary (LOW confidence)
- Wellfound unofficial API / scraping approach — no documented public API; approach may break on layout or auth changes; verify before building
- LiteLLM pricing table accuracy — ships with library but may lag provider price changes; validate against current Anthropic/OpenAI invoices
- Model IDs for current Haiku and GPT-4o-mini — pricing and availability changes frequently; verify current model IDs before using in config

---
*Research completed: 2026-04-04*
*Ready for roadmap: yes*
