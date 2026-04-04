# Technology Stack

**Project:** Jobinator — Local-first job search automation pipeline
**Researched:** 2026-04-04
**Knowledge cutoff:** August 2025 (versions marked LOW confidence — verify with `pip index versions <pkg>`)

---

## Recommended Stack

### CLI Interface

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Typer | >=0.12 | CLI framework | Built on Click, adds type annotation-based command definition, auto-generated help text, shell completion. Less boilerplate than raw Click. Native Pydantic v2 compatibility. Single-user developer tool — no need for Click's lower-level control. |
| Rich | >=13.7 | Terminal output formatting | Typer integrates directly with Rich for styled output, progress bars, and tables. Turns scoring output and material listings into readable summaries without extra work. |

**Why Typer over Click:** PROJECT.md explicitly lists both as options. Typer is Click underneath — you get all Click's power with less ceremony. For a tool where command signatures change frequently during development, type-hint-driven argument parsing reduces friction. Click is still appropriate if you need plugin architecture (Click's group/decorator model is more composable for that pattern), but Jobinator's command surface is fixed and small.

**Why not argparse:** No auto-help generation, no subcommand composition, significantly more verbose.

---

### Database / ORM

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLModel | >=0.0.21 | ORM + schema definition | Timon Wetenschapper (FastAPI author) project: SQLAlchemy under the hood + Pydantic v2 validation in one class definition. Single model class doubles as database schema and data validator — critical when the same Job object flows through scraping, scoring, and storage without re-serialization. |
| SQLite (stdlib) | 3.x (bundled) | Storage engine | Zero-config, file-based, local-first. Sufficient for single-user job tracking at any realistic volume (thousands of jobs, not millions). |
| Alembic | >=1.13 | Schema migrations | Schema will evolve as requirements validate. Raw SQLite DDL edits are error-prone; Alembic generates versioned migration scripts. SQLModel doesn't handle migrations itself — Alembic fills that gap. |

**Why SQLModel over raw SQLAlchemy:** SQLAlchemy Core is lower-level and requires separate Pydantic models for validation, creating a translation layer. SQLModel eliminates that layer. The tradeoff is SQLModel is less mature and has had historically slow releases — but it's now on v2 Pydantic and stable enough for a single-user tool.

**Why SQLModel over Peewee/Tortoise/SQLObject:** Pydantic integration is the deciding factor. Job data flows from HTTP responses → Pydantic validation → storage → LLM input → output. SQLModel keeps this chain type-safe without adapters.

**Why not PostgreSQL:** Local-first constraint. SQLite is the right default; migration to Postgres is trivial with SQLAlchemy-backed SQLModel if ever needed.

---

### LLM Integration (Multi-Provider)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LiteLLM | >=1.40 | Unified LLM API client | Single interface for Anthropic, OpenAI, Google, Groq, and 100+ providers. Handles authentication, retry logic, and response normalization. Critical for the multi-tier model strategy (cheap models for filtering, strong models for generation). |
| anthropic | >=0.28 | Direct Anthropic SDK | Fallback for Claude-specific features (extended thinking, vision) that LiteLLM may not expose. Keep pinned alongside LiteLLM. |
| openai | >=1.30 | Direct OpenAI SDK | Same — fallback for OpenAI-specific features. LiteLLM uses this under the hood for OpenAI calls. |
| tiktoken | >=0.7 | Token counting | Pre-flight token estimation before API calls. Essential for budget enforcement — count tokens before you spend them. |

**Why LiteLLM over calling providers directly:** Budget tracking across providers is the core rationale. LiteLLM has built-in `completion_cost()` that returns USD cost per call across providers using current pricing tables it ships with. Building this from scratch (per-model token pricing tables, keep them current) is a maintenance burden. LiteLLM handles it.

**Why not LangChain:** PROJECT.md explicitly excludes it. Justified: LangChain adds abstraction layers that obscure what's happening during debugging, has large transitive dependencies, and the agent abstractions don't match the custom loop design. For a system where you need precise control over when and why each LLM call happens (budget enforcement, decision logging), LangChain's chains are the wrong primitive.

**Why not a single provider:** Multi-provider is load-bearing for budget awareness. GPT-4o-mini and Haiku are 10-20x cheaper than GPT-4o/Claude 3.5 Sonnet. Filtering 100 jobs with a strong model is prohibitively expensive; filtering with a cheap model then generating materials for 5 finalists with a strong model is affordable.

**Model strategy (LOW confidence — pricing changes frequently):**
- Hard filter pass: rule-based only (no LLM cost)
- Soft scoring pass: `claude-haiku-3` or `gpt-4o-mini` — cheap, fast, good enough for binary fit signals
- Material generation: `claude-3-5-sonnet-latest` or `gpt-4o` — quality-critical, fewer calls

---

### Structured Data Extraction

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Pydantic | >=2.7 | Structured LLM output validation | Instructor and direct JSON mode both produce dicts — Pydantic validates and coerces them into typed models. Foundation of SQLModel. Use Pydantic models as the canonical schema for all structured data in the pipeline. |
| Instructor | >=1.4 | LLM structured output | Wraps LiteLLM/OpenAI clients to enforce Pydantic model output from LLM calls. Handles retry-on-validation-failure automatically. Eliminates manual JSON parsing of LLM responses. |

**Why Instructor over manual JSON parsing:** LLMs produce malformed JSON. Instructor handles retry logic and partial repair automatically. It integrates with LiteLLM's client, so the multi-provider setup still works.

**Why Instructor over function calling directly:** Instructor is provider-agnostic — it uses the provider's native structured output mechanism (function calling, JSON mode, or constrained decoding) transparently. You write one Pydantic model, it works across Anthropic and OpenAI.

---

### Job Discovery / Scraping

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx | >=0.27 | HTTP client | Async-capable, clean API, better timeout handling than requests. Supports both sync and async usage — start sync, migrate to async if throughput requires it. |
| BeautifulSoup4 | >=4.12 | HTML parsing | Standard HTML parsing for pages without APIs. Pair with lxml for speed. |
| lxml | >=5.2 | HTML/XML parser backend | Faster parser for BeautifulSoup. Required for robustness with malformed HTML. |
| python-dateutil | >=2.9 | Date parsing | Job boards use inconsistent date formats. dateutil handles all common variants. |
| tenacity | >=8.3 | Retry logic | Exponential backoff for rate-limited scrapers. Composable decorators — `@retry(wait=wait_exponential(...), stop=stop_after_attempt(3))`. |

**Source-specific notes:**

- **Greenhouse:** Public JSON API — `https://boards-api.greenhouse.io/v1/boards/{company}/jobs`. No auth. Best source for structured data. Use httpx directly.
- **Lever:** Public JSON API — `https://api.lever.co/v0/postings/{company}`. No auth. Similar to Greenhouse.
- **Wellfound (AngelList Talent):** No official public API. Requires scraping or unofficial endpoints. Treat as LOW confidence — the scraping approach may break. Worth building but flag as fragile.
- **HN Who's Hiring:** Monthly thread parsing. Use Algolia HN Search API (`https://hn.algolia.com/api/v1/search`) to find posts, then parse thread structure. Reliable; HN doesn't block scrapers.
- **LinkedIn:** Out of scope per PROJECT.md. Correct decision — ToS enforcement and bot detection make this a support burden.

**Why httpx over requests:** requests is synchronous-only. httpx supports both. For initial MVP, sync is fine; for future parallel scraping of multiple boards, async is the path. Switching later is a one-line change if you build with httpx's interface.

**Why not Scrapy:** Overkill for this use case. Scrapy's spider/item pipeline architecture solves problems (crawling at scale, distributed scraping, item pipelines) that don't exist in a single-user local tool. httpx + BeautifulSoup is less infrastructure.

**Why not Playwright/Selenium:** Browser automation is expensive (memory, CPU, setup) and brittle. The sources with value (Greenhouse, Lever, HN) have JSON APIs or scrapeable HTML. Reserve browser automation for a later phase if specific high-value sources require it.

---

### Resume Generation (JSON Resume + PDF)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| jsonresume-python (or custom) | N/A | JSON Resume schema validation | JSON Resume is a community schema standard (`jsonresume.org/schema`). There's no canonical Python library — validate against the schema directly with Pydantic models mirroring the spec. |
| Jinja2 | >=3.1 | Resume/cover letter templating | Template resume sections into LaTeX, HTML, or Markdown. Separates content (JSON Resume data) from presentation. Multiple output formats from one template engine. |
| WeasyPrint | >=62 | HTML-to-PDF rendering | Pure Python, no external binary dependency (unlike wkhtmltopdf). Produces high-quality PDF from CSS-styled HTML. The most maintainable pure-Python path: JSON Resume → Jinja2 HTML → WeasyPrint PDF. |

**Alternative PDF path (if WeasyPrint has CSS limitations):**

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| reportlab | >=4.2 | Programmatic PDF generation | Full control over layout but requires manual positioning — high effort for complex resume layouts. Use only if WeasyPrint output quality is insufficient. |
| latex (subprocess) | system | LaTeX PDF compilation | Produces the best-looking output but requires LaTeX installation (large system dependency, 500MB+). Not appropriate for a local-first tool meant to run without system dependencies. Exclude unless user explicitly wants it. |

**Recommendation:** WeasyPrint is the right default. If the user needs LaTeX-quality output, add it as an opt-in rendering backend later.

**Why not python-docx:** Word documents are not the output format — PDFs are. Docx generation is a secondary feature; if needed, add python-docx later for a docx export command.

---

### Configuration and Profile Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-dotenv | >=1.0 | API key management | Load API keys from `.env` without polluting shell environment. Standard pattern for local-first developer tools. |
| Pydantic Settings (pydantic-settings) | >=2.3 | Typed config loading | Load and validate config from `.env` + YAML/TOML files with Pydantic models. Type-safe access to budget limits, model preferences, output paths. Eliminates raw `os.environ.get()` calls with no validation. |
| PyYAML | >=6.0 | YAML config files | User-facing config (job filters, target companies, salary floors) is more readable as YAML than TOML or JSON. PyYAML is the standard; use `yaml.safe_load()` only. |
| platformdirs | >=4.2 | XDG-compliant config paths | Resolves `~/.config/jobinator/` on Mac/Linux correctly. Better than hardcoding `~/.jobinator/` — respects OS conventions. |

---

### Token Budget Tracking

No dedicated library needed. Build a lightweight `BudgetTracker` class using:

- `LiteLLM.completion_cost()` — returns USD cost per completion call
- `tiktoken` — pre-flight token counting for prompts before calling
- SQLite table (`api_spend`) — persist daily spend across sessions
- Pydantic model — typed budget configuration (daily limit, per-job limit, model overrides)

**Why not a dedicated library:** No library exists that precisely matches this use case (multi-provider, per-job + daily limits, SQLite-backed). The implementation is ~100 lines. Keep it in-tree.

---

### Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | >=8.2 | Test framework | Standard. No alternative worth considering. |
| pytest-httpx | >=0.30 | Mock httpx calls | Mock job board responses without hitting live endpoints. Essential for scraper tests. |
| respx | >=0.21 | httpx mock router | Alternative to pytest-httpx with more routing control. Pick one — respx is more flexible for varied URL patterns. |
| factory-boy | >=3.3 | Test fixtures | Generate realistic Job, Profile, Score Pydantic models for tests without brittle hardcoded dicts. |

---

### Development Tooling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | >=0.4 | Package manager + venv | Replaces pip + venv. 10-100x faster installs, lockfile support, deterministic environments. Now the standard for new Python projects in 2025. |
| ruff | >=0.5 | Linting + formatting | Replaces flake8, black, isort. Single tool, extremely fast. |
| mypy | >=1.10 | Static type checking | Pydantic + SQLModel are only as valuable as the types they enforce. mypy catches mismatches at dev time, not runtime. |
| pre-commit | >=3.7 | Git hook automation | Run ruff + mypy on commit. Keeps the codebase clean without manual invocation. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| CLI | Typer | Click | Typer is Click with less boilerplate. No reason to use Click raw unless you need plugin architecture. |
| ORM | SQLModel | raw SQLAlchemy | SQLAlchemy requires separate Pydantic models, doubling schema maintenance. |
| ORM | SQLModel | Peewee | Peewee has no Pydantic integration; adds a data translation layer. |
| LLM client | LiteLLM | Direct provider SDKs | Would require maintaining per-provider cost tables and normalization logic in-tree. |
| LLM framework | (none) | LangChain | Explicitly excluded in PROJECT.md. Justified: abstractions hide budget/call decisions. |
| Structured output | Instructor | Manual JSON parsing | LLMs produce malformed JSON; retry logic is non-trivial to build correctly. |
| PDF | WeasyPrint | wkhtmltopdf | wkhtmltopdf is a large external binary; WeasyPrint is pure Python. |
| PDF | WeasyPrint | LaTeX subprocess | LaTeX requires a 500MB system installation; unjustified for local dev tool. |
| HTTP client | httpx | requests | requests is sync-only; httpx supports async for future parallelization with no API change. |
| Scraping | httpx + BS4 | Scrapy | Scrapy solves at-scale crawling problems that don't apply to a single-user tool. |
| Config | pydantic-settings | dynaconf | pydantic-settings integrates directly with Pydantic v2; no extra dependency. |
| Package mgr | uv | pip + venv | uv is 10-100x faster and produces lockfiles; the ecosystem standard as of 2025. |

---

## Installation

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
uv init jobinator
cd jobinator

# Core runtime dependencies
uv add \
  typer \
  rich \
  sqlmodel \
  alembic \
  litellm \
  anthropic \
  openai \
  instructor \
  tiktoken \
  httpx \
  beautifulsoup4 \
  lxml \
  python-dateutil \
  tenacity \
  jinja2 \
  weasyprint \
  pydantic-settings \
  python-dotenv \
  pyyaml \
  platformdirs

# Dev dependencies
uv add --dev \
  pytest \
  respx \
  factory-boy \
  mypy \
  ruff \
  pre-commit
```

---

## Confidence Assessment

| Component | Confidence | Reason |
|-----------|------------|--------|
| Typer + Rich | HIGH | Stable, widely adopted, training data well-corroborated |
| SQLModel + Alembic | MEDIUM | SQLModel had slow release cadence historically; verify current version and Pydantic v2 compat |
| LiteLLM | MEDIUM | Rapidly evolving library; API surface changes frequently. Verify `completion_cost()` still accurate for all target providers |
| Instructor | MEDIUM | Growing fast; verify version pinning approach given rapid releases |
| httpx + BS4 | HIGH | Stable, well-established |
| WeasyPrint | MEDIUM | CSS support has gaps; verify rendered output quality with a test resume before committing |
| Greenhouse/Lever APIs | MEDIUM | Unofficial public APIs; no guarantee of stability. Verify endpoints are still live |
| Wellfound scraping | LOW | No public API; scraping approach may break on layout changes or bot detection |
| HN Algolia API | HIGH | Algolia provides this officially for HN; stable and well-documented |
| uv | HIGH | Now the established standard for Python packaging as of 2025 |
| Pydantic v2 | HIGH | Stable, widely adopted |
| LiteLLM cost tracking | LOW | Pricing tables are shipped with LiteLLM and may lag provider changes; always validate costs against provider invoices |

---

## Version Verification

All versions listed are approximate based on knowledge cutoff August 2025. Verify current versions before pinning:

```bash
# Check latest versions
pip index versions sqlmodel
pip index versions litellm
pip index versions instructor
pip index versions weasyprint
pip index versions typer
```

Or via PyPI:
- https://pypi.org/project/sqlmodel/
- https://pypi.org/project/litellm/
- https://pypi.org/project/instructor/
- https://pypi.org/project/weasyprint/
- https://pypi.org/project/typer/

---

## Sources

- SQLModel documentation: https://sqlmodel.tiangolo.com/ (training data, MEDIUM confidence)
- LiteLLM documentation: https://docs.litellm.ai/ (training data, MEDIUM confidence)
- Instructor documentation: https://python.useinstructor.com/ (training data, MEDIUM confidence)
- Greenhouse Jobs API: https://developers.greenhouse.io/job-board.html (training data, MEDIUM confidence)
- Lever Postings API: https://hire.lever.co/developer/postings (training data, MEDIUM confidence)
- HN Algolia API: https://hn.algolia.com/api (training data, HIGH confidence — long-stable)
- JSON Resume schema: https://jsonresume.org/schema/ (training data, HIGH confidence)
- WeasyPrint docs: https://doc.courtbouillon.org/weasyprint/ (training data, MEDIUM confidence)
- uv documentation: https://docs.astral.sh/uv/ (training data, HIGH confidence)
- pydantic-settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/ (training data, HIGH confidence)

**Note:** Web access was unavailable during this research session. All version numbers and API endpoints should be verified against live sources before use.
