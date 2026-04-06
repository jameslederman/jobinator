# Phase 3: LLM Scoring - Research

**Researched:** 2026-04-06
**Domain:** LiteLLM multi-provider integration, Instructor structured output, budget enforcement, SQLModel schema extension
**Confidence:** HIGH

## Summary

Phase 3 wires LLM-based scoring onto the already-working discovery pipeline. The budget infrastructure (`BudgetTracker`, `SpendRecord`, `BudgetExceeded`) was built in Phase 1 and is fully functional — this phase connects it to real LLM calls. The scoring layer has three responsibilities: (1) call a cheap LLM model tier (claude-3-haiku or gpt-4o-mini) with a structured prompt, (2) extract a typed `JobScore` Pydantic model via Instructor, and (3) persist both the score and the spend record atomically.

The key integration pattern is Instructor + LiteLLM via `instructor.from_litellm(litellm.completion)` (the `from_litellm` factory, not `from_provider`) with `create_with_completion()` to get both the structured output and the raw completion for cost extraction. Cost is available at `raw_completion._hidden_params["response_cost"]`. Token counts live at `raw_completion.usage.prompt_tokens` and `raw_completion.usage.completion_tokens`. A known issue exists where `completion_cost()` called on Instructor-wrapped responses may return 0.0 — using `_hidden_params["response_cost"]` directly is the reliable path.

The scoring schema needs a new `JobScore` SQLModel table (linked to `NormalizedJob` by FK) storing the fit_score, strengths, gaps, compensation_estimate, priority_score, and reasoning fields. An Alembic migration generates this table alongside the existing schema. The `score` CLI command queries unscored jobs (status = 'discovered'), calls `BudgetTracker.assert_within_limits()` before each LLM call, persists the score and spend record, and updates the job's status to 'scored' via a `StatusEvent`.

**Primary recommendation:** Use `instructor.from_litellm(litellm.completion)` + `create_with_completion()` for structured scoring. Gate every call with the existing `BudgetTracker.assert_within_limits()`. Store scores in a new `JobScore` table. Read profile from a JSON Resume file at a configurable path.

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, SQLite + SQLModel, CLI (Typer), JSON Resume format — no deviation
- **LLM providers**: LiteLLM for multi-provider abstraction; cheap models (claude-3-haiku / gpt-4o-mini) for scoring; strong models (claude-3-5-sonnet-latest / gpt-4o) for generation (Phase 4)
- **Agent framework**: Custom loop only — no LangChain, no LangGraph
- **Storage**: SQLite for all state (scores, spend, decisions)
- **Budget**: Every LLM call must be gated by `BudgetTracker.assert_within_limits()` and recorded via `BudgetTracker.record()`
- **Package manager**: uv
- **Linting/formatting**: ruff
- **Type checking**: mypy
- **Pre-commit hooks**: ruff + mypy run on commit
- **Test framework**: pytest, with respx or pytest-httpx for HTTP mocks; factory-boy for fixtures

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCOR-02 | Jobs passing hard filters are scored by LLM for nuanced fit (0-1 score) | LiteLLM + Instructor pattern identified; `JobScore` schema designed |
| SCOR-03 | Each scored job includes strengths match, gaps analysis, and compensation estimate | Fields included in `JobScore` Pydantic model; Instructor enforces structure |
| SCOR-04 | Each scored job has a priority score combining fit, urgency, recency, and user preferences | `priority_score` field; computed from fit_score + freshness metadata in `NormalizedJob` |
| SCOR-05 | Every score includes human-readable reasoning explaining why the job scored as it did | `reasoning` text field in `JobScore` model; required by Instructor schema |
| INFR-01 | LLM calls route through multi-provider abstraction (cheap models for filtering/scoring, strong models for generation) | LiteLLM handles routing; `ScoringConfig` holds model-tier config |
| INFR-02 | Token and API spend is tracked per call with configurable daily and per-job budget limits | `raw_completion._hidden_params["response_cost"]` + usage fields; existing `SpendRecord` table |
| INFR-03 | Budget enforcement gates LLM calls — hard stop when limit is reached | Existing `BudgetTracker.assert_within_limits()` raises `BudgetExceeded`; CLI catches and reports |
</phase_requirements>

## Standard Stack

### Core (new dependencies for Phase 3)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| litellm | 1.83.3 | Unified LLM API client | Single call surface for Anthropic + OpenAI; handles auth, retries, cost normalization; already chosen in CLAUDE.md |
| instructor | 1.15.1 | Structured LLM output | Wraps LiteLLM to enforce Pydantic model output with retry-on-validation-failure; eliminates manual JSON parsing |
| anthropic | 0.89.0 | Direct Anthropic SDK | LiteLLM dependency; also used by instructor under the hood for Claude calls |
| openai | 2.30.0 | Direct OpenAI SDK | LiteLLM dependency for OpenAI calls |
| tiktoken | 0.12.0 | Token pre-counting | Pre-flight token estimation before calling; essential for budget enforcement |

### Already Installed (no new install needed)
| Library | Version | Purpose |
|---------|---------|---------|
| pydantic | >=2.7 | `JobScore` Pydantic model validation |
| sqlmodel | >=0.0.21 | `JobScore` SQLModel table |
| alembic | >=1.13 | Migration for new `job_score` table |
| typer + rich | >=0.12, >=13.7 | `score` CLI command |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| instructor | Manual JSON parsing | Instructor handles retry-on-validation-failure; LLMs produce malformed JSON — don't DIY |
| litellm | Direct provider SDKs | LiteLLM eliminates per-provider cost tables, auth wiring, response normalization |
| `_hidden_params["response_cost"]` | `completion_cost(response)` | `completion_cost()` returns 0.0 when called via Instructor wrapper (known bug); use `_hidden_params` |

**Installation (Phase 3 additions):**
```bash
uv add litellm>=1.40 instructor>=1.4 anthropic>=0.28 openai>=1.30 tiktoken>=0.7
```

**Version verification (confirmed against PyPI 2026-04-06):**
- litellm: 1.83.3
- instructor: 1.15.1
- tiktoken: 0.12.0
- anthropic: 0.89.0
- openai: 2.30.0

## Architecture Patterns

### Recommended Project Structure (Phase 3 additions)
```
src/jobinator/
├── scoring/
│   ├── __init__.py          # exports: JobScorer, ScoringConfig, score_job
│   ├── scorer.py            # JobScorer class — orchestrates LLM call + spend record
│   ├── schema.py            # JobScore SQLModel table + Pydantic output model
│   └── prompt.py            # Prompt builder — formats job + profile into scoring prompt
├── models/
│   ├── job.py               # (existing) NormalizedJob, StatusEvent
│   ├── budget.py            # (existing) SpendRecord, DecisionLog
│   └── score.py             # NEW: JobScore SQLModel table
├── configs/
│   └── settings.py          # (extend) add ScoringConfig as standalone BaseModel
└── pipelines/
    └── score.py             # NEW: scoring pipeline orchestrator (like discover.py)

alembic/versions/
└── <hash>_add_job_score_table.py   # NEW migration
```

### Pattern 1: Instructor + LiteLLM for Structured Scoring

**What:** Use `instructor.from_litellm()` to get Pydantic-validated output from a cheap LLM tier. Use `create_with_completion()` to access raw response for cost extraction.

**When to use:** Every LLM scoring call.

**Example:**
```python
# Source: https://python.useinstructor.com/integrations/litellm/
import instructor
import litellm
from pydantic import BaseModel, Field

# Patch once at module level
client = instructor.from_litellm(litellm.completion)

class JobScoreOutput(BaseModel):
    """Structured output from the LLM scoring call."""
    fit_score: float = Field(ge=0.0, le=1.0, description="Overall fit 0-1")
    strengths_match: list[str] = Field(description="Matching strengths (2-5 bullet points)")
    gaps: list[str] = Field(description="Gaps or concerns (0-5 bullet points)")
    compensation_estimate: str = Field(description="Estimated comp range or 'unknown'")
    priority_score: float = Field(ge=0.0, le=1.0, description="Combined priority (fit + urgency + recency)")
    reasoning: str = Field(description="Human-readable explanation paragraph (3-5 sentences)")

def call_scoring_llm(model: str, messages: list[dict]) -> tuple[JobScoreOutput, float, int, int]:
    """Returns (score_output, cost_usd, input_tokens, output_tokens)."""
    score, raw = client.create_with_completion(
        model=model,
        messages=messages,
        response_model=JobScoreOutput,
        max_tokens=512,
    )
    cost = float(raw._hidden_params.get("response_cost", 0.0))
    input_tokens = raw.usage.prompt_tokens
    output_tokens = raw.usage.completion_tokens
    return score, cost, input_tokens, output_tokens
```

### Pattern 2: JobScore SQLModel Table

**What:** New table storing one score per job (one-to-one relationship with NormalizedJob).

**When to use:** After every successful LLM scoring call.

```python
# Source: established SQLModel pattern from existing models/job.py
from sqlmodel import Field, SQLModel
from datetime import datetime
from typing import Optional
import json

class JobScore(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = Field(foreign_key="normalizedjob.id", unique=True, index=True)
    fit_score: float = Field(description="LLM-assigned fit score 0-1")
    priority_score: float = Field(description="Combined priority 0-1")
    strengths_json: str = Field(description="JSON array of matching strengths")
    gaps_json: str = Field(description="JSON array of gaps/concerns")
    compensation_estimate: Optional[str] = Field(default=None)
    reasoning: str = Field(description="Human-readable reasoning paragraph")
    model_used: str = Field(description="Model that produced this score")
    scored_at: datetime = Field(default_factory=datetime.utcnow)
```

### Pattern 3: ScoringConfig (standalone BaseModel, not Settings subclass)

**What:** Config object for scoring parameters. Follows the same pattern as `FilterConfig` and `DiscoveryConfig` — standalone `BaseModel`, not a nested `Settings` subclass. Loadable from `[scoring]` section of config.toml.

**Why this pattern:** Phase 1 established that standalone `BaseModel` configs are test-overridable without requiring config files. All Phase 2 configs follow this pattern.

```python
from pydantic import BaseModel, Field

class ScoringConfig(BaseModel):
    cheap_model: str = Field(
        default="claude-3-haiku-20240307",
        description="Model for scoring (cheap tier)"
    )
    strong_model: str = Field(
        default="claude-3-5-sonnet-latest",
        description="Model for generation (strong tier, Phase 4)"
    )
    score_batch_size: int = Field(
        default=10,
        description="Max jobs to score per run"
    )
    min_fit_score_threshold: float = Field(
        default=0.5,
        description="Jobs below this score are not promoted to 'scored' status"
    )
    profile_path: Optional[str] = Field(
        default=None,
        description="Path to JSON Resume profile file"
    )
```

### Pattern 4: Score Pipeline Orchestrator

**What:** Mirrors `run_discovery()` in `discover.py` — iterates unscored jobs, applies budget gate, calls scorer, persists score and spend, logs decisions.

```python
# Mirrors discover.py pattern
def run_scoring(
    session: Session,
    budget_tracker: BudgetTracker,
    scorer: JobScorer,
    config: ScoringConfig,
) -> ScoringResult:
    # Query jobs with status = 'discovered' (no JobScore yet)
    # For each job:
    #   1. budget_tracker.assert_within_limits(job_id=job.id)  <- raises BudgetExceeded
    #   2. score, cost, in_tok, out_tok = scorer.score(job)
    #   3. persist JobScore row
    #   4. persist SpendRecord row (via budget_tracker.record())
    #   5. add StatusEvent(status='scored')
    #   6. budget_tracker.log_decision('score_complete', ...)
    # Return ScoringResult with counts
    ...
```

### Pattern 5: Budget-Gated CLI Command

**What:** `score` Typer command that catches `BudgetExceeded`, prints current spend, and exits cleanly.

```python
@app.command()
def score(
    limit: int = typer.Option(10, "--limit", help="Max jobs to score"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Score discovered jobs for fit using LLM."""
    from jobinator.budget.tracker import BudgetExceeded
    try:
        result = run_scoring(session, budget_tracker, scorer, config)
    except BudgetExceeded as e:
        console.print(f"[red]Budget limit reached: {e}[/red]")
        console.print(f"Daily spend: ${budget_tracker.daily_spend():.4f}")
        raise typer.Exit(code=1)
```

### Anti-Patterns to Avoid

- **Calling LLM before budget gate:** Always call `assert_within_limits()` before the LLM call, never after.
- **Using `completion_cost()` on Instructor-wrapped response:** Returns 0.0 due to a known bug (GitHub issue #1330 in instructor). Use `raw._hidden_params["response_cost"]` instead.
- **Storing strengths/gaps as separate columns:** Use JSON strings for list fields in SQLite — cleaner than 5 separate varchar columns.
- **ScoringConfig as Settings subclass:** Established in Phase 1/2 that standalone `BaseModel` configs are test-overridable without requiring config files on disk. Do not nest in `Settings`.
- **Calling `litellm.completion()` directly without Instructor:** Requires manual JSON parsing and retry logic. Instructor handles both.
- **Hardcoding model names in scorer:** Keep in `ScoringConfig` so the user can swap models in config.toml without code changes.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured LLM output with validation | Manual JSON parsing + try/except | Instructor | LLMs produce malformed JSON; retry-on-validation-failure is non-trivial; Instructor handles both |
| Multi-provider LLM routing | Per-provider if/else | LiteLLM | Cost normalization, auth handling, retry logic across 100+ providers |
| Token counting before call | Custom tokenizer logic | `tiktoken` / `litellm.token_counter()` | Model-specific encoding rules; incorrect counting causes budget miscalculation |
| Cost extraction | Computing price × tokens manually | `raw._hidden_params["response_cost"]` | LiteLLM maintains its own pricing table; manual calculation diverges from actual charges |
| Retry on validation failure | try/except loop around LLM call | Instructor's built-in `max_retries` | Instructor sends the validation error back to the LLM as a correction prompt — smarter than blind retry |

**Key insight:** The budget tracker and spend record infrastructure already exists from Phase 1. Phase 3's job is to wire real LLM calls through it, not rebuild any of it.

## Common Pitfalls

### Pitfall 1: completion_cost() Returns 0.0 with Instructor
**What goes wrong:** `litellm.completion_cost(completion_response=raw)` returns 0.0 when `raw` comes from an Instructor-wrapped call.
**Why it happens:** Instructor modifies the response object before returning it; the cost field gets stripped. Documented in instructor GitHub issue #1330.
**How to avoid:** Extract cost from `raw._hidden_params["response_cost"]` directly after `create_with_completion()`.
**Warning signs:** Daily spend stays at $0.00 even after scoring several jobs.

### Pitfall 2: LiteLLM Model Name Format
**What goes wrong:** `litellm.completion(model="haiku")` fails; `model="claude-3-haiku"` may also fail on some versions.
**Why it happens:** LiteLLM requires the full versioned model string for cost lookup to work.
**How to avoid:** Use `"claude-3-haiku-20240307"` for Anthropic, `"gpt-4o-mini"` for OpenAI. These are the exact strings in LiteLLM's pricing table.
**Warning signs:** `KeyError` on cost lookup, or `response_cost` is 0.0.

### Pitfall 3: LiteLLM Pricing Table Lag
**What goes wrong:** LiteLLM's bundled pricing table may be several weeks behind actual provider pricing (noted as LOW confidence in CLAUDE.md; recorded as blocker in STATE.md).
**Why it happens:** Pricing data is shipped as a static file with the library; fast-moving provider pricing changes aren't reflected immediately.
**How to avoid:** Treat `response_cost` as approximate; validate against actual Anthropic/OpenAI invoices after the first few scoring runs. Do not set budget limits assuming LiteLLM cost is exact.
**Warning signs:** Budget exhausted faster or slower than expected; actual API invoice diverges from logged spend.

### Pitfall 4: Missing API Key Produces Unhelpful Error
**What goes wrong:** LiteLLM raises a vague authentication error when `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is empty string (the `Settings` default).
**Why it happens:** Empty string is truthy-enough to not trigger the "missing key" guard but invalid as an API key.
**How to avoid:** In the `score` command, validate that at least one API key is non-empty before calling the scorer. Print a clear message: "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env".
**Warning signs:** `AuthenticationError` or `BadRequestError` on first call.

### Pitfall 5: Alembic Migration Needs `import sqlmodel`
**What goes wrong:** Alembic autogenerate produces a migration that fails at runtime with `AutoString` type not found.
**Why it happens:** SQLModel's custom column types need `import sqlmodel` in the migration file. This was baked into `script.py.mako` in Phase 1.
**How to avoid:** This is already handled by the Phase 1 mako template. But when generating new migrations, verify the import is present. Run `alembic upgrade head` and confirm no import errors.
**Warning signs:** `AttributeError: module 'sqlalchemy' has no attribute 'AutoString'`.

### Pitfall 6: `JobScore` unique constraint on job_id
**What goes wrong:** Re-running `score` on an already-scored job creates a duplicate `JobScore` row, causing a unique constraint violation on the next run that queries by job_id.
**Why it happens:** Without a unique constraint on `job_id`, the pipeline can insert multiple scores for one job.
**How to avoid:** Set `unique=True` on `JobScore.job_id`. The scoring pipeline should also query jobs with `status='discovered'` (no existing `JobScore`) before calling the LLM, so re-runs skip already-scored jobs.

### Pitfall 7: Profile Path Not Configured
**What goes wrong:** The scorer cannot construct a meaningful prompt without the user's profile.
**Why it happens:** Phase 3 is the first phase that needs the JSON Resume profile — it doesn't exist by default.
**How to avoid:** If `ScoringConfig.profile_path` is None or the file doesn't exist, skip scoring and print a clear setup message. The `score` command should check profile existence before starting the batch loop.

## Code Examples

Verified patterns from official sources:

### Instructor + LiteLLM: Structured Output with Cost
```python
# Source: https://python.useinstructor.com/integrations/litellm/
import instructor
import litellm

client = instructor.from_litellm(litellm.completion)

score_output, raw_completion = client.create_with_completion(
    model="claude-3-haiku-20240307",
    messages=[{"role": "user", "content": prompt}],
    response_model=JobScoreOutput,
    max_tokens=512,
    max_retries=2,  # Instructor retries on validation failure
)

cost_usd = float(raw_completion._hidden_params.get("response_cost", 0.0))
input_tokens = raw_completion.usage.prompt_tokens
output_tokens = raw_completion.usage.completion_tokens
```

### LiteLLM: Pre-flight Token Counting
```python
# Source: https://docs.litellm.ai/docs/completion/token_usage
import litellm

token_count = litellm.token_counter(
    model="claude-3-haiku-20240307",
    messages=[{"role": "user", "content": prompt}]
)
# Use this to estimate cost before calling, for pre-budget-gate logging
```

### SpendRecord Creation (existing pattern from Phase 1)
```python
# Source: existing jobinator/models/budget.py
from jobinator.models.budget import SpendRecord

spend = SpendRecord(
    job_id=job.id,
    model_name="claude-3-haiku-20240307",
    provider="anthropic",
    operation="score",
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    cost_usd=cost_usd,
)
budget_tracker.record(spend)
```

### StatusEvent for Status Transition (existing pattern)
```python
# Source: existing jobinator/models/job.py — StatusEvent append-only pattern
from jobinator.models.job import StatusEvent

event = StatusEvent(
    job_id=job.id,
    status="scored",
    reason=f"fit_score={score_output.fit_score:.2f}",
)
session.add(event)
session.commit()
```

### Alembic Migration for JobScore Table
```python
# Generate with: alembic revision --autogenerate -m "add_job_score_table"
# Then verify 'import sqlmodel' is present (Phase 1 mako template handles this)
# Run with: alembic upgrade head
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `instructor.from_provider("litellm/...")` | `instructor.from_litellm(litellm.completion)` | Instructor v1.x | `from_litellm` is the stable integration path that exposes raw completion; `from_provider` with litellm prefix may not surface `_hidden_params` reliably |
| Manual JSON parsing of LLM output | Instructor with `response_model=` | Instructor >=1.0 | Automatic retry on validation failure, typed output |
| Separate `anthropic` / `openai` clients | LiteLLM unified client | LiteLLM >=1.0 | Single call surface, cost normalization across providers |

**Deprecated/outdated:**
- `litellm.completion_cost(completion_response=instructor_wrapped_response)`: Returns 0.0 due to instructor wrapper — use `_hidden_params["response_cost"]` instead (confirmed bug, instructor#1330)

## Open Questions

1. **JSON Resume profile location**
   - What we know: `ScoringConfig.profile_path` will point to it; `Settings` has `config_dir` pointing to `~/.config/jobinator/`
   - What's unclear: Whether the user has a JSON Resume file already, and whether Phase 3 should include a `profile init` command or just document the expected path
   - Recommendation: Expect file at `~/.config/jobinator/resume.json`; print clear setup instructions if absent; do not block Phase 3 on profile creation

2. **Priority score formula**
   - What we know: SCOR-04 requires combining fit, urgency, recency, and user preferences into a single `priority_score`
   - What's unclear: Exact weighting — e.g., `0.6 * fit_score + 0.2 * recency_score + 0.2 * urgency`
   - Recommendation: Implement as a configurable weighted formula in `ScoringConfig`; default weights are reasonable guesses, user can tune in config.toml

3. **Fallback when `response_cost` is 0.0**
   - What we know: LiteLLM's pricing table may lag; `response_cost` can be 0.0 for unknown models
   - What's unclear: Whether to hard-fail or soft-warn when cost is 0.0
   - Recommendation: Log a warning when `response_cost == 0.0` but do not hard-fail; record 0.0 in SpendRecord and note in `DecisionLog`

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12.x (via uv) | — |
| uv | Package manager | ✓ | Current | — |
| litellm | INFR-01, INFR-02 | ✗ (not yet installed) | — | None — must install |
| instructor | SCOR-02, SCOR-03 | ✗ (not yet installed) | — | None — must install |
| anthropic | INFR-01 | ✗ (not yet installed) | — | Can fall back to openai only |
| openai | INFR-01 | ✗ (not yet installed) | — | Can fall back to anthropic only |
| tiktoken | INFR-02 | ✗ (not yet installed) | — | `litellm.token_counter()` as fallback |
| ANTHROPIC_API_KEY | Scoring calls (Anthropic) | Unknown | — | Use OpenAI if missing |
| OPENAI_API_KEY | Scoring calls (OpenAI) | Unknown | — | Use Anthropic if missing |

**Missing dependencies with no fallback:**
- At least one of `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` must be set — planner must include a Wave 0 setup step that validates key presence

**Missing dependencies with fallback:**
- litellm, instructor, anthropic, openai, tiktoken — all installable via `uv add` in Wave 0

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` testpaths = ["tests"] |
| Quick run command | `uv run pytest tests/test_scoring.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCOR-02 | LLM returns 0-1 fit score for a job | unit (mocked LLM) | `uv run pytest tests/test_scoring.py::test_score_job_fit_score -x` | ❌ Wave 0 |
| SCOR-03 | Score includes strengths, gaps, comp estimate | unit (mocked LLM) | `uv run pytest tests/test_scoring.py::test_score_job_output_fields -x` | ❌ Wave 0 |
| SCOR-04 | Priority score is computed and stored | unit | `uv run pytest tests/test_scoring.py::test_priority_score -x` | ❌ Wave 0 |
| SCOR-05 | Score includes reasoning paragraph | unit (mocked LLM) | `uv run pytest tests/test_scoring.py::test_score_job_reasoning -x` | ❌ Wave 0 |
| INFR-01 | Cheap model tier is used (not strong model) | unit | `uv run pytest tests/test_scoring.py::test_cheap_model_used -x` | ❌ Wave 0 |
| INFR-02 | SpendRecord is written after scoring call | unit | `uv run pytest tests/test_scoring.py::test_spend_recorded -x` | ❌ Wave 0 |
| INFR-03 | BudgetExceeded raised before LLM call when at limit | unit | `uv run pytest tests/test_scoring.py::test_budget_gate -x` | ❌ Wave 0 (but `test_budget.py` tests BudgetTracker directly) |

**Mocking approach:** Use `unittest.mock.patch` or `respx` to mock `litellm.completion`. Instructor's `from_litellm` wraps `litellm.completion` — mock at the `litellm.completion` level. Return a fake `ModelResponse` with `usage` and `_hidden_params` set.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_scoring.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_scoring.py` — covers SCOR-02 through SCOR-05, INFR-01 through INFR-03
- [ ] `tests/fixtures/sample_resume.json` — minimal JSON Resume for prompt builder tests
- [ ] Wave 0 install: `uv add litellm>=1.40 instructor>=1.4 anthropic>=0.28 openai>=1.30 tiktoken>=0.7`
- [ ] Alembic migration: `alembic revision --autogenerate -m "add_job_score_table"` + `alembic upgrade head`

## Sources

### Primary (HIGH confidence)
- https://python.useinstructor.com/integrations/litellm/ — `from_litellm`, `create_with_completion`, `_hidden_params["response_cost"]` pattern
- https://github.com/BerriAI/litellm/blob/main/docs/my-website/docs/completion/token_usage.md — `completion_cost()`, `token_counter()`, `_hidden_params` field names
- Existing codebase (Phases 1–2) — `BudgetTracker`, `SpendRecord`, `FilterConfig` pattern, `DiscoveryConfig` pattern, Alembic setup

### Secondary (MEDIUM confidence)
- https://docs.litellm.ai/docs/routing — LiteLLM Router model-tiering; relevant for future but direct `litellm.completion(model=...)` is sufficient for Phase 3
- PyPI version checks (2026-04-06): litellm=1.83.3, instructor=1.15.1, tiktoken=0.12.0, anthropic=0.89.0, openai=2.30.0

### Tertiary (LOW confidence — flag for validation)
- STATE.md blocker note: "LiteLLM pricing tables may lag actual provider pricing" — unverified exact lag; treat budget figures as approximate
- GitHub issue instructor#1330: `completion_cost()` returns 0.0 via `from_litellm` — referenced in search results but not directly confirmed against current instructor 1.15.1; use `_hidden_params` regardless

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI; libraries are exact fit for stated requirements
- Architecture patterns: HIGH — `from_litellm` + `create_with_completion` confirmed in official Instructor docs; `SpendRecord` + `BudgetTracker` integration directly inspected from codebase
- Pitfalls: MEDIUM — `completion_cost()` bug and pricing lag are documented in sources but not tested against current installed versions; safe to assume both apply
- LiteLLM pricing accuracy: LOW — per STATE.md blocker and CLAUDE.md confidence assessment

**Research date:** 2026-04-06
**Valid until:** 2026-05-06 (LiteLLM and Instructor move fast; re-verify before planning if > 30 days old)
