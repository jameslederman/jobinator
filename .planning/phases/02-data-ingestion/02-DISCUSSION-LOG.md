# Phase 2: Data Ingestion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-05
**Phase:** 02-data-ingestion
**Areas discussed:** Target company config, Wellfound strategy, Discovery orchestration

---

## Target Company Config

### Company list management

| Option | Description | Selected |
|--------|-------------|----------|
| TOML config list | A [discovery.companies] section in config.toml with board slugs per source. Fits existing config pattern. | ✓ |
| Separate YAML file | A dedicated companies.yaml in config dir. Easier to edit independently. | |
| CLI add/remove commands | Commands like `jobinator company add`. Stored in SQLite. | |

**User's choice:** TOML config list
**Notes:** Consistent with existing Phase 1 pattern of TOML-based configuration.

### Source specification

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit source per company | e.g., `greenhouse = ["anthropic"]`, `lever = ["figma"]`. No wasted API calls. | ✓ |
| Auto-detect source | Try Greenhouse first, fall back to Lever. Simpler config. | |
| You decide | Claude picks. | |

**User's choice:** Explicit source per company
**Notes:** User knows which ATS each target company uses; no need for auto-detection.

### Fetch scope

| Option | Description | Selected |
|--------|-------------|----------|
| Fetch all, filter locally | Pull every open role, let heuristic filter handle relevance. | ✓ |
| Keyword filter at source | Pass title keywords to APIs that support it. | |
| You decide | Claude picks. | |

**User's choice:** Fetch all, filter locally
**Notes:** Consistent filtering across all sources via existing heuristic filter.

### Seed list

| Option | Description | Selected |
|--------|-------------|----------|
| Empty, user adds manually | Default config has empty company lists. | ✓ |
| Starter list of DS/ML companies | Ship curated ~20 companies. | |
| You decide | Claude picks. | |

**User's choice:** Empty, user adds manually
**Notes:** Developer tool — user populates their own targets.

---

## Wellfound Strategy

### Fragility appetite

| Option | Description | Selected |
|--------|-------------|----------|
| Build scraper, accept fragility | Build with httpx + BS4, mark as fragile. Include health checks. | ✓ |
| Stub adapter, defer scraping | Create interface, return empty results. Implement later. | |
| Skip entirely for v1 | Remove DISC-01 from Phase 2. Focus on stable APIs. | |

**User's choice:** Build scraper, accept fragility
**Notes:** Wellfound is key source for startup roles (DISC-01). Health checks make breakage obvious.

### Discovery mode

| Option | Description | Selected |
|--------|-------------|----------|
| Search by role keywords | Search Wellfound for terms like "data scientist". Broader but noisier. | |
| Browse specific company pages | Same slug-based targeting as Greenhouse/Lever. Narrower but reliable. | |
| Both approaches | Keyword search + company pages combined. | ✓ |
| You decide | Claude picks. | |

**User's choice:** Both approaches
**Notes:** Comprehensive coverage — keyword search for breadth, company pages for targeted companies.

---

## Discovery Orchestration

### Source selection

| Option | Description | Selected |
|--------|-------------|----------|
| All sources by default | `discover` runs all. `--source X` for one. | ✓ |
| Interactive source picker | Prompt which sources each time. | |
| You decide | Claude picks. | |

**User's choice:** All sources by default
**Notes:** Simplest default, explicit when needed via `--source` flag.

### Staleness TTL

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable TTL in config.toml | e.g., `stale_after_days = 14`. User can tune. | ✓ |
| Fixed 30-day TTL | Simple, no config. | |
| You decide | Claude picks. | |

**User's choice:** Configurable TTL in config.toml
**Notes:** Default 14 days, tunable.

### Failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Log warning, continue other sources | One failure doesn't block others. Tenacity retries. Summary at end. | ✓ |
| Fail fast on any error | Stop entire discover run on any source error. | |
| You decide | Claude picks. | |

**User's choice:** Log warning, continue other sources
**Notes:** Resilient — surface failures in CLI summary without blocking.

### Concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential for now | Sync httpx. Simple, debuggable. Async migration later if needed. | ✓ |
| Async concurrent from start | httpx async + asyncio.gather. Faster but complex. | |
| You decide | Claude picks. | |

**User's choice:** Sequential for now
**Notes:** Reliability over speed during active job search.

---

## Claude's Discretion

- Adapter base class/protocol design and module structure
- HN Who's Hiring thread selection strategy
- Exact TOML config key names and structure
- Health alert implementation for consecutive zero-result runs
- Rate limiting approach per source

## Deferred Ideas

None — discussion stayed within phase scope
