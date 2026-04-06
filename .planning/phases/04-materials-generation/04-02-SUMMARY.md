---
phase: 04-materials-generation
plan: "02"
subsystem: generation
tags: [generation, llm, instructor, jinja2, weasyprint, pdf, prompts, budget]
dependency_graph:
  requires: ["04-01"]
  provides: ["04-03"]
  affects: ["scoring/client.py pattern", "budget/tracker.py pattern"]
tech_stack:
  added: []
  patterns:
    - "Instructor create_with_completion() for structured LLM output"
    - "module-level _client = instructor.from_litellm() matching scoring/client.py"
    - "Budget gate via assert_within_limits() before each LLM call"
    - "Cost extraction via raw._hidden_params['response_cost']"
    - "Jinja2 FileSystemLoader for template-based HTML rendering"
    - "WeasyPrint HTML(string=).write_pdf() for PDF conversion"
    - "MagicMock(spec=BudgetTracker) to allow assert_* attribute access in tests"
key_files:
  created:
    - src/jobinator/generation/prompts.py
    - src/jobinator/generation/generator.py
    - src/jobinator/generation/renderer.py
    - src/jobinator/templates/resume.html.jinja
    - src/jobinator/templates/cover_letter.html.jinja
    - src/jobinator/templates/prep_brief.html.jinja
    - tests/test_generation.py
    - tests/test_renderer.py
  modified: []
decisions:
  - "MagicMock(spec=BudgetTracker) required for assert_within_limits — pytest/MagicMock treats attributes starting with 'assert' as assertion helpers without spec"
  - "Prompt grounding rules embedded in system message with full profile JSON — not truncated, satisfies MATL-02 verifiability"
  - "Templates use relevant_experience not experience — matches ResumeContent.relevant_experience field name from models.py"
metrics:
  duration_minutes: 6
  completed_date: "2026-04-06"
  tasks_completed: 2
  files_created: 8
  files_modified: 0
  tests_added: 13
  tests_passing: 198
---

# Phase 04 Plan 02: Generation Logic, Prompts, Templates, and Renderer Summary

**One-liner:** Instructor-based LLM generation with per-method budget gating producing structured Pydantic content, Jinja2 templates rendering to styled HTML, WeasyPrint converting to valid PDF bytes.

## What Was Built

### Task 1: Prompt Builders and MaterialsGenerator

**src/jobinator/generation/prompts.py** — Three prompt builders following the scoring/prompt.py pattern:
- `build_resume_prompt()`: System message with full profile JSON and 7-rule truthfulness guard ("ONLY source of truth", "NOT INVENT"). User message with job title, company, description, optional score strengths/gaps.
- `build_cover_letter_prompt()`: Same grounding rules, scoped to company+role, instructs concise 3-paragraph format.
- `build_prep_brief_prompt()`: Profile JSON for talking point grounding, requests company overview, 5-10 questions, 5-8 talking points, 2-4 gaps.

**src/jobinator/generation/generator.py** — `MaterialsGenerator` with three generation methods:
- Each method: (1) assert_within_limits BEFORE LLM call, (2) build prompt, (3) create_with_completion(), (4) extract cost from raw._hidden_params["response_cost"], (5) create SpendRecord with correct operation name, (6) record spend, (7) return (content, spend).
- Operation names: `generate_resume`, `generate_cover_letter`, `generate_prep_brief`.
- Module-level `_client = instructor.from_litellm(litellm.completion)` — same pattern as scoring/client.py.

### Task 2: Templates and Renderer

**src/jobinator/templates/resume.html.jinja** — Styled resume with header, summary, experience loop, skills grid, education. Uses `relevant_experience` (matching ResumeContent field).

**src/jobinator/templates/cover_letter.html.jinja** — Dated letter with opening, body paragraphs loop, closing.

**src/jobinator/templates/prep_brief.html.jinja** — Interview prep with company overview, role summary, questions/talking points lists, optional gaps section in red.

**src/jobinator/generation/renderer.py** — Two public functions:
- `render_html()`: Jinja2 Environment with FileSystemLoader, merges content.model_dump() + context dict, renders template.
- `render_pdf()`: Lazy-imports WeasyPrint, calls render_html() then HTML(string=).write_pdf().

## Test Coverage

**tests/test_generation.py** — 7 tests:
- `test_generate_resume_returns_structured_content` — verify (ResumeContent, SpendRecord) return
- `test_generate_cover_letter` — verify (CoverLetterContent, SpendRecord) return
- `test_generate_prep_brief` — verify (PrepBriefContent, SpendRecord) return
- `test_budget_gated_before_each_call` — assert_within_limits called 3x with job_id
- `test_budget_exceeded_stops_generation` — BudgetExceeded propagates, LLM not called
- `test_resume_grounding_no_invented_content` — system prompt contains profile JSON and grounding rules
- `test_spend_record_operation_names` — correct operation strings per method

**tests/test_renderer.py** — 6 tests:
- `test_render_resume_html` — HTML contains summary, experience, company
- `test_render_cover_letter_html` — HTML contains opening, body, closing
- `test_render_prep_brief_html` — HTML contains overview, questions, talking points
- `test_render_pdf_produces_valid_bytes` — bytes start with b"%PDF"
- `test_render_pdf_cover_letter` — valid PDF bytes
- `test_render_pdf_prep_brief` — valid PDF bytes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MagicMock spec required for assert_within_limits**
- **Found during:** Task 1 GREEN phase (first test run)
- **Issue:** `MagicMock()` without spec treats any attribute starting with "assert" as a pytest assertion helper, raising `AttributeError: 'assert_within_limits' is not a valid assertion`.
- **Fix:** Changed `_make_budget_tracker()` to `MagicMock(spec=BudgetTracker)` — spec tells MagicMock that `assert_within_limits` is a real attribute.
- **Files modified:** tests/test_generation.py
- **Commit:** 117f373 (included in GREEN phase commit)

**2. [Rule 3 - Blocking] Template uses relevant_experience not experience**
- **Found during:** Task 2 template creation
- **Issue:** Plan template snippet used `{% for entry in experience %}` but ResumeContent model field is `relevant_experience`.
- **Fix:** Used `relevant_experience` in resume.html.jinja to match the actual Pydantic model field name.
- **Files modified:** src/jobinator/templates/resume.html.jinja
- **Commit:** 5612893

## Known Stubs

None — all content fields are wired to Pydantic model data. Templates render real structured content from ResumeContent/CoverLetterContent/PrepBriefContent instances.

## Self-Check: PASSED

Files verified to exist:
- src/jobinator/generation/prompts.py: FOUND
- src/jobinator/generation/generator.py: FOUND
- src/jobinator/generation/renderer.py: FOUND
- src/jobinator/templates/resume.html.jinja: FOUND
- src/jobinator/templates/cover_letter.html.jinja: FOUND
- src/jobinator/templates/prep_brief.html.jinja: FOUND
- tests/test_generation.py: FOUND
- tests/test_renderer.py: FOUND

Commits verified: d59e915, 117f373, 5456d4c, 5612893
