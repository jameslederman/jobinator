# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 1-Foundation
**Areas discussed:** Schema design, Filter configuration, Output directory structure, Project scaffolding

---

## Schema Design

### Salary handling when missing

| Option | Description | Selected |
|--------|-------------|----------|
| Null fields | salary_min/salary_max Optional[int], null when missing | |
| Estimated range | LLM/heuristic guesses a range from title/company/location | |
| Separate confidence | salary_min/max plus salary_source enum | |
| Other (user) | Separate estimated_salary_min/estimated_salary_max fields alongside posted fields | ✓ |

**User's choice:** Separate estimated fields — posted salary and estimated salary as distinct field pairs with a source indicator
**Notes:** User wants it clear which is posted vs estimated. Not a single field with confidence.

### Location modeling

| Option | Description | Selected |
|--------|-------------|----------|
| Enum + optional city | location_type: remote/hybrid/onsite/unknown + location_raw (free text) | ✓ |
| Structured geo | city, state, country as separate fields + location_type enum | |
| Tags-based | Set of location tags like {'remote', 'us', 'sf-bay'} | |

**User's choice:** Enum + optional city
**Notes:** Clean for filtering, doesn't require complex geo parsing.

### Job status flow

| Option | Description | Selected |
|--------|-------------|----------|
| Single status enum | Linear progression through pipeline states | |
| Status + substatus | Main status plus substatus for pipeline position | |
| Event log | Append-only status_events table with timestamps | ✓ |

**User's choice:** Event log
**Notes:** Full history preserved, status derived from latest event.

### Company slug generation

| Option | Description | Selected |
|--------|-------------|----------|
| Lowercase + strip | Deterministic slug generation | |
| Fuzzy normalization | rapidfuzz matching above threshold | |
| Both layers | Deterministic slug for exact match, fuzzy as second pass | ✓ |

**User's choice:** Both layers
**Notes:** Same company appears with different names across sources.

---

## Filter Configuration

### Filter rule location

| Option | Description | Selected |
|--------|-------------|----------|
| TOML config file | ~/.config/jobinator/filters.toml | |
| YAML config file | ~/.config/jobinator/filters.yaml | |
| CLI flags + config | Defaults in config file, overridable via CLI flags | ✓ |

**User's choice:** CLI flags + config (TOML defaults, CLI overrides)

### Filter combination logic

| Option | Description | Selected |
|--------|-------------|----------|
| All AND | Job must pass ALL filters | |
| AND with OR within groups | Groups ANDed, items within group ORed | ✓ |
| Full expression DSL | Custom filter expressions | |

**User's choice:** AND with OR within groups

### Missing field behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Pass through | Missing data = filter doesn't apply | |
| Fail closed | Missing data = filter fails | |
| Configurable per filter | Each filter has on_missing: pass/fail/estimate | ✓ |

**User's choice:** Configurable per filter

### Exclusion patterns

| Option | Description | Selected |
|--------|-------------|----------|
| Include + exclude lists | title_include, title_exclude, company_exclude | ✓ |
| Include only | Just positive filters | |

**User's choice:** Include + exclude lists

---

## Output Directory Structure

### Directory tree organization

| Option | Description | Selected |
|--------|-------------|----------|
| company/role/timestamp/ | Browsable, one folder per application attempt | ✓ |
| company/role/vN/ | Incrementing versions | |
| flat by date | Grouped by day | |

**User's choice:** company/role/timestamp/

### Application folder contents

| Option | Description | Selected |
|--------|-------------|----------|
| PDF + source + metadata | PDFs, source JSON, metadata JSON | |
| PDF only | Just final PDFs | |
| Full bundle | PDFs + markdown source + job snapshot + scoring + metadata | ✓ |

**User's choice:** Full bundle

### Latest symlink

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, latest/ symlink | Points to most recent timestamp folder | ✓ |
| No, browse by date | Keep it simple | |

**User's choice:** Yes, latest/ symlink

---

## Project Scaffolding

### Package manager

| Option | Description | Selected |
|--------|-------------|----------|
| uv | Fast, modern, pyproject.toml based | ✓ |
| Poetry | Mature, well-known | |
| pip + venv | Standard library | |

**User's choice:** uv

### Configuration approach

| Option | Description | Selected |
|--------|-------------|----------|
| TOML + env vars | Config file for settings, .env for secrets | ✓ |
| YAML + env vars | Same split but YAML | |
| Env vars only | Everything in environment | |

**User's choice:** TOML + env vars

### CLI framework

| Option | Description | Selected |
|--------|-------------|----------|
| Typer | Type-hint driven, less boilerplate | ✓ |
| Click | Industry standard, more explicit | |
| argparse | Standard library, no deps | |

**User's choice:** Typer

### Source directory layout

| Option | Description | Selected |
|--------|-------------|----------|
| src/jobinator/ | Standard installable package layout | ✓ |
| jobinator/ | Flat layout | |
| Monorepo-style | packages/core/, packages/cli/ | |

**User's choice:** src/jobinator/

---

## Claude's Discretion

- Exact Pydantic model field names and types
- Alembic migration setup approach
- Internal module boundaries
- Test framework choice
- Logging framework

## Deferred Ideas

None — discussion stayed within phase scope
