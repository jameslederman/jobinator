---
phase: 01-foundation
plan: 01
subsystem: database
tags: [python, sqlmodel, alembic, sqlite, pydantic-settings, typer, uv, pre-commit]

# Dependency graph
requires: []
provides:
  - NormalizedJob SQLModel table with salary quad, location fields, freshness timestamps, description_hash
  - StatusEvent SQLModel table for append-only event-sourced status tracking
  - SpendRecord and DecisionLog SQLModel tables for budget and decision audit trail
  - SQLite engine factory with WAL mode pragma
  - Settings class loading from .env + TOML via pydantic-settings
  - Alembic initial migration generating all 4 tables
  - uv Python project scaffold with Python 3.12, all runtime and dev dependencies
  - All D-16 subpackages: agents/, tools/, pipelines/, scoring/, memory/, configs/, budget/, output/
  - Pre-commit hooks with ruff and mypy configured and installed
affects: [02-ingestion, 03-scoring, 04-materials, 05-cli]

# Tech tracking
tech-stack:
  added:
    - uv 0.11.3 (package manager)
    - Python 3.12.13 (via uv)
    - sqlmodel 0.0.38
    - alembic 1.18.4
    - pydantic 2.12.5
    - pydantic-settings 2.13.1
    - typer 0.24.1
    - rich 14.3.3
    - rapidfuzz 3.14.3
    - platformdirs 4.9.4
    - python-dotenv 1.2.2
    - pytest 9.0.2
    - factory-boy 3.3.3
    - ruff 0.15.9
    - mypy 1.20.0
    - pre-commit 4.5.1
  patterns:
    - SQLModel table classes double as DB schema and Pydantic validators (single-class pattern)
    - Event-sourced status via append-only StatusEvent table (D-03)
    - Salary modeled as four-field quad: posted min/max + estimated min/max (D-01)
    - pydantic-settings with settings_customise_sources() for TOML + .env loading (D-14)
    - Alembic env.py reads DATABASE_URL from env var (for tests) or settings (for prod)
    - Migration files must include `import sqlmodel` due to sqlmodel.sql.sqltypes.AutoString usage

key-files:
  created:
    - src/jobinator/models/job.py
    - src/jobinator/models/budget.py
    - src/jobinator/models/__init__.py
    - src/jobinator/configs/settings.py
    - src/jobinator/db.py
    - alembic/env.py
    - alembic/script.py.mako
    - alembic/versions/e86913dc4de1_initial_schema.py
    - tests/conftest.py
    - tests/test_models.py
    - pyproject.toml
    - uv.lock
    - .env.example
    - .pre-commit-config.yaml
  modified:
    - src/jobinator/__init__.py (added __version__)
    - src/jobinator/configs/__init__.py (added Settings, get_settings exports)
    - alembic.ini (cleared sqlalchemy.url, set programmatically)

key-decisions:
  - "uv_build replaced by hatchling as build backend for better ecosystem compatibility"
  - "pydantic-settings TOML loading requires settings_customise_sources() method with TomlConfigSettingsSource, not just toml_file in model_config"
  - "Alembic autogenerate produces sqlmodel.sql.sqltypes.AutoString references — migration files and script.py.mako template must include import sqlmodel"
  - "DATABASE_URL env var checked first in alembic/env.py to enable test isolation without touching settings"
  - "test_alembic_upgrade_head must run subprocess from project_root (not tmp_path) so alembic.ini is found"

patterns-established:
  - "Pattern: All SQLModel table classes imported in models/__init__.py for unified import surface"
  - "Pattern: get_settings() factory with @lru_cache — single Settings instance per process"
  - "Pattern: get_engine(url=None) accepts optional override — enables test isolation with :memory: DBs"
  - "Pattern: Alembic migrations run in subprocess tests using DATABASE_URL env var override"

requirements-completed: [INFR-04, DISC-06]

# Metrics
duration: 7min
completed: 2026-04-05
---

# Phase 01, Plan 01: Foundation Summary

**SQLite data layer with NormalizedJob/StatusEvent/SpendRecord/DecisionLog SQLModel tables, Alembic migration, WAL-mode engine, and pydantic-settings config — all 7 model tests passing including end-to-end Alembic upgrade verification**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-05T01:36:55Z
- **Completed:** 2026-04-05T01:43:35Z
- **Tasks:** 2
- **Files modified:** 19

## Accomplishments

- Scaffolded Python 3.12 project with uv, hatchling, all runtime and dev dependencies (sqlmodel, alembic, pydantic-settings, typer, rich, rapidfuzz, etc.)
- Implemented all 4 SQLModel table classes: NormalizedJob (salary quad D-01, location D-02, freshness timestamps DISC-06, description_hash D-05), StatusEvent (event-sourced D-03), SpendRecord, DecisionLog (INFR-06)
- Configured Alembic with initial migration that correctly creates all 4 tables; end-to-end upgrade path tested in test_alembic_upgrade_head
- Settings class loading from .env + TOML via pydantic-settings with proper settings_customise_sources() implementation
- All 7 model tests pass (no flakiness)

## Task Commits

1. **Task 1: Project scaffold** - `b623642` (feat)
2. **Task 2: SQLModel tables, Alembic, settings, tests** - `3e6ef36` (feat)

## Files Created/Modified

- `src/jobinator/models/job.py` - NormalizedJob, StatusEvent, JobStatus, LocationType, SalarySource
- `src/jobinator/models/budget.py` - SpendRecord, DecisionLog
- `src/jobinator/configs/settings.py` - Settings class with TOML + .env loading
- `src/jobinator/db.py` - get_engine() with WAL mode, get_session(), init_db()
- `alembic/env.py` - Alembic config targeting SQLModel.metadata, DATABASE_URL env var support
- `alembic/versions/e86913dc4de1_initial_schema.py` - Initial schema migration
- `tests/conftest.py` - in-memory engine and session fixtures
- `tests/test_models.py` - 7 model tests including alembic upgrade end-to-end test
- `pyproject.toml` - project config with hatchling, all deps, ruff/mypy config

## Decisions Made

- Replaced uv_build with hatchling as build backend (uv_build is new/less tested, hatchling is standard)
- pydantic-settings TOML support requires `settings_customise_sources()` override with `TomlConfigSettingsSource` — the `toml_file` shorthand in `model_config` triggers a warning and is silently ignored without it
- Alembic autogenerate emits `sqlmodel.sql.sqltypes.AutoString` in migration files but doesn't add the import — fixed in migration file and baked into script.py.mako template for future migrations

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pydantic-settings TOML configuration emitting UserWarning**
- **Found during:** Task 2 (running alembic revision)
- **Issue:** `toml_file` in `model_config` silently ignored without TomlConfigSettingsSource; pydantic-settings emits UserWarning
- **Fix:** Replaced shorthand with `settings_customise_sources()` override that conditionally adds `TomlConfigSettingsSource` when the TOML file exists
- **Files modified:** src/jobinator/configs/settings.py
- **Verification:** No warning emitted; tests pass
- **Committed in:** 3e6ef36

**2. [Rule 1 - Bug] Fixed alembic env.py failing when parent DB directory doesn't exist**
- **Found during:** Task 2 (alembic revision --autogenerate)
- **Issue:** Default database_url points to ~/.local/share/jobinator/ which doesn't exist; sqlite3.OperationalError: unable to open database file
- **Fix:** Added os.makedirs(parent, exist_ok=True) in get_url() in alembic/env.py
- **Files modified:** alembic/env.py
- **Verification:** alembic revision --autogenerate succeeds
- **Committed in:** 3e6ef36

**3. [Rule 1 - Bug] Fixed missing `import sqlmodel` in autogenerated migration file**
- **Found during:** Task 2 (test_alembic_upgrade_head)
- **Issue:** Alembic autogenerate emits sqlmodel.sql.sqltypes.AutoString() references but doesn't add `import sqlmodel`; NameError at runtime
- **Fix:** Added `import sqlmodel` to migration file; also added to script.py.mako template so future migrations include it
- **Files modified:** alembic/versions/e86913dc4de1_initial_schema.py, alembic/script.py.mako
- **Verification:** test_alembic_upgrade_head passes
- **Committed in:** 3e6ef36

**4. [Rule 1 - Bug] Fixed test_freshness_metadata timing race**
- **Found during:** Task 2 (test run)
- **Issue:** `before = datetime.utcnow()` was captured after `make_job()` created NormalizedJob (which calls default_factory), causing assertion `before <= first_seen_at` to fail by microseconds
- **Fix:** Moved `before = datetime.utcnow()` to before `make_job()` call
- **Files modified:** tests/test_models.py
- **Verification:** test_freshness_metadata passes consistently
- **Committed in:** 3e6ef36

**5. [Rule 1 - Bug] Fixed test_alembic_upgrade_head using wrong cwd**
- **Found during:** Task 2 (test run)
- **Issue:** Test was using `tmp_path.parent.parent` as cwd, but tmp_path is in /private/var/folders — alembic couldn't find alembic.ini
- **Fix:** Changed cwd to `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` (the project root)
- **Files modified:** tests/test_models.py
- **Verification:** test_alembic_upgrade_head passes
- **Committed in:** 3e6ef36

---

**Total deviations:** 5 auto-fixed (5 Rule 1 bugs)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. All were integration bugs discovered during execution of planned tasks.

## Issues Encountered

- uv init generates uv_build as build backend (new uv feature); switched to hatchling for broader ecosystem compatibility
- Alembic/SQLModel autogenerate integration requires manual `import sqlmodel` in migration files — documented in script.py.mako template to prevent future recurrence

## User Setup Required

None - no external service configuration required. API keys can optionally be added to `.env` based on `.env.example`.

## Next Phase Readiness

- Data layer is complete and tested; Phase 02 (ingestion) can start immediately
- All SQLModel table classes importable from `jobinator.models`
- Settings and engine factory ready for use by all downstream components
- Alembic upgrade path verified end-to-end — future migrations can be generated with `uv run alembic revision --autogenerate -m "description"`

## Self-Check: PASSED

- FOUND: src/jobinator/models/job.py
- FOUND: src/jobinator/models/budget.py
- FOUND: src/jobinator/db.py
- FOUND: src/jobinator/configs/settings.py
- FOUND: alembic/env.py
- FOUND: commit b623642 (Task 1: project scaffold)
- FOUND: commit 3e6ef36 (Task 2: SQLModel tables, Alembic, tests)
- All 7 pytest tests passing

---
*Phase: 01-foundation*
*Completed: 2026-04-05*
