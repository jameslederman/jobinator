# Phase 4: Materials Generation - Research

**Researched:** 2026-04-06
**Domain:** LLM generation (resume/cover letter/prep brief), Jinja2 HTML templating, WeasyPrint PDF rendering, human-in-the-loop CLI confirmation, versioned file output
**Confidence:** HIGH

## Summary

Phase 4 builds the `apply <job_id>` command, the most value-dense feature of Jobinator. For a scored job above threshold, the system generates three tailored documents — resume, cover letter, and interview prep brief — then renders them to PDF and saves them under a versioned directory. The human-in-the-loop confirmation requirement means NO file is written until the user explicitly confirms after seeing a preview.

The generation pipeline has three layers: (1) LLM generation using the strong model tier (claude-3-5-sonnet-latest or gpt-4o) via the existing `instructor.from_litellm()` + `create_with_completion()` pattern from Phase 3, (2) Jinja2 HTML templating to render structured output into printable HTML, and (3) WeasyPrint to convert HTML to PDF. The grounding/truthfulness constraint (MATL-02) is enforced at the prompt level: the system prompt explicitly restricts the LLM to facts extractable from the provided JSON Resume profile, and the Instructor response model is structured to carry only verifiable fields.

The output infrastructure (`OutputManager`, `make_role_slug`, `BUNDLE_FILES`) was built in Phase 1 as part of the foundation and is fully functional. The `MaterialsConfig` follows the same standalone `BaseModel` pattern as `ScoringConfig`, `DiscoveryConfig`, and `FilterConfig`. The `apply` command must gate on `budget_tracker.assert_within_limits()` before each LLM call, record three `SpendRecord` rows (one per generation call), and log the final apply/skip decision via `budget_tracker.log_decision()`.

**Primary recommendation:** Use `instructor.from_litellm()` + `create_with_completion()` for structured generation. Enforce grounding in system prompts. Render via Jinja2 -> WeasyPrint (installed via `brew install weasyprint`). Use `typer.confirm()` for the human-in-the-loop gate before writing any file.

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, SQLite + SQLModel, Typer CLI, JSON Resume format — no deviation
- **LLM providers**: LiteLLM multi-provider; strong model (`claude-3-5-sonnet-latest` / `gpt-4o`) for generation quality
- **Agent framework**: Custom loop — no LangChain, no LangGraph
- **Storage**: SQLite for state; configurable filesystem directory for generated materials
- **Budget**: Every LLM call gated by `BudgetTracker.assert_within_limits()` and recorded via `BudgetTracker.record()`
- **Package manager**: uv
- **Linting/formatting**: ruff
- **Type checking**: mypy
- **Pre-commit hooks**: ruff + mypy on commit
- **Test framework**: pytest; respx for HTTP mocks; factory-boy for fixtures

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MATL-01 | User can generate a tailored resume from JSON Resume base that emphasizes relevant experience per role | LLM generation with Instructor structured output; `ResumeContent` Pydantic model holds tailored sections; Jinja2 template renders to HTML; WeasyPrint to PDF |
| MATL-02 | Generated resumes are truthful — no hallucinated metrics, dates, or skills | System prompt explicitly binds LLM to provided JSON Resume data; Pydantic response model only accepts fields traceable to profile; post-generation traceback verification pattern |
| MATL-03 | User can generate a concise, company+role-specific cover letter per job | `CoverLetterContent` Pydantic model; dedicated generation call with job description + profile context; same Instructor + LiteLLM pattern |
| MATL-04 | User can generate an interview prep brief per job | `PrepBriefContent` Pydantic model; generation includes company overview, likely questions, talking points grounded in profile strengths/gaps from JobScore |
| MATL-05 | All generated materials are rendered to PDF | Jinja2 HTML template + WeasyPrint (installed via `brew install weasyprint`); three separate PDF files per bundle |
| MATL-06 | Materials are saved to configurable output directory organized by company/role with versioning | `OutputManager.create_application_dir()` already built in Phase 1; `latest` symlink already implemented; versioned timestamp dirs already work |
</phase_requirements>

## Standard Stack

### Core (new dependencies for Phase 4)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Jinja2 | 3.1.6 | HTML template rendering | Template-based HTML generation separates content (LLM output) from layout (CSS/HTML). Already pulled in as transitive dep (confirmed present in venv). Must be added to pyproject.toml explicitly. |
| WeasyPrint | 66.0 (PyPI) / 68.1 (brew) | HTML-to-PDF rendering | Pure Python PDF from CSS-styled HTML. No external binary needed if system deps (pango) are installed. Chosen in CLAUDE.md over LaTeX and wkhtmltopdf. Install via `brew install weasyprint` to get system deps automatically. |

### Already Installed (no new pip install needed)
| Library | Version | Purpose |
|---------|---------|---------|
| instructor | 1.15.1 | Structured LLM output via `create_with_completion()` — same pattern as scoring |
| litellm | 1.83.3 | Multi-provider LLM routing — same client pattern as scoring |
| pydantic | >=2.7 | `ResumeContent`, `CoverLetterContent`, `PrepBriefContent` response models |
| sqlmodel | >=0.0.21 | `GeneratedMaterial` SQLModel table (new) |
| typer + rich | >=0.12, >=13.7 | `apply` CLI command + `typer.confirm()` for HITL gate |
| jinja2 | 3.1.6 | Already in venv as transitive dep — must add to pyproject.toml |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| WeasyPrint | xhtml2pdf | xhtml2pdf is pure Python (no system deps) but CSS support is CSS 2.1 only — no flex/grid. WeasyPrint CSS support is significantly better. CLAUDE.md specifies WeasyPrint. |
| WeasyPrint | reportlab | reportlab requires manual layout positioning — very high effort for a resume. CLAUDE.md explicitly deprioritizes it. |
| WeasyPrint | LaTeX subprocess | 500MB system install; CLAUDE.md explicitly excludes it. |
| `instructor.from_litellm()` | Direct `litellm.completion()` | Without Instructor, manual JSON extraction from LLM responses is brittle; retry-on-validation-failure requires Instructor. Same pattern used in scoring. |
| Jinja2 templates | f-string generation | f-strings cannot produce CSS-styled, paginated, print-optimized HTML. Jinja2 separates layout from data. |

**Installation:**
```bash
brew install weasyprint   # installs weasyprint + system deps (pango, cffi, pillow)
uv add "jinja2>=3.1"     # Jinja2 already in venv; pin in pyproject.toml
uv add "weasyprint>=62"  # after brew install resolves system deps
```

**Version verification (confirmed 2026-04-06):**
- WeasyPrint PyPI: 66.0 (brew formula has 68.1 — brew install preferred)
- Jinja2: 3.1.6 (already in project venv as transitive dep)
- instructor: 1.15.1 (existing)
- litellm: 1.83.3 (existing)

## Architecture Patterns

### Recommended Project Structure (Phase 4 additions)
```
src/jobinator/
├── generation/
│   ├── __init__.py          # exports: MaterialsGenerator, GenerationConfig
│   ├── generator.py         # MaterialsGenerator — orchestrates LLM calls + PDF rendering
│   ├── prompts.py           # Prompt builders: resume, cover_letter, prep_brief
│   ├── renderer.py          # Jinja2 HTML render + WeasyPrint PDF conversion
│   └── models.py            # Pydantic response models: ResumeContent, CoverLetterContent, PrepBriefContent
├── templates/
│   ├── resume.html.jinja    # Resume HTML template
│   ├── cover_letter.html.jinja   # Cover letter HTML template
│   └── prep_brief.html.jinja    # Prep brief HTML template
├── models/
│   └── material.py          # NEW: GeneratedMaterial SQLModel table
├── configs/
│   └── settings.py          # (extend) add MaterialsConfig as standalone BaseModel
└── pipelines/
    └── apply.py             # NEW: apply pipeline orchestrator (mirrors score.py pattern)
```

### Pattern 1: Structured LLM Generation (mirrors scoring pattern)

**What:** Use `instructor.from_litellm(litellm.completion)` + `create_with_completion()` to produce typed Pydantic models from strong model, with cost extraction.
**When to use:** All three generation calls (resume, cover letter, prep brief).

```python
# Source: established in Phase 3 (src/jobinator/scoring/client.py)
import instructor
import litellm

_client = instructor.from_litellm(litellm.completion)

class ResumeContent(BaseModel):
    """Structured resume output — all fields must trace to profile data."""
    summary: str = Field(description="Tailored professional summary (2-3 sentences). Use ONLY facts from the provided profile.")
    relevant_experience: list[TailoredWorkEntry] = Field(description="Work entries from the profile, reordered/rephrased to emphasize job-relevant aspects. Do NOT add metrics or dates not in the profile.")
    highlighted_skills: list[str] = Field(description="Skills from profile.skills relevant to this job. Do NOT invent skills.")
    education: list[dict] = Field(description="Education entries verbatim from profile — no modification.")

content, raw = _client.create_with_completion(
    model=config.strong_model,
    messages=messages,
    response_model=ResumeContent,
    max_tokens=2048,
    max_retries=2,
)
cost = float(raw._hidden_params.get("response_cost", 0.0))
```

### Pattern 2: Grounding/Truthfulness Enforcement

**What:** The system prompt explicitly enumerates the constraints and includes the full profile as context. The Pydantic response model fields carry grounding instructions in their `description` strings — Instructor uses these as sub-prompts.
**When to use:** All generation calls, but especially the resume (MATL-02).

```python
# Source: training data + verified Instructor pattern
system_prompt = """You are generating tailored application materials for a job candidate.

CRITICAL TRUTHFULNESS RULES:
1. Every metric in the resume (numbers, percentages, dates) MUST appear verbatim in the provided profile.
2. Every skill listed MUST appear in the profile's skills section.
3. You may REPHRASE or EMPHASIZE profile content, but you may NOT INVENT content.
4. If the profile lacks information for a section, omit that section rather than fabricating.
5. The provided JSON Resume profile is the ONLY source of truth.

Below is the candidate's complete JSON Resume profile:
{profile_json}
"""
```

### Pattern 3: Jinja2 HTML Template + WeasyPrint PDF

**What:** Generate PDF in two steps: (1) render Pydantic model into HTML with Jinja2, (2) convert HTML to PDF with WeasyPrint.
**When to use:** For all three document types.

```python
# Source: WeasyPrint official docs + Jinja2 docs
from jinja2 import Environment, PackageLoader
from weasyprint import HTML

env = Environment(loader=PackageLoader("jobinator", "templates"))
template = env.get_template("resume.html.jinja")
html_content = template.render(
    basics=profile_data.get("basics", {}),
    experience=content.relevant_experience,
    skills=content.highlighted_skills,
    job_title=job.title,
    company=job.company,
)
pdf_bytes = HTML(string=html_content).write_pdf()
output_path.write_bytes(pdf_bytes)
```

### Pattern 4: Human-in-the-Loop Confirmation Gate

**What:** `typer.confirm()` with a Rich preview table. No file is written until the user explicitly confirms. This is the key MATL-02 safety gate.
**When to use:** Between LLM generation and file writing.

```python
# Source: Typer docs — typer.confirm() raises typer.Abort() on "n"
from rich.panel import Panel

# Show preview summaries (not full content — just enough to review)
console.print(Panel(content.summary, title="Resume Summary Preview", expand=False))
console.print(f"\n[bold]Cover letter:[/bold] {cover.opening_line[:100]}...")
console.print(f"\n[bold]Prep brief:[/bold] {len(prep.likely_questions)} questions generated")

typer.confirm(
    "\nWrite these files to disk?",
    abort=True,  # raises typer.Abort if user says n
)
# Only reaches here if user confirmed
_write_bundle(app_dir, ...)
```

### Pattern 5: MaterialsConfig (standalone BaseModel)

**What:** `MaterialsConfig` as a standalone Pydantic `BaseModel` (not a `Settings` subclass), loaded from `[materials]` section of config.toml. Consistent with `ScoringConfig`, `DiscoveryConfig`, `FilterConfig`.
**When to use:** All config access in the materials pipeline.

```python
# Source: established Phase 1-3 pattern (src/jobinator/configs/settings.py)
class MaterialsConfig(BaseModel):
    strong_model: str = Field(default="claude-3-5-sonnet-latest")
    apply_threshold: float = Field(default=0.6, description="Minimum fit_score to allow apply")
    profile_path: Optional[str] = Field(default=None)
    output_dir: str = Field(default="~/jobinator-output")
```

### Pattern 6: GeneratedMaterial DB Record

**What:** A new `GeneratedMaterial` SQLModel table tracks which bundles have been generated for which jobs — prevents silent data loss, enables status tracking, and is FK'd to `NormalizedJob`.
**When to use:** After successful bundle write.

```python
class GeneratedMaterial(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = Field(foreign_key="normalizedjob.id", index=True)
    bundle_path: str  # absolute path to versioned dir
    model_used: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed: bool = Field(default=True)  # always True — only written after confirm
```

### Anti-Patterns to Avoid

- **Writing files before confirmation:** The requirement is explicit — no file written until user explicitly confirms. All LLM calls complete first, the preview is shown, then `typer.confirm()` gates file writing.
- **Overwriting previous bundles:** Each `apply` run must call `OutputManager.create_application_dir()` which creates a new timestamped dir — never pass an existing dir.
- **Mutable strong_model at module level:** The Phase 3 pattern puts `_client = instructor.from_litellm(litellm.completion)` at module level. For generation, the strong model string should be passed at call time via `create_with_completion(model=config.strong_model, ...)` — not baked into a class at construction time.
- **Truncating profile context:** Unlike scoring (which truncated profile to key fields), generation needs the FULL profile JSON as context because MATL-02 requires every output to be verifiable against it.
- **Monolithic generator function:** Three separate generation functions (resume, cover_letter, prep_brief) — each with its own budget gate, spend record, and error isolation — is cleaner than one function that does all three. A failure generating the prep brief should not discard an already-generated resume.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML-to-PDF rendering | Custom PDF layout with reportlab | WeasyPrint | reportlab requires manual page positioning — enormous complexity for resume layouts |
| Template rendering | f-string template engine | Jinja2 | Jinja2 handles loops, conditionals, escaping, and CSS-safe output out of the box |
| Structured LLM output | Manual JSON parsing + retry loop | Instructor + LiteLLM | Instructor handles validation failure, retry, and schema enforcement — battle-tested |
| CLI confirmation | `input("y/n?")` | `typer.confirm(abort=True)` | typer.confirm raises `typer.Abort` cleanly; handles Ctrl-C; integrates with Rich |
| File versioning | Custom timestamp logic | `OutputManager.create_application_dir()` | Already built in Phase 1; handles `latest` symlink; uses ISO timestamp format |
| Cost tracking | `litellm.completion_cost()` | `raw._hidden_params["response_cost"]` | `completion_cost()` returns 0.0 via Instructor wrapper (known bug, documented in Phase 3) |

**Key insight:** All the hard infrastructure problems are already solved in Phases 1-3. Phase 4 assembles them.

## Common Pitfalls

### Pitfall 1: WeasyPrint System Dependencies Not Installed
**What goes wrong:** `uv add weasyprint` succeeds but `import weasyprint` raises `OSError: no library called "pango-1.0" was found` at runtime.
**Why it happens:** WeasyPrint is not pure Python — it requires Pango (and its deps: cairo, glib, fontconfig) as system libraries. These are not installed on this machine (confirmed: brew list shows no cairo/pango).
**How to avoid:** Install via `brew install weasyprint` first. This installs WeasyPrint 68.1 with all system deps via brew bottles. Then `uv add "weasyprint>=62"` for the Python package. Verify with `python -c "from weasyprint import HTML; HTML(string='<p>test</p>').write_pdf()"`.
**Warning signs:** ImportError or OSError at WeasyPrint import time.

### Pitfall 2: LLM Hallucination in Resume (MATL-02 Violation)
**What goes wrong:** LLM invents metrics ("increased revenue by 40%"), skills, or dates not present in the JSON Resume profile.
**Why it happens:** Strong models have strong priors about resume writing and will embellish unless explicitly constrained.
**How to avoid:** (1) Include the FULL profile JSON verbatim in the system prompt as the "only source of truth." (2) Instruction-tune the Pydantic field descriptions to say "must trace to profile." (3) Post-generation: a lightweight verification pass that checks generated text against profile text (fuzzy match key metrics/dates).
**Warning signs:** Numbers in generated resume that don't appear in profile data.

### Pitfall 3: generate_resume / generate_cover_letter / generate_prep_brief Budget Gates
**What goes wrong:** All three LLM calls consume budget but only the first call checks `assert_within_limits()`.
**Why it happens:** Easy to add budget gate only at the `apply` pipeline entry point rather than before each individual LLM call.
**How to avoid:** Each of the three generation functions must call `budget_tracker.assert_within_limits(job_id=job.id)` before its own LLM call. The apply pipeline starts with a gate, then each sub-call gates again — matching the scoring pattern where the gate is in `scorer.score_job()` not only in `run_scoring()`.
**Warning signs:** Three LLM calls with only one SpendRecord; budget overrun possible.

### Pitfall 4: Writing Files Before Confirmation
**What goes wrong:** Files appear on disk even when user declines.
**Why it happens:** OutputManager creates the directory in `create_application_dir()` — if called before confirmation, the empty directory persists even on decline.
**How to avoid:** Call `create_application_dir()` AFTER `typer.confirm()` confirms. Do all LLM generation in-memory first; only hit the filesystem after confirmation.
**Warning signs:** Empty timestamped directories in output dir.

### Pitfall 5: Jinja2 PackageLoader Path Resolution
**What goes wrong:** `PackageLoader("jobinator", "templates")` fails because templates directory isn't included in the installed package.
**Why it happens:** Hatchling build backend only includes Python files by default. Templates (`.html.jinja`) must be explicitly included.
**How to avoid:** Add `[tool.hatch.build.targets.wheel]` include pattern for `src/jobinator/templates/**`. Or use `FileSystemLoader` with `Path(__file__).parent / "templates"` for simpler local dev. `FileSystemLoader` is more robust for a non-distributed tool.
**Warning signs:** `TemplateNotFound` error at runtime.

### Pitfall 6: Alembic Migration for GeneratedMaterial Table
**What goes wrong:** Alembic autogenerate doesn't pick up the new table because `GeneratedMaterial` wasn't imported in the migration env.
**Why it happens:** Alembic only generates migrations for models registered in `SQLModel.metadata`, which requires importing the model class. The `alembic/env.py` must import all models.
**How to avoid:** Add `from jobinator.models.material import GeneratedMaterial` to `alembic/env.py` target metadata setup. Then `alembic revision --autogenerate -m "add_generated_material_table"`. Pattern established in Phase 3 (import sqlmodel in migration files).
**Warning signs:** Alembic autogenerate shows empty migration; GeneratedMaterial table absent at runtime.

### Pitfall 7: Preview Before Confirmation — Show Enough But Not Too Much
**What goes wrong:** Either (a) showing the full 2-page resume in the terminal overwhelming the user, or (b) showing so little the user can't make an informed decision.
**Why it happens:** No prior pattern for "preview" in the codebase.
**How to avoid:** Show: resume summary paragraph + word count, cover letter first two sentences, prep brief as bulleted list count ("8 likely questions identified"). Use Rich `Panel` with `expand=False`. Include file paths where output will be written. Then `typer.confirm()`.
**Warning signs:** User immediately confirms without reading — UX failure if preview is useless.

## Code Examples

Verified patterns from existing codebase and official sources:

### LLM Generation Call (extends Phase 3 pattern)
```python
# Source: src/jobinator/scoring/client.py (Phase 3, verified working)
import instructor
import litellm
from pydantic import BaseModel, Field

_client = instructor.from_litellm(litellm.completion)

content, raw = _client.create_with_completion(
    model="claude-3-5-sonnet-latest",  # strong model for generation
    messages=messages,
    response_model=ResumeContent,
    max_tokens=2048,
    max_retries=2,
)
cost = float(raw._hidden_params.get("response_cost", 0.0))
input_tokens = raw.usage.prompt_tokens
output_tokens = raw.usage.completion_tokens
```

### WeasyPrint HTML-to-PDF
```python
# Source: WeasyPrint official docs (https://doc.courtbouillon.org/weasyprint/stable/)
from weasyprint import HTML

pdf_bytes = HTML(string=html_content).write_pdf()
output_path.write_bytes(pdf_bytes)
```

### Jinja2 Template Rendering (FileSystemLoader for local tool)
```python
# Source: Jinja2 docs (https://jinja.palletsprojects.com/en/3.1.x/api/)
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

templates_dir = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
template = env.get_template("resume.html.jinja")
html_content = template.render(
    basics=profile_data["basics"],
    experience=content.relevant_experience,
    skills=content.highlighted_skills,
    job_title=job.title,
    company=job.company,
)
```

### Typer Confirmation Gate
```python
# Source: Typer docs (https://typer.tiangolo.com/tutorial/prompt/)
import typer
from rich.panel import Panel

# Show preview
console.print(Panel(content.summary[:200], title="[bold]Resume Summary[/bold]", expand=False))
console.print(f"Cover letter: {cover.opening[:100]}...")

# Gate — raises typer.Abort on "n", proceeds on "y"
typer.confirm("Write files to disk?", abort=True)
```

### Budget Gate Per Call (mirrors scorer pattern)
```python
# Source: src/jobinator/scoring/scorer.py (Phase 3, verified working)
# Gate before each LLM call, not only at pipeline entry
self.budget_tracker.assert_within_limits(job_id=job.id)
content, raw = _client.create_with_completion(...)
spend = SpendRecord(
    job_id=job.id,
    model_name=config.strong_model,
    provider=_provider_from_model(config.strong_model),
    operation="generate_resume",   # or "generate_cover_letter", "generate_prep_brief"
    input_tokens=raw.usage.prompt_tokens,
    output_tokens=raw.usage.completion_tokens,
    cost_usd=float(raw._hidden_params.get("response_cost", 0.0)),
)
self.budget_tracker.record(spend)
```

### Markdown Fallback Alongside PDF
```python
# Source: output manager pattern — write .md alongside .pdf
# BUNDLE_FILES already includes both resume.md and resume.pdf
(app_dir / "resume.md").write_text(content.to_markdown())
(app_dir / "cover_letter.md").write_text(cover.to_markdown())
(app_dir / "prep_brief.md").write_text(prep.to_markdown())
# PDFs generated from same content via Jinja2 + WeasyPrint
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| wkhtmltopdf external binary | WeasyPrint pure Python (+ system libs) | 2019-2022 | No external binary download; managed via brew |
| Manual JSON parsing of LLM output | Instructor structured output with retry | 2023+ | Eliminates fragile string parsing |
| `litellm.completion_cost()` | `raw._hidden_params["response_cost"]` | instructor#1330 (ongoing) | Prevents silent 0.0 cost recording via Instructor wrapper |

**Deprecated/outdated:**
- `litellm.completion_cost(response)`: Returns 0.0 when called via Instructor wrapper — use `_hidden_params["response_cost"]` (documented Phase 3 decision).

## Open Questions

1. **WeasyPrint CSS template quality**
   - What we know: WeasyPrint supports CSS paged media; unknown how much work is needed to produce a visually acceptable resume.
   - What's unclear: Whether default HTML/CSS templates will produce output the user is willing to submit, or if significant CSS iteration is needed.
   - Recommendation: Wave 0 task — render a sample PDF from the fixture profile immediately before building generation logic. If output is unacceptable, fall back to xhtml2pdf for simpler CSS.

2. **Rich terminal preview format**
   - What we know: `typer.confirm()` works; Rich `Panel` can display text.
   - What's unclear: Whether showing only summary/first-line is enough to make an informed confirmation, or whether a temp file preview (e.g., open PDF in browser) would be more useful.
   - Recommendation: Start with text summary preview (always works); document the design in comments. Full PDF preview is v2 scope.

3. **Per-material vs per-bundle budget gate**
   - What we know: Three LLM calls per apply run; strong model is ~10x more expensive than haiku.
   - What's unclear: Should apply be gated by a single per-bundle budget limit, or the existing per-job limit applies?
   - Recommendation: Reuse `per_job_limit_usd` from BudgetConfig; it applies per-job, not per-call, so three calls share the same job limit. No new config needed.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All | Yes | 3.12.x | — |
| Jinja2 | Template rendering | Yes (transitive dep) | 3.1.6 | — |
| WeasyPrint (Python pkg) | PDF rendering | No | — | `uv add weasyprint>=62` after brew |
| pango (system lib) | WeasyPrint | No | — | `brew install weasyprint` installs it |
| cffi (system/Python) | WeasyPrint | Unknown | — | Installed as part of WeasyPrint |
| instructor | Structured generation | Yes | 1.15.1 | — |
| litellm | LLM routing | Yes | 1.83.3 | — |
| ANTHROPIC_API_KEY or OPENAI_API_KEY | LLM calls | Assumed present (required by score) | — | User sets in .env |

**Missing dependencies with no fallback:**
- WeasyPrint + pango: blocks PDF generation. Must run `brew install weasyprint` before `uv add weasyprint>=62`.

**Missing dependencies with fallback:**
- None beyond WeasyPrint.

**Pre-task verification command** (Wave 0 test to gate the rest of Phase 4):
```bash
brew install weasyprint && uv add "jinja2>=3.1" "weasyprint>=62"
python -c "from weasyprint import HTML; HTML(string='<html><body><h1>Test</h1></body></html>').write_pdf('/tmp/wp_test.pdf'); print('WeasyPrint OK')"
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.2+ |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options] testpaths = ["tests"]` |
| Quick run command | `uv run pytest tests/test_generation.py tests/test_apply_cli.py tests/test_renderer.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MATL-01 | Resume generation returns structured `ResumeContent` with profile-grounded fields | unit | `pytest tests/test_generation.py::test_generate_resume_returns_structured_content -x` | Wave 0 |
| MATL-02 | Generated resume fields are verifiably traceable to profile data (no hallucinated metrics) | unit | `pytest tests/test_generation.py::test_resume_grounding_no_invented_content -x` | Wave 0 |
| MATL-03 | Cover letter generation returns `CoverLetterContent` scoped to company/role | unit | `pytest tests/test_generation.py::test_generate_cover_letter -x` | Wave 0 |
| MATL-04 | Prep brief generation returns `PrepBriefContent` with questions and talking points | unit | `pytest tests/test_generation.py::test_generate_prep_brief -x` | Wave 0 |
| MATL-05 | PDF bytes are non-empty and begin with `%PDF` magic bytes | unit | `pytest tests/test_renderer.py::test_render_pdf_produces_valid_bytes -x` | Wave 0 |
| MATL-06 | Re-running apply creates new versioned dir; previous dir intact | unit | `pytest tests/test_output.py::test_latest_symlink_updated -x` | Already exists |
| (HITL) | `apply` command shows preview and writes no files if user declines | unit | `pytest tests/test_apply_cli.py::test_apply_aborts_if_user_declines -x` | Wave 0 |
| (budget) | Budget gate fires before each of three generation calls | unit | `pytest tests/test_generation.py::test_budget_gated_before_each_call -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_generation.py tests/test_renderer.py tests/test_apply_cli.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q` (full suite — must stay green; current baseline: 185 passed)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_generation.py` — covers MATL-01, MATL-02, MATL-03, MATL-04, budget gating
- [ ] `tests/test_renderer.py` — covers MATL-05 (Jinja2 render + WeasyPrint PDF bytes)
- [ ] `tests/test_apply_cli.py` — covers HITL confirmation gate, typer.Abort on decline
- [ ] `src/jobinator/generation/__init__.py` — new module
- [ ] `src/jobinator/models/material.py` — GeneratedMaterial SQLModel table
- [ ] `alembic/versions/add_generated_material_table.py` — migration

*(Note: `tests/test_output.py` already covers MATL-06 versioning — no gap for that requirement.)*

## Sources

### Primary (HIGH confidence)
- Phase 3 codebase (`src/jobinator/scoring/client.py`, `scorer.py`, `pipelines/score.py`) — Instructor + LiteLLM + budget pattern verified working, 185 tests passing
- Phase 1 codebase (`src/jobinator/output/manager.py`, `tests/test_output.py`) — OutputManager fully built and tested
- WeasyPrint official docs (https://doc.courtbouillon.org/weasyprint/stable/) — confirmed system dep requirements
- Jinja2 official docs (https://jinja.palletsprojects.com/en/3.1.x/) — FileSystemLoader pattern
- Typer docs (https://typer.tiangolo.com/tutorial/prompt/) — `typer.confirm(abort=True)` pattern

### Secondary (MEDIUM confidence)
- PyPI WeasyPrint 66.0 (https://pypi.org/project/weasyprint/) — version confirmed
- Brew formula weasyprint 68.1 — confirmed via `brew info weasyprint`
- WebSearch: xhtml2pdf 0.2.17 as pure-Python fallback — verified no system deps

### Tertiary (LOW confidence)
- WebSearch: CSS quality comparison WeasyPrint vs xhtml2pdf — community reports, not officially benchmarked

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified against PyPI; Jinja2 confirmed in venv; WeasyPrint brew path confirmed
- Architecture: HIGH — all patterns are direct extensions of working Phase 3 code; no new paradigms
- Pitfalls: HIGH — WeasyPrint system dep issue confirmed empirically (brew list showed no pango); hallucination pitfall is fundamental LLM behavior; others drawn from Phase 3 decisions log
- Environment: HIGH — availability confirmed via direct `brew info` and `import` checks

**Research date:** 2026-04-06
**Valid until:** 2026-07-06 (90 days — stable libraries; WeasyPrint PyPI version may update but brew install path remains valid)
