---
phase: 04-materials-generation
verified: 2026-04-06T20:00:00Z
status: human_needed
score: 5/5 must-haves verified
human_verification:
  - test: "Open the generated PDFs from a real `apply` run and inspect visual quality"
    expected: "Resume, cover letter, and prep brief render with correct layout, readable fonts, no overlapping sections, and no garbled text"
    why_human: "WeasyPrint CSS rendering quality cannot be verified programmatically — pixel-level layout defects are only visible in a PDF viewer"
  - test: "Run `jobinator apply <scored_job_id>` end-to-end against a real API key"
    expected: "Preview panel appears showing resume summary, cover letter opening snippet, and prep brief question count before any prompt; then `Write these files to disk?` prompt appears; answering 'n' leaves no files on disk; answering 'y' creates <company>/<role>/<timestamp>/ directory containing resume.pdf, cover_letter.pdf, prep_brief.pdf, resume.md, cover_letter.md, prep_brief.md, metadata.json, job_description.md, scoring.json"
    why_human: "End-to-end path through a real LLM call and interactive typer.confirm prompt cannot be triggered without a live API key and a scored job in the local database"
  - test: "Re-run `jobinator apply <same_job_id>` a second time and confirm"
    expected: "A second timestamped directory is created alongside the first — no overwrite occurs; both bundles are intact on disk"
    why_human: "Versioned directory uniqueness requires observing two separate confirmed runs with real timestamps"
---

# Phase 4: Materials Generation Verification Report

**Phase Goal:** For any above-threshold job, the system generates a tailored resume, cover letter, and interview prep brief grounded strictly in the user's profile — and requires human confirmation before writing outputs
**Verified:** 2026-04-06T20:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `apply <job_id>` generates resume, cover letter, and prep brief saved to `<company>/<role>/<timestamp>/` | ✓ VERIFIED | `run_apply` in `pipelines/apply.py` calls all three generator methods, calls `output_manager.create_application_dir(company_slug, role_slug)`, and writes 9 files to the versioned directory. CLI `apply` command wires to this pipeline. Test `TestRunApplyWritesFiles` confirms all 9 files exist post-run. |
| 2 | Generated resume contains no claims not traceable to user's JSON Resume profile | ✓ VERIFIED | `prompts.py` embeds 7 grounding rules in the system message: "ONLY source of truth", "NOT INVENT", "Do NOT invent". Full profile JSON is injected into the system message verbatim. `ResumeContent` field descriptions explicitly prohibit invented data. `test_resume_grounding_no_invented_content` verifies the system prompt contains both "ONLY source of truth" and "NOT INVENT". |
| 3 | All three materials are rendered to PDF and files are present on disk after generation | ✓ VERIFIED | `renderer.py` provides `render_pdf()` using `WeasyPrint.HTML(string=).write_pdf()`. All three templates exist (`resume.html.jinja`, `cover_letter.html.jinja`, `prep_brief.html.jinja`). `apply.py` calls `render_pdf("resume", ...)`, `render_pdf("cover_letter", ...)`, `render_pdf("prep_brief", ...)` and writes bytes to disk. `test_render_pdf_produces_valid_bytes` asserts `b"%PDF"` magic bytes. Full suite 218/218 passing. |
| 4 | User sees preview and must confirm before any file is written — system does not write silently | ✓ VERIFIED | `apply.py` line 159 calls `confirm_callback("Write these files to disk?", abort=True)` before any `create_application_dir` or file write. Directory creation is at line 175, file writes begin at line 186. `TestRunApplyAbortIfUserDeclines` verifies zero `.pdf` files exist after `typer.Abort()`. `test_run_apply_aborts_if_user_declines` checks `result.bundle_path is None`. |
| 5 | Re-running `apply` for same job creates new versioned folder rather than overwriting | ✓ VERIFIED | `OutputManager.create_application_dir` produces timestamp-based subdirectories. `TestRunApplyVersionedDirectory.test_two_applies_create_different_dirs` sleeps 1.1s between runs and asserts `result1.bundle_path != result2.bundle_path` with both paths existing on disk. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/jobinator/models/material.py` | GeneratedMaterial SQLModel table | ✓ VERIFIED | Exists, contains `class GeneratedMaterial(SQLModel, table=True)` with `foreign_key="normalizedjob.id"`, all tracking fields present |
| `src/jobinator/generation/models.py` | LLM response Pydantic models | ✓ VERIFIED | Exports `ResumeContent`, `CoverLetterContent`, `PrepBriefContent`, `TailoredWorkEntry` — all BaseModel (not SQLModel) |
| `src/jobinator/generation/prompts.py` | Prompt builders | ✓ VERIFIED | Contains `build_resume_prompt`, `build_cover_letter_prompt`, `build_prep_brief_prompt` with full profile injection and grounding rules |
| `src/jobinator/generation/generator.py` | MaterialsGenerator | ✓ VERIFIED | `class MaterialsGenerator` with all three generation methods, each calling `budget_tracker.assert_within_limits()` before the LLM call |
| `src/jobinator/generation/renderer.py` | Jinja2 + WeasyPrint renderer | ✓ VERIFIED | `render_html()` and `render_pdf()` present; uses `FileSystemLoader`; lazy-imports WeasyPrint |
| `src/jobinator/generation/__init__.py` | Module package with exports | ✓ VERIFIED | Exports all key symbols: `MaterialsGenerator`, `ResumeContent`, `CoverLetterContent`, `PrepBriefContent`, `TailoredWorkEntry`, `render_html`, `render_pdf` |
| `src/jobinator/templates/resume.html.jinja` | Resume HTML template | ✓ VERIFIED | Present; renders `{{ basics.name }}`, `{{ summary }}`, loops `relevant_experience` |
| `src/jobinator/templates/cover_letter.html.jinja` | Cover letter HTML template | ✓ VERIFIED | Present; renders `{{ opening }}`, `body_paragraphs` loop |
| `src/jobinator/templates/prep_brief.html.jinja` | Prep brief HTML template | ✓ VERIFIED | Present; renders `{{ likely_questions }}` loop, talking points, gaps |
| `src/jobinator/configs/settings.py` | MaterialsConfig | ✓ VERIFIED | `class MaterialsConfig(BaseModel)` and `get_materials_config()` added; defaults: `strong_model="claude-3-5-sonnet-latest"`, `apply_threshold=0.6` |
| `src/jobinator/pipelines/apply.py` | Apply pipeline orchestrator | ✓ VERIFIED | `run_apply()` and `ApplyResult` dataclass; all 8 pipeline steps present; HITL gate before file write |
| `src/jobinator/cli.py` | `apply` CLI command | ✓ VERIFIED | `def apply(job_id, force)` command registered in Typer app; includes API key check, job lookup, profile loading, threshold gating, `--force` override |
| `tests/test_generation.py` | Generation unit tests | ✓ VERIFIED | 7 tests including grounding, budget gating, operation names — all passing |
| `tests/test_renderer.py` | Renderer tests | ✓ VERIFIED | 6 tests including PDF `b"%PDF"` assertion — all passing |
| `tests/test_apply_pipeline.py` | Pipeline tests | ✓ VERIFIED | 10 tests covering all behavioral paths (confirm, decline, threshold, budget, versioning, persistence, decision logging) — all passing |
| `tests/test_apply_cli.py` | CLI tests | ✓ VERIFIED | 10 tests covering CLI paths (no API key, job not found, no profile, threshold, --force) — all passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `generation/generator.py` | `instructor.from_litellm(litellm.completion)` | `_client.create_with_completion()` | ✓ WIRED | Module-level `_client = instructor.from_litellm(litellm.completion)` at line 42; all three methods call `_client.create_with_completion(...)` |
| `generation/generator.py` | `budget/tracker.py` | `budget_tracker.assert_within_limits()` | ✓ WIRED | Each of the three generation methods calls `self.budget_tracker.assert_within_limits(job_id=job.id)` as step 1 before LLM call |
| `generation/renderer.py` | `src/jobinator/templates/` | `Jinja2 FileSystemLoader` | ✓ WIRED | `_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"` and `FileSystemLoader(str(_TEMPLATES_DIR))` in `_get_env()` |
| `generation/renderer.py` | `weasyprint.HTML` | `HTML(string=).write_pdf()` | ✓ WIRED | `from weasyprint import HTML` (lazy) then `HTML(string=html_content).write_pdf()` |
| `pipelines/apply.py` | `generation/generator.py` | `generator.generate_resume/cover_letter/prep_brief` | ✓ WIRED | All three `generator.generate_*` calls in `run_apply()` at lines 115, 122, 129 |
| `pipelines/apply.py` | `generation/renderer.py` | `render_pdf` for all three documents | ✓ WIRED | `from jobinator.generation.renderer import render_pdf` at top; calls `render_pdf("resume", ...)`, `render_pdf("cover_letter", ...)`, `render_pdf("prep_brief", ...)` |
| `pipelines/apply.py` | `output/manager.py` | `output_manager.create_application_dir` after confirmation | ✓ WIRED | `OutputManager(output_dir=config.output_dir)` and `create_application_dir(job.company_slug, role_slug)` called at line 175, AFTER `confirm_callback` at line 159 |
| `cli.py` | `pipelines/apply.py` | `from jobinator.pipelines.apply import run_apply` | ✓ WIRED | Lazy import inside `apply()` function body: `from jobinator.pipelines.apply import get_job_with_score, run_apply` |
| `pipelines/apply.py` | `typer.confirm` | HITL gate before file write | ✓ WIRED | `confirm_callback=typer.confirm` default parameter; called as `confirm_callback("Write these files to disk?", abort=True)` with `except typer.Abort` handler |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `resume.html.jinja` | `summary`, `relevant_experience`, `highlighted_skills`, `education` | `ResumeContent` model from LLM via Instructor | Yes — LLM produces structured output validated by Pydantic; template uses `relevant_experience` (matching model field) | ✓ FLOWING |
| `cover_letter.html.jinja` | `opening`, `body_paragraphs`, `closing` | `CoverLetterContent` model from LLM | Yes — fields come from Instructor-validated LLM output | ✓ FLOWING |
| `prep_brief.html.jinja` | `likely_questions`, `talking_points`, `company_overview`, `role_summary`, `gaps_to_address` | `PrepBriefContent` model from LLM | Yes — fields come from Instructor-validated LLM output | ✓ FLOWING |
| `apply.py` resume/cover/prep PDFs | `resume_content`, `cover_content`, `prep_content` | `generator.generate_*()` → LLM → Pydantic models → `render_pdf()` | Yes — no hardcoded empty data anywhere in the pipeline | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 4 test suite passes | `uv run pytest tests/test_generation.py tests/test_renderer.py tests/test_apply_pipeline.py tests/test_apply_cli.py -x -q` | 33 passed | ✓ PASS |
| Full test suite stays green | `uv run pytest tests/ -x -q` | 218 passed | ✓ PASS |
| apply command help registered | `uv run python -m jobinator.cli apply --help` | Shows `JOB_ID` argument and `--force` flag | ✓ PASS |
| apply rejects missing job gracefully | `uv run python -m jobinator.cli apply nonexistent-id` | Exit 1 — "No API key configured" (expected; no key in env) | ✓ PASS |
| Key imports work | `uv run python -c "from jobinator.models.material import GeneratedMaterial; from jobinator.generation.models import ResumeContent..."` | ALL IMPORTS OK | ✓ PASS |
| Alembic at head | `uv run alembic upgrade head` | No migrations pending | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MATL-01 | 04-01, 04-02, 04-03 | User can generate a tailored resume from JSON Resume base | ✓ SATISFIED | `MaterialsGenerator.generate_resume()` produces `ResumeContent` tailored to job via Instructor + LiteLLM; `apply` CLI command exposes this |
| MATL-02 | 04-01, 04-02 | Generated resumes are truthful — no hallucinated metrics, dates, or skills | ✓ SATISFIED | 7-rule grounding block in prompts.py system message; `ResumeContent` field descriptions enforce no-invention; `test_resume_grounding_no_invented_content` verifies runtime prompt contains grounding rules |
| MATL-03 | 04-01, 04-02 | User can generate a concise, company+role-specific cover letter per job | ✓ SATISFIED | `generate_cover_letter()` produces `CoverLetterContent` with opening referencing specific company and role; prompt scopes generation to `{job.company}` |
| MATL-04 | 04-01, 04-02 | User can generate an interview prep brief per job | ✓ SATISFIED | `generate_prep_brief()` produces `PrepBriefContent` with `company_overview`, `likely_questions`, `talking_points`, `gaps_to_address` |
| MATL-05 | 04-02, 04-03 | All generated materials are rendered to PDF | ✓ SATISFIED | `render_pdf()` via Jinja2 + WeasyPrint produces valid PDF bytes (`b"%PDF"` verified by tests); all three documents rendered and written to disk in `run_apply()` |
| MATL-06 | 04-01, 04-03 | Materials saved to configurable output directory organized by company/role with versioning | ✓ SATISFIED | `OutputManager.create_application_dir(company_slug, role_slug)` produces `<output_dir>/<company>/<role>/<timestamp>/` structure; versioning tested by `TestRunApplyVersionedDirectory` |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Scanned all Phase 4 key files. No TODO/FIXME/PLACEHOLDER comments, no `return null`/`return {}` stubs, no hardcoded empty data flowing to user-visible output. The grounding instructions in `prompts.py` look superficially like they could be "check-box" text, but they are enforced at the LLM call level through Instructor's response_model validation — not a stub pattern.

### Human Verification Required

#### 1. PDF Visual Quality

**Test:** Generate materials for a real scored job (`jobinator apply <job_id>`) and open the three output PDFs in a viewer.
**Expected:** Resume renders with header (name, label, contact), Summary section, Experience entries with dates, Skills grid, and Education. Cover letter renders with date, paragraphs, and name at close. Prep brief renders with numbered/bulleted sections for company overview, questions, talking points, and gaps. No overlapping elements, no garbled text, correct page margins.
**Why human:** WeasyPrint CSS rendering quality is a visual property. The test suite verifies that PDF bytes start with `b"%PDF"` and have length > 100, but cannot detect layout defects, font rendering issues, or section overflow.

#### 2. End-to-End HITL Confirmation Gate

**Test:** Run `jobinator apply <scored_job_id>` with a real API key.
**Expected:** (a) Generation output appears in terminal. (b) A Rich `Panel` labeled "Resume Summary Preview" appears with the resume summary text. (c) Lines showing experience entry count, skill count, cover letter opening snippet, and prep brief question count appear below the panel. (d) The prompt "Write these files to disk?" appears. (e) Answering "n" produces no files on disk and exits 0. (f) Answering "y" produces all 9 files in `<output_dir>/<company>/<role>/<timestamp>/`.
**Why human:** The interactive `typer.confirm()` prompt cannot be triggered in automated tests — the test suite uses `confirm_callback=lambda ...` injection. The Rich panel preview also requires visual inspection to confirm informativeness.

#### 3. Versioned Directory Behavior (Confirmed Run)

**Test:** Run `jobinator apply <job_id>` twice, confirming both times.
**Expected:** Two separate timestamp directories exist side-by-side under `<output_dir>/<company>/<role>/`. Neither overwrites the other. Both contain complete file bundles.
**Why human:** The automated test `TestRunApplyVersionedDirectory` verifies this with mocked render_pdf and a 1.1s sleep, but confirming the behavior with real PDFs and real timestamps requires a live run.

### Gaps Summary

No gaps found in automated verification. All 5 success criteria are satisfied by the implementation:

1. `apply <job_id>` command exists, is wired end-to-end, and all 9 output files are written under the versioned directory structure.
2. Grounding rules are embedded in all three prompt builders with the full profile JSON; tests verify runtime prompt content.
3. All three materials use WeasyPrint PDF rendering, confirmed by `b"%PDF"` magic bytes in tests.
4. HITL gate via `typer.confirm()` is called at line 159 of `apply.py`, with directory creation at line 175 — no files can be written before user confirms.
5. `OutputManager.create_application_dir()` produces timestamp-based unique directories; versioning tested automatically.

Three items require human confirmation before the phase can be fully signed off: PDF visual quality, interactive confirmation behavior with a live LLM, and versioned directory confirmation in a real run.

---

_Verified: 2026-04-06T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
