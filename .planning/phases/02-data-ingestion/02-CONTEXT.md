# Phase 2: Data Ingestion - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Source adapters for Wellfound, Greenhouse/Lever, and HN Who's Hiring that fetch real job postings, pass them through the existing normalization/dedup pipeline (Phase 1), and persist normalized records to SQLite. Includes cross-source deduplication, freshness/staleness tracking, and source health monitoring.

</domain>

<decisions>
## Implementation Decisions

### Target Company Configuration
- **D-01:** Target companies managed in `[discovery]` section of config.toml (existing TOML config pattern from Phase 1). No separate config file.
- **D-02:** Each company entry specifies its source explicitly: `greenhouse = ["anthropic", "stripe"]`, `lever = ["figma", "notion"]`. No auto-detection — avoids wasted API calls.
- **D-03:** Adapters fetch ALL open roles from each target company. Local heuristic filter (Phase 1) handles relevance filtering. No server-side keyword filtering.
- **D-04:** Default config ships with empty company lists. User populates with their own targets.

### Wellfound Strategy
- **D-05:** Build Wellfound scraper using httpx + BS4, accept fragility. Mark adapter as fragile in code. Include health checks so breakage is immediately obvious.
- **D-06:** Wellfound uses two discovery modes: keyword search (terms like "data scientist", "ML engineer") AND company page scraping (same slug-based targeting as Greenhouse/Lever). Both approaches combined for comprehensive coverage.

### Discovery Orchestration
- **D-07:** `discover` command runs all configured sources by default. `--source greenhouse` flag available to run a single source. Simplest default, explicit when needed.
- **D-08:** Staleness TTL is configurable in config.toml (e.g., `stale_after_days = 14`). Jobs not re-sighted within TTL get a stale flag. Default 14 days.
- **D-09:** Source failures log a warning and continue to other sources — one source failing does not block the run. Use tenacity for retries (3 attempts with exponential backoff). Surface failure in CLI output summary.
- **D-10:** Discovery runs sources sequentially (sync httpx). No async complexity for v1. httpx supports async migration later if speed becomes a bottleneck.

### Claude's Discretion
- Adapter base class/protocol design and module structure
- HN Who's Hiring thread selection strategy (latest vs configurable months, Algolia API query approach)
- Exact TOML config key names and structure within `[discovery]`
- Health alert implementation for consecutive zero-result runs (success criteria #4)
- Rate limiting / request throttling approach per source

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Project vision, core value, constraints
- `.planning/REQUIREMENTS.md` — v1 requirements; this phase covers DISC-01, DISC-02, DISC-03
- `.planning/ROADMAP.md` — Phase 2 success criteria and dependencies

### Prior Phase Context
- `.planning/phases/01-foundation/01-CONTEXT.md` — Phase 1 decisions (schema design D-01 through D-05, filter config D-06 through D-09, output structure D-10 through D-12, scaffolding D-13 through D-17)

### Research (from Phase 1)
- `.planning/research/STACK.md` — Technology stack: httpx, BS4, lxml, tenacity, python-dateutil
- `.planning/research/ARCHITECTURE.md` — Component boundaries and data flow
- `.planning/research/PITFALLS.md` — Domain pitfalls including scraper fragility, dedup failures

### Source API Documentation
- Greenhouse Jobs API: `https://developers.greenhouse.io/job-board.html` — Public JSON API, no auth required
- Lever Postings API: `https://hire.lever.co/developer/postings` — Public JSON API, no auth required
- HN Algolia API: `https://hn.algolia.com/api` — Search API for finding Who's Hiring threads
- Wellfound: No public API — scraping required, site structure must be verified before building

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pipelines/normalize.py`: Full normalization pipeline with flexible `_KEY_ALIASES` mapping, `normalize_job(raw: RawJobDict, source: str) -> NormalizedJob`. Adapters just need to produce `dict[str, Any]`.
- `pipelines/dedup.py`: Three-layer dedup (`is_duplicate()`, `get_existing_job_keys()`). Adapters don't need to handle dedup themselves.
- `pipelines/filter.py`: Heuristic filter with configurable rules from TOML. Adapters don't need to filter.
- `models/job.py`: `NormalizedJob` SQLModel with all fields, `StatusEvent` for event-sourced status tracking.
- `configs/settings.py`: `Settings` class with TOML + .env loading, `get_settings()` factory. New discovery config extends this.
- `db.py`: `get_engine()`, `get_session()`, `init_db()` — SQLite with WAL mode.

### Established Patterns
- `RawJobDict = dict[str, Any]` is the adapter output contract — each adapter returns a list of these
- Settings loaded via pydantic-settings from `~/.config/jobinator/config.toml`
- SQLModel for all persistence, Session-based DB access
- dateutil for flexible date parsing (already used in normalize.py)

### Integration Points
- Adapters produce `list[RawJobDict]` → `normalize_job()` → `is_duplicate()` check → `session.add()` → `StatusEvent(status="discovered")`
- New `[discovery]` section in config.toml for company lists and staleness TTL
- `tools/` package is empty — adapters could live here or in a new `adapters/` subpackage
- CLI (`cli.py`) will need a `discover` command wired to the orchestrator

</code_context>

<specifics>
## Specific Ideas

- Wellfound marked as fragile source in code — health monitoring is critical for this adapter
- Both keyword search and company page scraping for Wellfound provides broader coverage than either alone
- Explicit source-per-company config avoids the "try both APIs" anti-pattern that wastes calls
- Sequential sync execution is intentional — keeps debugging simple during active job search when reliability matters more than speed

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-data-ingestion*
*Context gathered: 2026-04-05*
