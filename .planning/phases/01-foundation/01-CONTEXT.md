# Phase 1: Foundation - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Data layer, normalization pipeline, heuristic filtering, budget tracker infrastructure, and output directory conventions. Pure Python — no LLM calls, no external API calls, no job discovery. This phase builds the skeleton that all downstream phases plug into.

</domain>

<decisions>
## Implementation Decisions

### Schema Design
- **D-01:** Salary modeled as four fields: `salary_min`, `salary_max` (posted, nullable), plus `estimated_salary_min`, `estimated_salary_max` (estimated, nullable). A `salary_source` enum (posted, estimated, unknown) indicates provenance. Estimation logic deferred to scoring phase — foundation just defines the fields.
- **D-02:** Location modeled as `location_type` enum (remote, hybrid, onsite, unknown) plus `location_raw` free text string for the original posting text.
- **D-03:** Job status is event-sourced. An append-only `status_events` table with timestamps. Current status derived from latest event. Status values: discovered, scored, applied, phone_screen, interview, rejected, offer.
- **D-04:** Company dedup uses two layers: deterministic slug (lowercase, strip Inc/LLC/Corp, collapse whitespace, replace special chars) for exact match, plus rapidfuzz second pass for near-misses above a configurable threshold.
- **D-05:** Dedup key is compound: `(company_slug, title_normalized)` plus description content hash as a secondary signal.

### Filter Configuration
- **D-06:** Filter rules defined in TOML config file (~/.config/jobinator/config.toml) with CLI flag overrides. CLI flags take precedence.
- **D-07:** Filters combine as AND between groups, OR within groups. e.g., `(salary >= 150k) AND (title matches "ML" OR "data science") AND (location = remote OR hybrid)`.
- **D-08:** Each filter has a configurable `on_missing` behavior: pass (default), fail, or estimate. Controls what happens when the job posting lacks the field being filtered.
- **D-09:** Both include and exclude lists supported: `title_include`, `title_exclude`, `company_exclude`. Exclude lists are checked first (reject beats match).

### Output Directory Structure
- **D-10:** Materials organized as `{output_dir}/{company_slug}/{role_slug}/{ISO-timestamp}/`. Default output_dir: `~/jobinator-output/`.
- **D-11:** Each application folder contains full bundle: resume.pdf, cover_letter.pdf, prep_brief.pdf, resume.md (source), cover_letter.md (source), prep_brief.md (source), job_description.md (snapshot), scoring.json (score output), metadata.json (job info, generation params, timestamps).
- **D-12:** A `latest/` symlink in each company/role directory points to the most recent timestamp folder.

### Project Scaffolding
- **D-13:** Package manager: uv. pyproject.toml based with lockfile.
- **D-14:** Config: TOML file (~/.config/jobinator/config.toml) for settings, .env for secrets (API keys). pydantic-settings loads both.
- **D-15:** CLI framework: Typer with Rich for formatted output.
- **D-16:** Source layout: `src/jobinator/` with subpackages: agents/, tools/, pipelines/, scoring/, memory/, configs/.
- **D-17:** SQLite + SQLModel for persistence, Alembic for schema migrations.

### Claude's Discretion
- Exact Pydantic model field names and types (as long as they follow the decisions above)
- Alembic migration setup approach
- Internal module boundaries within the src/jobinator/ package
- Test framework choice and structure
- Logging framework and configuration

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs — requirements fully captured in decisions above. Key project files:

### Project Context
- `.planning/PROJECT.md` — Project vision, core value, constraints
- `.planning/REQUIREMENTS.md` — v1 requirements with REQ-IDs for this phase: DISC-04, DISC-05, DISC-06, SCOR-01, INFR-04, INFR-06
- `.planning/research/STACK.md` — Technology stack recommendations (LiteLLM, Instructor, SQLModel, Typer, WeasyPrint, etc.)
- `.planning/research/ARCHITECTURE.md` — Component boundaries and data flow
- `.planning/research/PITFALLS.md` — Domain pitfalls (dedup failures, budget overruns, scraper fragility)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code.

### Established Patterns
- None — this phase establishes the patterns.

### Integration Points
- This phase creates the foundation that Phase 2 (Data Ingestion), Phase 3 (LLM Scoring), Phase 4 (Materials Generation), and Phase 5 (CLI) all build on.
- Key interfaces to define: NormalizedJob model, StatusEvent model, FilterConfig model, BudgetTracker protocol, OutputManager protocol.

</code_context>

<specifics>
## Specific Ideas

- User explicitly wants estimated salary as separate fields from posted salary — not a single field with a confidence flag
- Event-sourced status was chosen over simple enum to preserve full history for the feedback loop (Phase 5)
- Two-layer company dedup (deterministic + fuzzy) reflects that the same company appears with different names across sources
- Full bundle output (not just PDFs) chosen for complete audit trail per application

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-04*
