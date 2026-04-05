# Phase 1: Foundation - Research

**Researched:** 2026-04-04
**Domain:** Python project scaffolding, SQLModel/Alembic data layer, normalization pipeline, heuristic filtering, budget tracker infrastructure, output directory management
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema Design**
- D-01: Salary modeled as four fields: `salary_min`, `salary_max` (posted, nullable), plus `estimated_salary_min`, `estimated_salary_max` (estimated, nullable). A `salary_source` enum (posted, estimated, unknown) indicates provenance. Estimation logic deferred to scoring phase — foundation just defines the fields.
- D-02: Location modeled as `location_type` enum (remote, hybrid, onsite, unknown) plus `location_raw` free text string for the original posting text.
- D-03: Job status is event-sourced. An append-only `status_events` table with timestamps. Current status derived from latest event. Status values: discovered, scored, applied, phone_screen, interview, rejected, offer.
- D-04: Company dedup uses two layers: deterministic slug (lowercase, strip Inc/LLC/Corp, collapse whitespace, replace special chars) for exact match, plus rapidfuzz second pass for near-misses above a configurable threshold.
- D-05: Dedup key is compound: `(company_slug, title_normalized)` plus description content hash as a secondary signal.

**Filter Configuration**
- D-06: Filter rules defined in TOML config file (~/.config/jobinator/config.toml) with CLI flag overrides. CLI flags take precedence.
- D-07: Filters combine as AND between groups, OR within groups. e.g., `(salary >= 150k) AND (title matches "ML" OR "data science") AND (location = remote OR hybrid)`.
- D-08: Each filter has a configurable `on_missing` behavior: pass (default), fail, or estimate. Controls what happens when the job posting lacks the field being filtered.
- D-09: Both include and exclude lists supported: `title_include`, `title_exclude`, `company_exclude`. Exclude lists are checked first (reject beats match).

**Output Directory Structure**
- D-10: Materials organized as `{output_dir}/{company_slug}/{role_slug}/{ISO-timestamp}/`. Default output_dir: `~/jobinator-output/`.
- D-11: Each application folder contains full bundle: resume.pdf, cover_letter.pdf, prep_brief.pdf, resume.md (source), cover_letter.md (source), prep_brief.md (source), job_description.md (snapshot), scoring.json (score output), metadata.json (job info, generation params, timestamps).
- D-12: A `latest/` symlink in each company/role directory points to the most recent timestamp folder.

**Project Scaffolding**
- D-13: Package manager: uv. pyproject.toml based with lockfile.
- D-14: Config: TOML file (~/.config/jobinator/config.toml) for settings, .env for secrets (API keys). pydantic-settings loads both.
- D-15: CLI framework: Typer with Rich for formatted output.
- D-16: Source layout: `src/jobinator/` with subpackages: agents/, tools/, pipelines/, scoring/, memory/, configs/.
- D-17: SQLite + SQLModel for persistence, Alembic for schema migrations.

### Claude's Discretion
- Exact Pydantic model field names and types (as long as they follow the decisions above)
- Alembic migration setup approach
- Internal module boundaries within the src/jobinator/ package
- Test framework choice and structure
- Logging framework and configuration

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DISC-04 | All discovered jobs are normalized to a standard schema (title, company, location, description, requirements, salary_range, url, source) | NormalizedJob SQLModel table with all required fields; normalization pipeline patterns documented |
| DISC-05 | Jobs are deduplicated across sources using compound key (company_normalized, title_normalized) plus description content hash | rapidfuzz 3.13.0 available; two-layer dedup pattern (slug exact match + fuzzy second pass) documented |
| DISC-06 | Jobs include freshness metadata (posted_at, first_seen, last_seen) and stale postings are deprioritized | SQLModel datetime fields; event-sourced status design enables deprioritization |
| SCOR-01 | User can configure hard filters (salary floor, location type, title keywords, exclusion keywords) | TOML config via pydantic-settings; AND/OR/on_missing filter architecture documented |
| INFR-04 | All job and application state persists in SQLite via SQLModel with schema migrations | SQLModel 0.0.34 + Alembic 1.16.5 documented; WAL mode pattern noted |
| INFR-06 | Agent loop is interruptible and logs all decisions | decision_log table in schema; BudgetExceeded exception pattern for hard stops |
</phase_requirements>

---

## Summary

Phase 1 builds the entire skeleton that downstream phases plug into. No external API calls, no LLM calls — pure Python with four distinct work areas: (1) project scaffolding with uv + pyproject.toml, (2) SQLite data layer via SQLModel with Alembic migrations, (3) normalization pipeline with deduplication logic, and (4) budget tracker infrastructure with a hard-stop mechanism.

The stack is well-established and all versions are current. The one friction point is uv not being installed on this machine — the planner must include a Wave 0 task to install uv before any `uv init` or `uv add` commands can run. Everything else is greenfield with no existing code to integrate around.

The event-sourced status design (D-03) and the two-layer dedup system (D-04, D-05) are the most architecturally non-trivial pieces. Both have clear implementation patterns documented below. The budget tracker needs to raise `BudgetExceeded` as a hard stop before any LLM call — this phase wires the infrastructure even though no LLM calls happen yet.

**Primary recommendation:** Build in strict dependency order: pyproject.toml scaffold → SQLModel models + Alembic → normalization pipeline → heuristic filter → output directory manager → budget tracker stub. Each layer is independently testable. Tests should be written alongside each component.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| uv | 0.4+ (install fresh) | Package manager + venv | Locked by D-13; 10-100x faster than pip, produces lockfile, now ecosystem standard for Python 2025 |
| SQLModel | 0.0.34 | ORM + Pydantic-native schema | Locked by D-17; single model class = DB table + Pydantic validator; no dual-model overhead |
| Alembic | 1.16.5 | Schema migrations | Locked by D-17; SQLModel has no built-in migration support; Alembic generates versioned migration scripts |
| Pydantic v2 | 2.12.5 | Data validation, config models | Foundation of SQLModel; all filter config and budget config use Pydantic BaseModel |
| pydantic-settings | 2.11.0 | Typed config from TOML + .env | Locked by D-14; merges config.toml settings and .env API keys into one typed Settings object |
| rapidfuzz | 3.13.0 | Fuzzy company name matching | Locked by D-04; fast C-extension fuzzy matching for dedup second pass |
| Typer | 0.23.2 | CLI framework | Locked by D-15; type-annotation-driven command definitions, built-in Rich integration |
| Rich | 14.3.3 | Terminal output formatting | Locked by D-15; tables, progress bars, styled console output |
| platformdirs | 4.4.0 | XDG-compliant config paths | Resolves `~/.config/jobinator/` correctly on macOS/Linux |
| python-dotenv | 1.2.1 | .env loading | Standard pattern for API key management in local dev tools |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tomli | 2.4.1 | TOML parsing (Python < 3.11) | System Python is 3.9.6; `tomllib` is stdlib only in Python 3.11+. Use `tomli` as backport. pydantic-settings reads TOML natively but `tomli` may be needed as a backend dep. |
| pytest | 8.4.2 | Test framework | All unit tests for normalization, filtering, budget tracker |
| factory-boy | 3.3.3 | Test fixtures | Generate realistic RawJob and NormalizedJob test objects |
| ruff | 0.15.9 | Linting + formatting | Replaces black/flake8/isort in one tool |
| mypy | 1.19.1 | Static type checking | Enforce types on SQLModel + Pydantic models from the start |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLModel | Raw SQLAlchemy | SQLAlchemy requires separate Pydantic models; doubles schema maintenance. SQLModel is correct here. |
| rapidfuzz | fuzzywuzzy / thefuzz | fuzzywuzzy is slower, pure Python, GPL-licensed. rapidfuzz is MIT, C-extension, faster. |
| pydantic-settings | dynaconf | pydantic-settings integrates natively with Pydantic v2; no extra dep. |
| Alembic | Manual DDL | Schema will definitely change across 5 phases; manual DDL means wiping the DB to migrate. |

**Installation (once uv is available):**
```bash
# Install uv first (one-time system install)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project
uv init jobinator --lib
cd jobinator

# Core runtime dependencies
uv add sqlmodel>=0.0.34 alembic>=1.16.5 pydantic>=2.12.5 pydantic-settings>=2.11.0
uv add typer>=0.23.2 rich>=14.3.3 rapidfuzz>=3.13.0 platformdirs>=4.4.0
uv add python-dotenv>=1.2.1 tomli>=2.4.1

# Dev dependencies
uv add --dev pytest>=8.4.2 factory-boy>=3.3.3 ruff>=0.15.9 mypy>=1.19.1
```

**Version verification:** All versions confirmed from PyPI registry on 2026-04-04.

---

## Architecture Patterns

### Recommended Project Structure
```
src/jobinator/
├── __init__.py
├── cli.py               # Typer app entry point (minimal in Phase 1)
├── db.py                # SQLite engine creation, session factory, WAL pragma
├── models/
│   ├── __init__.py
│   ├── job.py           # NormalizedJob, RawJob, StatusEvent SQLModel tables
│   ├── score.py         # JobScore, HeuristicResult models
│   ├── budget.py        # SpendRecord SQLModel table, BudgetConfig Pydantic model
│   └── output.py        # GeneratedMaterial SQLModel table
├── pipelines/
│   ├── __init__.py
│   ├── normalize.py     # RawJob -> NormalizedJob transformation
│   ├── dedup.py         # Two-layer dedup: slug exact + rapidfuzz fuzzy
│   └── filter.py        # Heuristic hard filter, FilterConfig
├── configs/
│   ├── __init__.py
│   └── settings.py      # pydantic-settings Settings class, TOML + .env loading
├── budget/
│   ├── __init__.py
│   └── tracker.py       # BudgetTracker, BudgetExceeded exception
└── output/
    ├── __init__.py
    └── manager.py       # OutputManager: directory creation, symlinks

alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 0001_initial.py  # First migration: all Phase 1 tables

tests/
├── conftest.py          # pytest fixtures: engine, session, sample jobs
├── test_normalize.py
├── test_dedup.py
├── test_filter.py
├── test_budget.py
└── test_output.py

pyproject.toml
alembic.ini
.env.example
~/.config/jobinator/config.toml  (user-created, not in repo)
```

### Pattern 1: SQLModel Table with Event-Sourced Status (D-03)

The user decided against a single `status` enum on the job — status is an append-only event log. Current status is derived from the latest event.

**What:** `NormalizedJob` stores job data. `StatusEvent` is a separate append-only table. Current status is always `SELECT ... ORDER BY created_at DESC LIMIT 1`.

**When to use:** Whenever you need to record when status changed and what triggered it. Required by INFR-06 (decision logging) and APPL-04 (outcome tracking).

```python
# Source: SQLModel documentation patterns + project decisions D-03
from enum import Enum
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class JobStatus(str, Enum):
    discovered = "discovered"
    scored = "scored"
    applied = "applied"
    phone_screen = "phone_screen"
    interview = "interview"
    rejected = "rejected"
    offer = "offer"


class NormalizedJob(SQLModel, table=True):
    id: str = Field(primary_key=True)  # uuid4
    source: str
    source_url: str = Field(unique=True, index=True)
    title: str
    title_normalized: str = Field(index=True)
    company: str
    company_slug: str = Field(index=True)
    location_raw: Optional[str] = None
    location_type: Optional[str] = None  # LocationType enum as str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    estimated_salary_min: Optional[int] = None
    estimated_salary_max: Optional[int] = None
    salary_source: Optional[str] = None  # SalarySource enum as str
    description: str
    posted_at: Optional[datetime] = None
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    description_hash: str = Field(index=True)  # sha256 first 500 chars
    raw_json: str  # JSON string of original payload


class StatusEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    job_id: str = Field(foreign_key="normalizedjob.id", index=True)
    status: str  # JobStatus enum as str
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Pattern 2: Two-Layer Company Deduplication (D-04, D-05)

**What:** Layer 1 is deterministic slug matching — fast O(1) lookup. Layer 2 is rapidfuzz fuzzy matching for near-misses (e.g., "Anthropic PBC" vs "Anthropic").

**When to use:** Every time a RawJob is about to be inserted. Called from the normalization pipeline.

```python
# Source: project decisions D-04, D-05; rapidfuzz docs
import re
import hashlib
from rapidfuzz import fuzz

STRIP_SUFFIXES = re.compile(
    r'\s+(inc\.?|llc\.?|corp\.?|ltd\.?|co\.?|company|group|holdings|technologies|tech)$',
    re.IGNORECASE
)

def make_company_slug(name: str) -> str:
    name = STRIP_SUFFIXES.sub("", name.strip())
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s-]', '', name)
    name = re.sub(r'[\s]+', '-', name.strip())
    return name[:40]

def make_title_normalized(title: str) -> str:
    title = title.lower()
    title = re.sub(r'\b(sr\.?|senior)\b', 'senior', title)
    title = re.sub(r'\b(jr\.?|junior)\b', 'junior', title)
    title = re.sub(r'\b(eng\.?|engineer)\b', 'engineer', title)
    title = re.sub(r'[^a-z0-9\s]', '', title)
    return re.sub(r'\s+', ' ', title).strip()

def make_description_hash(description: str) -> str:
    return hashlib.sha256(description[:500].encode()).hexdigest()[:16]

def is_duplicate(
    company_slug: str,
    title_normalized: str,
    description_hash: str,
    existing_slugs: set[str],        # from DB: all known company slugs
    existing_titles: dict[str, str], # {company_slug: title_normalized}
    fuzzy_threshold: int = 90,
) -> bool:
    # Layer 1: exact slug match
    compound_key = f"{company_slug}::{title_normalized}"
    if compound_key in existing_titles:
        return True

    # Layer 2: fuzzy match on company slug, then check title
    for known_slug in existing_slugs:
        if fuzz.ratio(company_slug, known_slug) >= fuzzy_threshold:
            known_title = existing_titles.get(known_slug, "")
            if fuzz.ratio(title_normalized, known_title) >= fuzzy_threshold:
                return True

    return False
```

### Pattern 3: Heuristic Filter with AND/OR/on_missing (D-06 through D-09)

**What:** FilterConfig loaded from TOML. Filters combine AND between groups, OR within groups. Each filter respects `on_missing` behavior.

**When to use:** Every NormalizedJob passes through this before any LLM scoring is triggered.

```python
# Source: project decisions D-06 through D-09
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class OnMissing(str, Enum):
    pass_ = "pass"
    fail = "fail"
    estimate = "estimate"


class SalaryFilter(BaseModel):
    min_usd: Optional[int] = None
    on_missing: OnMissing = OnMissing.pass_


class LocationFilter(BaseModel):
    allowed: list[str] = ["remote", "hybrid"]  # LocationType values
    on_missing: OnMissing = OnMissing.pass_


class TitleFilter(BaseModel):
    include: list[str] = []   # OR within this list
    exclude: list[str] = []   # checked first; any match = reject


class FilterConfig(BaseModel):
    salary: SalaryFilter = SalaryFilter()
    location: LocationFilter = LocationFilter()
    title: TitleFilter = TitleFilter()
    company_exclude: list[str] = []


class FilterResult(BaseModel):
    passed: bool
    reason: Optional[str] = None  # populated on failure


def apply_hard_filters(job: NormalizedJob, config: FilterConfig) -> FilterResult:
    # Exclude lists checked first (D-09: reject beats match)
    title_lower = job.title.lower()
    for excl in config.title.exclude:
        if excl.lower() in title_lower:
            return FilterResult(passed=False, reason=f"title_exclude: '{excl}'")
    for excl in config.company_exclude:
        if excl.lower() in job.company_slug:
            return FilterResult(passed=False, reason=f"company_exclude: '{excl}'")

    # Salary filter (D-07: AND between groups)
    if config.salary.min_usd is not None:
        effective_salary = job.salary_max or job.salary_min
        if effective_salary is None:
            if config.salary.on_missing == OnMissing.fail:
                return FilterResult(passed=False, reason="salary missing (on_missing=fail)")
        elif effective_salary < config.salary.min_usd:
            return FilterResult(passed=False, reason=f"salary {effective_salary} < floor {config.salary.min_usd}")

    # Location filter (D-07: AND between groups)
    if config.location.allowed:
        if job.location_type is None:
            if config.location.on_missing == OnMissing.fail:
                return FilterResult(passed=False, reason="location missing (on_missing=fail)")
        elif job.location_type not in config.location.allowed:
            return FilterResult(passed=False, reason=f"location_type {job.location_type!r} not in allowed")

    # Title include list (D-07: OR within group, D-09: include only relevant when exclude passes)
    if config.title.include:
        matched = any(kw.lower() in title_lower for kw in config.title.include)
        if not matched:
            return FilterResult(passed=False, reason="title matches none of title_include list")

    return FilterResult(passed=True)
```

### Pattern 4: BudgetTracker with Hard-Stop Gate (INFR-03 foundation)

**What:** BudgetTracker checks cumulative daily spend against the configured limit and raises `BudgetExceeded` before any LLM call. Phase 1 builds the infrastructure; Phase 3 wires it to actual LLM calls.

**When to use:** Called as a pre-call gate by the orchestrator before every LLM dispatch.

```python
# Source: ARCHITECTURE.md Component 8 pattern
from pydantic import BaseModel
from datetime import date


class BudgetConfig(BaseModel):
    daily_limit_usd: float = 5.00
    per_job_limit_usd: float = 0.50
    warn_threshold: float = 0.80


class BudgetExceeded(Exception):
    """Raised before an LLM call when budget limits would be exceeded."""
    pass


class BudgetTracker:
    def __init__(self, config: BudgetConfig, session):
        self.config = config
        self.session = session

    def daily_spend(self) -> float:
        today = date.today()
        # SELECT SUM(cost_usd) FROM spendrecord WHERE DATE(recorded_at) = today
        result = self.session.exec(...)
        return result or 0.0

    def job_spend(self, job_id: str) -> float:
        # SELECT SUM(cost_usd) FROM spendrecord WHERE job_id = job_id
        ...

    def assert_within_limits(self, job_id: str | None = None) -> None:
        """Call this BEFORE every LLM call. Raises BudgetExceeded if over limit."""
        spent = self.daily_spend()
        if spent >= self.config.daily_limit_usd:
            raise BudgetExceeded(
                f"Daily budget exhausted: ${spent:.4f} >= ${self.config.daily_limit_usd:.2f}"
            )
        if job_id:
            job_spent = self.job_spend(job_id)
            if job_spent >= self.config.per_job_limit_usd:
                raise BudgetExceeded(
                    f"Per-job budget exhausted for {job_id}: ${job_spent:.4f}"
                )

    def record(self, record: "SpendRecord") -> None:
        self.session.add(record)
        self.session.commit()
```

### Pattern 5: Alembic + SQLModel Integration

**What:** SQLModel uses SQLAlchemy under the hood. Alembic's `env.py` must be configured to use SQLModel's metadata, not raw SQLAlchemy metadata.

**When to use:** Set up once during project scaffold, then run `alembic revision --autogenerate` for each schema change.

```python
# alembic/env.py — key section
from sqlmodel import SQLModel
from jobinator.models import job, score, budget, output  # import all models to register them

target_metadata = SQLModel.metadata

# In run_migrations_online():
# Use SQLite URL from settings
from jobinator.configs.settings import get_settings
settings = get_settings()
connectable = create_engine(settings.database_url)
```

```bash
# Initialize Alembic (once)
alembic init alembic

# Generate first migration after models are defined
alembic revision --autogenerate -m "initial schema"

# Apply on startup (auto-migrate pattern for local tool)
alembic upgrade head
```

**Critical:** All SQLModel table classes must be imported before `alembic revision --autogenerate` is called, or Alembic won't detect the tables.

### Pattern 6: pydantic-settings with TOML + .env

**What:** `pydantic-settings` v2 can load from TOML via a custom source. Settings class merges config.toml (non-secrets) and .env (secrets).

```python
# src/jobinator/configs/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from platformdirs import user_config_dir
from pathlib import Path


class Settings(BaseSettings):
    # Resolved by platformdirs
    config_dir: Path = Path(user_config_dir("jobinator"))
    database_url: str = "sqlite:///~/.local/share/jobinator/jobinator.db"
    output_dir: Path = Path("~/jobinator-output").expanduser()

    # API keys from .env only
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Budget from config.toml
    daily_limit_usd: float = 5.00
    per_job_limit_usd: float = 0.50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

**Note on TOML loading:** pydantic-settings v2.11 supports TOML via `TomlConfigSettingsSource`. Since system Python is 3.9 (no stdlib `tomllib`), ensure `tomli` is installed as a dependency — pydantic-settings will use it automatically as the TOML parser on Python < 3.11.

### Pattern 7: Output Directory Manager (D-10 through D-12)

**What:** Creates the versioned directory tree and `latest/` symlink atomically.

```python
# src/jobinator/output/manager.py
from pathlib import Path
from datetime import datetime
import os


class OutputManager:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir.expanduser()

    def create_application_dir(self, company_slug: str, role_slug: str) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        app_dir = self.output_dir / company_slug / role_slug / timestamp
        app_dir.mkdir(parents=True, exist_ok=True)

        # Write placeholder metadata.json so directory is non-empty
        (app_dir / "metadata.json").write_text("{}")

        # Update latest/ symlink (D-12)
        latest_link = self.output_dir / company_slug / role_slug / "latest"
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink()
        os.symlink(app_dir, latest_link)

        return app_dir
```

### Anti-Patterns to Avoid

- **Boolean flag status tracking:** Never use `is_scored: bool`, `is_applied: bool`. Use the event-sourced `status_events` table (D-03). Multiple boolean flags create invalid states.
- **Skipping Alembic for "just SQLite":** Schema changes across 5 phases are certain. Set up Alembic in Wave 0, not after the first schema change breaks the DB.
- **Direct `os.environ.get()` for config:** All config access goes through the `Settings` class. No raw env var reads scattered through the codebase.
- **Importing models lazily in Alembic env.py:** Alembic autogenerate only detects models that have been imported. Explicitly import all model modules in `env.py` before calling `SQLModel.metadata`.
- **Symlink on Windows:** `os.symlink()` requires elevated privileges on Windows. For the `latest/` symlink (D-12), guard with `try/except OSError` and fall back to writing a `latest.txt` with the path. This is a macOS/Linux-first tool but shouldn't crash on Windows.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy company name matching | Custom edit-distance loop | rapidfuzz `fuzz.ratio()` | C extension, handles Unicode, far faster at scale |
| TOML config parsing | `re` + custom parser | pydantic-settings + tomli | Handles nested keys, type coercion, validation errors |
| XDG config path resolution | Hardcoded `~/.jobinator/` | platformdirs `user_config_dir()` | Respects macOS/Linux conventions correctly |
| DB schema versioning | Manual `ALTER TABLE` scripts | Alembic `revision --autogenerate` | Handles column adds/renames/drops with rollback support |
| .env loading | `os.environ` + file parsing | python-dotenv + pydantic-settings | Handles quoting, comments, override priority correctly |
| SHA-256 content hashing | Custom rolling hash | `hashlib.sha256()` (stdlib) | Already available, no dependency needed |

**Key insight:** In this phase, the library choices eliminate entire categories of bugs (migration drift, config type coercion failures, fuzzy matching edge cases) that custom implementations routinely get wrong.

---

## Common Pitfalls

### Pitfall 1: SQLModel Metadata Not Registered for Alembic Autogenerate
**What goes wrong:** Running `alembic revision --autogenerate` produces an empty migration (no tables detected) even though SQLModel tables are defined.
**Why it happens:** SQLModel registers tables in `SQLModel.metadata` only when the table class is imported. If `env.py` doesn't import model modules, the metadata is empty.
**How to avoid:** In `alembic/env.py`, import every model module before accessing `SQLModel.metadata`:
```python
from jobinator.models import job, score, budget, output  # noqa: F401 — side effects needed
target_metadata = SQLModel.metadata
```
**Warning signs:** `alembic revision --autogenerate` generates a migration file with only `def upgrade(): pass`.

### Pitfall 2: SQLModel Field Nullable vs Optional Mismatch
**What goes wrong:** SQLModel creates non-nullable DB columns for fields typed as `Optional[str]` without a `Field(default=None)`. Inserts fail with NOT NULL constraint violations.
**Why it happens:** SQLModel infers nullability from Pydantic's Optional typing, but requires explicit `Field(default=None)` to generate the correct DDL.
**How to avoid:** Always pair `Optional[T]` with `= Field(default=None)`:
```python
salary_min: Optional[int] = Field(default=None)  # correct
salary_min: Optional[int] = None  # may work but is ambiguous — prefer Field()
```
**Warning signs:** `IntegrityError: NOT NULL constraint failed` on insert despite field being Optional in Python.

### Pitfall 3: Alembic + SQLite Column Alteration
**What goes wrong:** Alembic's `op.alter_column()` fails silently or errors on SQLite because SQLite has very limited `ALTER TABLE` support (no column renames or type changes natively).
**Why it happens:** SQLite only supports `ADD COLUMN` in `ALTER TABLE`. Alembic's SQLite dialect works around this by recreating the table, but batch mode must be explicitly enabled.
**How to avoid:** Use `batch_alter_table` context in all Alembic migrations when SQLite is the target:
```python
with op.batch_alter_table("normalizedjob") as batch_op:
    batch_op.add_column(sa.Column("new_field", sa.String(), nullable=True))
```
Configure in `alembic.ini` or `env.py`: `render_as_batch=True`.
**Warning signs:** `OperationalError: Cannot add a NOT NULL column with a non-constant default` on SQLite.

### Pitfall 4: pydantic-settings TOML Loading Requires tomli on Python < 3.11
**What goes wrong:** `Settings()` raises `ImportError` or silently ignores TOML config file.
**Why it happens:** The system Python is 3.9.6. `tomllib` is stdlib only in Python 3.11+. pydantic-settings needs a TOML parser; on 3.9 it falls back to `tomli` if installed, but if `tomli` is missing, TOML loading silently fails or raises.
**How to avoid:** Add `tomli` as an explicit dependency in `pyproject.toml` for all Python < 3.11 targets.
**Warning signs:** Config values from `config.toml` are not reflected in `Settings()` even when file exists and is valid.

### Pitfall 5: Dedup Hash Computed After Text Cleanup
**What goes wrong:** Two versions of the same job (one with extra whitespace, one HTML-encoded) produce different hashes and pass through dedup as different jobs.
**Why it happens:** `description_hash` is computed on the raw description before normalization. Minor formatting differences produce different hashes.
**How to avoid:** Normalize description text before hashing: strip leading/trailing whitespace, collapse internal whitespace, strip HTML tags (if any), lowercase. Apply the same normalization consistently across all sources.
**Warning signs:** Same job from two sources appears twice in DB with slightly different description text.

### Pitfall 6: uv Not Installed (Blocking — No Fallback)
**What goes wrong:** All project setup commands (`uv init`, `uv add`) fail because uv is not installed on this machine.
**Why it happens:** uv is not pre-installed; it's a user-installed tool. The current machine has no uv installation.
**How to avoid:** Wave 0 must include a step to install uv via the official installer before any uv commands run:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env  # or restart shell
```
**Warning signs:** `command not found: uv` on first project setup command.

---

## Code Examples

Verified patterns from project architecture decisions and library documentation:

### SQLite WAL Mode + Auto-Migration on Startup
```python
# src/jobinator/db.py
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event
from alembic.config import Config
from alembic import command


def create_db_engine(db_url: str):
    engine = create_engine(db_url, echo=False)

    # Enable WAL mode for better read/write concurrency
    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def run_migrations(alembic_ini_path: str) -> None:
    """Apply all pending Alembic migrations. Safe to call on every startup."""
    alembic_cfg = Config(alembic_ini_path)
    command.upgrade(alembic_cfg, "head")


def get_session(engine) -> Session:
    return Session(engine)
```

### FilterConfig TOML Schema (config.toml format)
```toml
# ~/.config/jobinator/config.toml

[filters.salary]
min_usd = 150000
on_missing = "pass"

[filters.location]
allowed = ["remote", "hybrid"]
on_missing = "pass"

[filters.title]
include = ["machine learning", "data science", "ml engineer", "staff engineer"]
exclude = ["junior", "intern", "manager", "director", "VP"]

[filters]
company_exclude = ["company-i-wont-work-at"]

[budget]
daily_limit_usd = 5.00
per_job_limit_usd = 0.50
warn_threshold = 0.80

[output]
output_dir = "~/jobinator-output"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pip + venv for project setup | uv (pyproject.toml + lockfile) | 2024-2025 | 10-100x faster installs, deterministic environments; uv is now the Python project standard |
| `black` + `flake8` + `isort` separately | `ruff` for all three | 2023+ | Single tool, single config, extremely fast |
| SQLAlchemy + separate Pydantic models | SQLModel | 2021+ (stable 2023+) | One model class serves as both DB table and Pydantic validator |
| Separate Alembic model imports | `SQLModel.metadata` as Alembic target | Current | Avoids maintaining two separate metadata objects |
| `tomllib` (Python 3.11 stdlib) | `tomli` backport for Python < 3.11 | Python 3.11 release | System is 3.9.6; need explicit `tomli` dependency |

**Deprecated/outdated:**
- `fuzzywuzzy`: Superseded by `rapidfuzz` (same API surface, significantly faster, MIT license)
- Raw `os.path` for config dir resolution: Use `platformdirs.user_config_dir()` instead
- `black` + `flake8` + `isort` as separate tools: Replaced by `ruff` which covers all three

---

## Open Questions

1. **Python version in uv venv**
   - What we know: System Python is 3.9.6 (macOS system Python, likely old)
   - What's unclear: Should the project target Python 3.12+ (uv can fetch any CPython version) or pin to match system?
   - Recommendation: Use `uv python install 3.12` to fetch a project-local Python 3.12. This enables `tomllib` stdlib and modern type syntax. Add `requires-python = ">=3.12"` to `pyproject.toml`. System Python 3.9 becomes irrelevant once uv manages the venv.

2. **SQLModel v0.0.34 Pydantic v2 Compatibility**
   - What we know: SQLModel 0.0.21+ has official Pydantic v2 support; 0.0.34 is current.
   - What's unclear: Edge cases in Pydantic v2 strict mode validation with SQLModel table models have been reported in community but not widely documented.
   - Recommendation: Use Pydantic's default (non-strict) mode for SQLModel table classes. Reserve strict mode for standalone Pydantic BaseModel classes (FilterConfig, BudgetConfig).

3. **Alembic `render_as_batch` Global Default**
   - What we know: SQLite has limited ALTER TABLE support; batch mode is the workaround.
   - What's unclear: Whether to configure `render_as_batch=True` globally in `env.py` or on a per-migration basis.
   - Recommendation: Set globally in `env.py` (`context.configure(..., render_as_batch=True)`). Since this is SQLite-only, there is no downside.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | Project setup, package management (D-13) | No | — | None — locked decision. Must install before any other setup. |
| Python 3.x | All code | Yes | 3.9.6 (system) | uv will fetch Python 3.12 — use that instead |
| git | Version control | Yes | 2.50.1 | — |
| SQLite3 | Database engine | Yes | 3.51.0 (via stdlib) | — |
| pytest | Testing | Not installed | — | Install via uv dev deps in Wave 0 |
| All Python packages | Runtime | Not installed | — | Install via `uv add` in Wave 0 |

**Missing dependencies with no fallback:**
- `uv` — project locked to uv by D-13. Wave 0 must install it: `curl -LsSf https://astral.sh/uv/install.sh | sh`

**Missing dependencies with fallback:**
- All Python libraries (sqlmodel, alembic, pydantic, etc.) — not installed globally, but this is expected for a greenfield project. uv creates an isolated venv; global install not needed or desired.
- Python 3.9.6 is too old for stdlib `tomllib` — fallback is `tomli` PyPI package (include as dependency).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` section — Wave 0 creates this |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISC-04 | RawJob dict normalized to NormalizedJob with all required fields populated | unit | `uv run pytest tests/test_normalize.py -x` | Wave 0 |
| DISC-04 | Salary, location, company_slug parsed deterministically from various input formats | unit | `uv run pytest tests/test_normalize.py::test_salary_parsing -x` | Wave 0 |
| DISC-05 | Duplicate job (same company + title) rejected by dedup | unit | `uv run pytest tests/test_dedup.py::test_exact_dedup -x` | Wave 0 |
| DISC-05 | Near-duplicate company name ("Anthropic" vs "Anthropic PBC") caught by fuzzy second pass | unit | `uv run pytest tests/test_dedup.py::test_fuzzy_dedup -x` | Wave 0 |
| DISC-06 | NormalizedJob has first_seen_at, last_seen_at, posted_at fields; second ingest updates last_seen_at | unit | `uv run pytest tests/test_normalize.py::test_freshness_fields -x` | Wave 0 |
| SCOR-01 | Job failing salary floor rejected by heuristic filter with logged reason, no LLM called | unit | `uv run pytest tests/test_filter.py::test_salary_filter -x` | Wave 0 |
| SCOR-01 | Job failing location type filter (onsite-only when remote required) rejected | unit | `uv run pytest tests/test_filter.py::test_location_filter -x` | Wave 0 |
| SCOR-01 | Job with excluded title keyword rejected before include check | unit | `uv run pytest tests/test_filter.py::test_title_exclude -x` | Wave 0 |
| SCOR-01 | Job with missing salary and on_missing=pass passes filter | unit | `uv run pytest tests/test_filter.py::test_on_missing_pass -x` | Wave 0 |
| SCOR-01 | Job with missing salary and on_missing=fail rejected | unit | `uv run pytest tests/test_filter.py::test_on_missing_fail -x` | Wave 0 |
| INFR-04 | SQLite DB initializes on first run with all tables created | integration | `uv run pytest tests/test_db.py::test_db_init -x` | Wave 0 |
| INFR-04 | Alembic migration applies cleanly to fresh DB | integration | `uv run pytest tests/test_db.py::test_alembic_migration -x` | Wave 0 |
| INFR-04 | NormalizedJob persists to DB and reads back with all fields intact | integration | `uv run pytest tests/test_db.py::test_job_roundtrip -x` | Wave 0 |
| INFR-06 | BudgetTracker raises BudgetExceeded before LLM call when daily limit reached | unit | `uv run pytest tests/test_budget.py::test_daily_limit -x` | Wave 0 |
| INFR-06 | StatusEvent appended on each status transition; current status derived from latest event | unit | `uv run pytest tests/test_db.py::test_status_events -x` | Wave 0 |
| INFR-06 (output) | Output directory created at configured path with correct company/role/timestamp structure | unit | `uv run pytest tests/test_output.py::test_dir_creation -x` | Wave 0 |
| INFR-06 (output) | latest/ symlink updated to most recent timestamp on second generation | unit | `uv run pytest tests/test_output.py::test_latest_symlink -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q` (fast, stops on first failure)
- **Per wave merge:** `uv run pytest tests/ -v --tb=short` (full suite with details)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` — shared fixtures: in-memory SQLite engine, session, sample RawJob factory
- [ ] `tests/test_normalize.py` — covers DISC-04, DISC-06
- [ ] `tests/test_dedup.py` — covers DISC-05
- [ ] `tests/test_filter.py` — covers SCOR-01
- [ ] `tests/test_db.py` — covers INFR-04 (DB init, migrations, roundtrip, status events)
- [ ] `tests/test_budget.py` — covers INFR-06 (BudgetExceeded gate)
- [ ] `tests/test_output.py` — covers INFR-06 (directory creation, symlink)
- [ ] Framework install: `uv add --dev pytest>=8.4.2 factory-boy>=3.3.3` — pytest not yet installed

---

## Project Constraints (from CLAUDE.md)

The following directives from `CLAUDE.md` are mandatory. The planner must verify compliance:

| Directive | Constraint |
|-----------|------------|
| Tech stack | Python, SQLite + SQLModel, CLI (Typer), JSON Resume format only |
| LLM providers | LiteLLM for multi-provider; anthropic + openai SDKs as fallback (Phase 1 builds infrastructure, no actual LLM calls) |
| Agent framework | Custom loop only — no LangChain/LangGraph |
| Package manager | uv — no pip/venv |
| Storage | SQLite for state; configurable filesystem dir for materials |
| Budget | Must track and respect configurable token/API spend limits (Phase 1 builds this infrastructure) |
| No alternative CLI frameworks | Typer only (not Click, not argparse) |
| No alternative ORMs | SQLModel only (not raw SQLAlchemy, not Peewee) |
| No alternative LLM clients | LiteLLM (Phase 3 concern, but do not introduce alternatives in Phase 1) |

---

## Sources

### Primary (HIGH confidence)
- PyPI registry (2026-04-04) — all package versions verified: sqlmodel 0.0.34, alembic 1.16.5, pydantic 2.12.5, pydantic-settings 2.11.0, typer 0.23.2, rich 14.3.3, rapidfuzz 3.13.0, pytest 8.4.2, ruff 0.15.9, mypy 1.19.1, factory-boy 3.3.3, tomli 2.4.1, platformdirs 4.4.0
- `.planning/research/ARCHITECTURE.md` — component boundaries, data models, build order
- `.planning/research/PITFALLS.md` — domain pitfalls, dedup failures, budget overruns, schema migration debt
- `.planning/phases/01-foundation/01-CONTEXT.md` — locked implementation decisions D-01 through D-17
- `CLAUDE.md` — mandatory tech stack and constraint directives
- Environment probe (2026-04-04) — confirmed: sqlite3 3.51.0 available; uv NOT installed; Python 3.9.6 system Python; git 2.50.1

### Secondary (MEDIUM confidence)
- SQLModel + Alembic integration pattern: well-documented community pattern (training data, multiple sources agree on `SQLModel.metadata` as `target_metadata` in `env.py`)
- Alembic SQLite batch mode: SQLAlchemy/Alembic official documentation pattern for SQLite ALTER TABLE limitations

### Tertiary (LOW confidence)
- Pydantic v2 strict mode edge cases with SQLModel 0.0.34: based on training data community reports, not officially documented — flagged as Open Question 2

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified from PyPI registry on research date
- Architecture: HIGH — patterns drawn from ARCHITECTURE.md (pre-researched) and well-established SQLModel/Alembic community patterns
- Pitfalls: HIGH — Alembic/SQLite pitfalls well-documented; uv availability confirmed by environment probe

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable libraries; version pinning confirmed)
