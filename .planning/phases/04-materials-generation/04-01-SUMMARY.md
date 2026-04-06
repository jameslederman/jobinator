---
phase: 04-materials-generation
plan: 01
subsystem: database
tags: [sqlmodel, alembic, pydantic, weasyprint, jinja2, materials, generation]

# Dependency graph
requires:
  - phase: 03-llm-scoring
    provides: "JobScore SQLModel table, ScoringConfig pattern, Instructor/LiteLLM setup"
  - phase: 01-foundation
    provides: "SQLModel + Alembic migration infrastructure, NormalizedJob FK target, settings pattern"
provides:
  - "GeneratedMaterial SQLModel table (FK to normalizedjob.id) for persisting generated bundles"
  - "ResumeContent, CoverLetterContent, PrepBriefContent, TailoredWorkEntry Pydantic models for LLM output contracts"
  - "MaterialsConfig with get_materials_config() for [materials] TOML section loading"
  - "jinja2 and weasyprint declared as dependencies with macOS runtime fix"
  - "Alembic migration 1dfa4707eb26 applied"
affects: [04-02-generation-logic, 04-03-renderer, 04-04-cli]

# Tech tracking
tech-stack:
  added:
    - "jinja2>=3.1 — HTML templating for resume/cover letter rendering"
    - "weasyprint>=62 (68.1 installed) — HTML-to-PDF rendering"
  patterns:
    - "Pydantic BaseModel (not SQLModel) for LLM response_model contracts — same as JobScoreOutput"
    - "Standalone BaseModel config (MaterialsConfig) following ScoringConfig/DiscoveryConfig pattern"
    - "macOS WeasyPrint: sitecustomize.py in venv sets DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib"

key-files:
  created:
    - "src/jobinator/generation/__init__.py — generation module package init"
    - "src/jobinator/generation/models.py — ResumeContent, CoverLetterContent, PrepBriefContent, TailoredWorkEntry"
    - "src/jobinator/models/material.py — GeneratedMaterial SQLModel table"
    - "alembic/versions/1dfa4707eb26_add_generated_material_table.py — migration for generatedmaterial table"
  modified:
    - "src/jobinator/configs/settings.py — added MaterialsConfig class and get_materials_config()"
    - "alembic/env.py — added material and score model imports for autogenerate"
    - "pyproject.toml + uv.lock — added jinja2 and weasyprint dependencies"

key-decisions:
  - "MaterialsConfig as standalone BaseModel (not Settings subclass) — consistent with ScoringConfig/DiscoveryConfig pattern for test-overridable config"
  - "Generation response models (ResumeContent, CoverLetterContent, PrepBriefContent) as plain Pydantic BaseModel not SQLModel — same pattern as JobScoreOutput in Phase 3"
  - "WeasyPrint macOS fix: sitecustomize.py in venv sets DYLD_FALLBACK_LIBRARY_PATH to /opt/homebrew/lib at Python startup — eliminates need for env var in every shell invocation"
  - "GeneratedMaterial confirmed=True always — only persisted after user confirmation, no in-progress tracking row"

patterns-established:
  - "LLM response model pattern: plain Pydantic BaseModel for Instructor response_model, separate SQLModel table for DB persistence"
  - "Config pattern: standalone BaseModel with get_{subsystem}_config(config_dir) factory loading from TOML section"

requirements-completed: [MATL-01, MATL-02, MATL-03, MATL-04, MATL-06]

# Metrics
duration: 7min
completed: 2026-04-06
---

# Phase 4 Plan 1: Materials Generation Data Layer Summary

**GeneratedMaterial SQLModel table, Pydantic LLM output contracts (ResumeContent/CoverLetterContent/PrepBriefContent), MaterialsConfig, Alembic migration, and WeasyPrint + Jinja2 dependency declarations with macOS runtime fix**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-06T18:42:48Z
- **Completed:** 2026-04-06T18:49:45Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Created `GeneratedMaterial` SQLModel table with FK to `normalizedjob.id`, all tracking fields (bundle_path, word counts, cost, model_used, confirmed), and Alembic migration applied
- Created `src/jobinator/generation/` module with four Pydantic response models defining strict LLM output contracts with grounding instructions in field descriptions (all claims must trace to profile)
- Added `MaterialsConfig` and `get_materials_config()` to settings following the established standalone BaseModel pattern; resolved WeasyPrint macOS library path issue via `sitecustomize.py`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create GeneratedMaterial model, generation response models, and MaterialsConfig** - `85d654d` (feat)
2. **Task 2: Alembic migration, dependency declarations, and import registration** - `fa431e0` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `src/jobinator/generation/__init__.py` — generation module package init
- `src/jobinator/generation/models.py` — TailoredWorkEntry, ResumeContent, CoverLetterContent, PrepBriefContent Pydantic response models
- `src/jobinator/models/material.py` — GeneratedMaterial SQLModel table (FK normalizedjob.id, bundle_path, counts, cost, confirmed)
- `src/jobinator/configs/settings.py` — MaterialsConfig class + get_materials_config() factory (added after ScoringConfig)
- `alembic/env.py` — added `material, score` to model imports for autogenerate
- `alembic/versions/1dfa4707eb26_add_generated_material_table.py` — migration creating generatedmaterial table + ix_generatedmaterial_job_id index
- `pyproject.toml` + `uv.lock` — added jinja2>=3.1, weasyprint>=62 (weasyprint 68.1 installed with 14 transitive deps)

## Decisions Made

- **MaterialsConfig as standalone BaseModel:** Consistent with ScoringConfig/DiscoveryConfig pattern — not a Settings subclass — allows test-overridable config without requiring config files on disk. Phase 1 Pitfall 7.
- **Response models as plain Pydantic BaseModel:** Same pattern as JobScoreOutput in Phase 3 — Instructor response_model is separate from DB persistence model. Clear separation of concerns.
- **WeasyPrint macOS fix via sitecustomize.py:** WeasyPrint needs `libgobject-2.0.0.dylib` (present in `/opt/homebrew/lib`) but macOS doesn't include it in the default dyld search path. Created `.venv/.../sitecustomize.py` that sets `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` at Python startup. Works without any env var in shell.
- **confirmed=True always on GeneratedMaterial:** Only persisted after user confirmation — no in-progress tracking row needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] WeasyPrint macOS libgobject not found**
- **Found during:** Task 2 (WeasyPrint runtime verification)
- **Issue:** WeasyPrint imports failed with `OSError: cannot load library 'libgobject-2.0-0'` because macOS dyld search path doesn't include `/opt/homebrew/lib` by default
- **Fix:** `brew install weasyprint` installed pango/glib system deps; created `.venv/lib/python3.12/site-packages/sitecustomize.py` that sets `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` at Python startup. `DYLD_LIBRARY_PATH` env var and symlinks did not resolve the issue; `sitecustomize.py` was the reliable path.
- **Files modified:** `.venv/lib/python3.12/site-packages/sitecustomize.py` (venv file, not committed to repo)
- **Verification:** `uv run python -c "from weasyprint import HTML; HTML(string='<p>test</p>').write_pdf('/tmp/t.pdf')"` exits 0
- **Committed in:** fa431e0 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** WeasyPrint is operational on macOS. sitecustomize.py in venv is not committed to the repo (venv is gitignored) — future setup will need pango + the sitecustomize.py. This should be documented for onboarding.

## Issues Encountered

- WeasyPrint on macOS requires Homebrew pango/glib system libraries. The library name WeasyPrint looks for (`libgobject-2.0-0`) differs from the macOS naming convention (`libgobject-2.0.0.dylib`). Resolved via sitecustomize.py approach — note that this fix lives in the venv and will need to be reapplied if the venv is recreated.

## User Setup Required

None — no external service configuration required. WeasyPrint system library fix is applied automatically via sitecustomize.py in the venv (requires `brew install pango` on fresh macOS setups).

## Next Phase Readiness

- All type contracts stable and importable: `GeneratedMaterial`, `ResumeContent`, `CoverLetterContent`, `PrepBriefContent`, `TailoredWorkEntry`, `MaterialsConfig`
- Alembic migration applied, `generatedmaterial` table exists in the database
- WeasyPrint produces valid PDFs from HTML — renderer can use it in Plan 03
- Plan 02 (generation logic) can import from `jobinator.generation.models` and `jobinator.models.material` immediately

---
*Phase: 04-materials-generation*
*Completed: 2026-04-06*

## Self-Check: PASSED

All files verified present. All commits verified in git history.

- FOUND: `src/jobinator/generation/__init__.py`
- FOUND: `src/jobinator/generation/models.py`
- FOUND: `src/jobinator/models/material.py`
- FOUND: `alembic/versions/1dfa4707eb26_add_generated_material_table.py`
- FOUND: `.planning/phases/04-materials-generation/04-01-SUMMARY.md`
- FOUND: commit `85d654d` (Task 1)
- FOUND: commit `fa431e0` (Task 2)
