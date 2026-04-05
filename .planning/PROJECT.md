# Jobinator

## What This Is

A local-first, agent-driven job search and application optimization system for a senior DS/ML engineer who is actively searching. Jobinator discovers high-fit opportunities from multiple sources, scores them against a detailed profile, generates tailored application materials (resume, cover letter, prep briefs), and optionally assists with form-filling submission. It's a developer tool, not a SaaS product — CLI-first, fully controlled, budget-aware.

## Core Value

Surface high-fit opportunities I'd miss manually and generate application materials good enough to submit with minimal editing — so I spend time on interviews, not applications.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Multi-source job discovery (Wellfound, Greenhouse/Lever ATS, HN Who's Hiring)
- [ ] Structured job data normalization (title, company, location, description, requirements, salary, URL, source)
- [ ] Hybrid fit scoring: hard filters (location, salary, keywords) then LLM-based nuanced evaluation
- [ ] Fit score output: score 0-1, strengths match, gaps, compensation estimate, priority score
- [ ] JSON Resume base profile with programmatic tailoring per role
- [ ] Tailored resume generation that emphasizes relevant experience while staying truthful
- [ ] Concise, company+role-specific cover letter generation
- [ ] Interview prep brief generation (company overview, likely questions, talking points)
- [ ] Application materials saved to configurable output directory (~/jobinator-output/ default)
- [ ] Materials versioned and structured per company/role
- [ ] Three application modes: manual assist, human-in-the-loop, form-filling assist
- [ ] SQLite + SQLModel persistent state (jobs seen, scored, applied, materials, outcomes)
- [ ] Deduplication — no re-processing or duplicate applications
- [ ] Custom Python agent loop with tool dispatch (no framework dependency)
- [ ] Multi-provider LLM: cheap models for filtering/scoring, strong models for generation
- [ ] Token/API spend tracking with configurable daily and per-job budgets
- [ ] CLI interface (discover, score, apply, run --auto, review)
- [ ] Decision logging with reasoning for every ignore/track/apply choice
- [ ] Feedback loop: track response/interview/offer rates to refine scoring and targeting

### Out of Scope

- SaaS/multi-user features — this is a single-user developer tool
- LinkedIn scraping — legal/technical complexity, not worth it for v1
- Browser automation for apply — brittle, prefer form-filling assist and API submission
- Mobile app or web UI — CLI-first, optional dashboard later
- Full auto-apply without human confirmation — too risky for real applications
- Video resume or portfolio generation — text materials only

## Context

- User is a senior data scientist / ML engineer with strong Python, ML systems, forecasting, LLMs, experimentation, and analytics background
- Target roles: senior/staff DS, ML engineer, applied AI, decision science, early-stage startups, high-impact roles
- Preferences: high comp or strong upside, technically challenging work, lean teams, high ownership
- Anti-pattern: low-signal spray-and-apply — quality over quantity
- Active job search — speed to usable MVP is critical
- Local-first architecture: all data stays on disk, user controls everything

## Constraints

- **Tech stack**: Python, SQLite + SQLModel, CLI (Click or Typer), JSON Resume format
- **LLM providers**: Multi-provider — Haiku/GPT-4o-mini for filtering, Claude/GPT-4 for generation
- **Agent framework**: Custom loop, no LangChain/LangGraph dependency
- **Storage**: SQLite for state, configurable filesystem directory for generated materials
- **Budget**: Must track and respect configurable token/API spend limits
- **Timeline**: Active search — MVP must be usable quickly, iterate from there

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Custom agent loop over framework | No framework lock-in, full control over budget/interruption, simpler debugging | -- Pending |
| Multi-provider LLM strategy | Cheap models for high-volume filtering, strong models for quality-critical generation | -- Pending |
| JSON Resume format | Structured, portable, renders to multiple formats, easy to diff/version | -- Pending |
| SQLModel over raw SQL | Typed models that double as data schemas, Pydantic integration | -- Pending |
| Heuristics + LLM scoring | Hard filters are cheap and fast, LLM adds nuance — best of both | -- Pending |
| Form-filling assist over auto-submit | Lower risk than full automation, still saves significant time | -- Pending |
| Skip LinkedIn for v1 | Legal/technical scraping complexity not worth it when other sources available | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-05 after Phase 1 (Foundation) completion — data layer, pipeline skeleton, and budget rails operational*
