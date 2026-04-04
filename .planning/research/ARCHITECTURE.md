# Architecture Patterns

**Domain:** Local-first agent-driven job search and application automation pipeline
**Project:** Jobinator
**Researched:** 2026-04-04
**Confidence:** HIGH — patterns drawn from well-established Python CLI tooling, pipeline architecture, and custom agent loop design principles

---

## Recommended Architecture

Jobinator is a **pipeline system with an embedded agent loop**, not a monolithic agent. The agent loop is one component that orchestrates tool calls; the surrounding pipeline handles data ingestion, normalization, scoring, and generation independently of the agent. This separation is critical: most work is deterministic pipeline logic that does not require LLM reasoning, and the agent loop is invoked only where tool orchestration or multi-step reasoning is actually needed.

### Layered View

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Click/Typer)                                      │
│  discover | score | apply | run --auto | review              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Orchestrator / Agent Loop                                    │
│  (custom Python, no framework)                               │
│  - Interprets commands                                        │
│  - Routes to pipeline stages                                  │
│  - Invokes LLM with tool dispatch                            │
│  - Enforces budget gate                                       │
└──┬─────────┬──────────┬──────────┬───────────────────────────┘
   │         │          │          │
   ▼         ▼          ▼          ▼
Source    Normalize  Score      Generate
Adapters  Pipeline   Pipeline   Pipeline
   │         │          │          │
   └────┬────┴──────────┴──────────┘
        │
┌───────▼─────────────────────────────────────────────────────┐
│  State Layer (SQLite + SQLModel)                              │
│  jobs | scores | materials | applications | spend | outcomes │
└─────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────┐
│  Output Layer (Filesystem)                                    │
│  ~/jobinator-output/<company>/<role>/                        │
│  resume.json | resume.pdf | cover_letter.md | prep_brief.md  │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

### Component 1: CLI Layer

**Responsibility:** Parse user commands, display output, gate on human confirmation in human-in-the-loop mode. Has no business logic — delegates entirely to the Orchestrator.

**Communicates with:** Orchestrator only (one-way downward).

**Technology:** Typer (preferred over Click — Typer is Pydantic-native, cleaner type annotations, same ergonomics).

**Key commands:**
- `discover` — trigger source adapters, normalize, store raw jobs
- `score` — score unscored jobs (heuristic + LLM)
- `apply [job_id]` — generate materials + initiate application flow
- `run --auto` — discover + score + apply above-threshold jobs in one pass
- `review` — show scored jobs awaiting decision
- `status` — spend summary, pipeline state, recent outcomes

---

### Component 2: Orchestrator / Agent Loop

**Responsibility:** Sequence pipeline stages, manage the LLM conversation context, dispatch tool calls, enforce budget gates, log decisions with reasoning. This is the "brain" of the system.

**Communicates with:** All pipeline components (calls them as tools or directly), LLM Provider Abstraction, State Layer (reads budget, writes decision log).

**Design pattern — custom tool dispatch loop:**

```python
# Core loop pattern (no framework dependency)
class AgentLoop:
    def run(self, task: Task) -> Result:
        messages = [system_prompt, task.to_message()]
        while True:
            # Budget gate — check before every LLM call
            self.budget.assert_within_limits()

            response = self.llm.complete(messages)
            self.budget.record(response.usage)

            if response.is_final:
                return Result(response.content)

            # Tool dispatch
            for tool_call in response.tool_calls:
                tool_result = self.tools[tool_call.name].run(tool_call.args)
                messages.append(tool_call.to_message())
                messages.append(tool_result.to_message())
```

**Tools registered with the agent loop:**
- `search_jobs(source, query, filters)` — delegates to Source Adapters
- `score_job(job_id)` — delegates to Score Pipeline
- `generate_materials(job_id, material_type)` — delegates to Generation Pipeline
- `get_job_details(job_id)` — reads from State Layer
- `log_decision(job_id, decision, reasoning)` — writes to State Layer

**Key invariant:** The agent loop never has direct business logic. It only sequences tools. Business logic lives in the pipeline components.

---

### Component 3: Source Adapters

**Responsibility:** Fetch raw job postings from external sources and return normalized `RawJob` objects. Each adapter is independent; the Orchestrator calls them via the `search_jobs` tool.

**Communicates with:** External APIs/scrapers (outbound), Normalization Pipeline (outbound), State Layer (writes raw jobs, reads seen-job dedup set).

**Adapter interface:**

```python
class SourceAdapter(Protocol):
    source_id: str  # e.g., "wellfound", "greenhouse", "hn_hiring"

    def fetch(self, query: SearchQuery) -> list[RawJob]:
        ...
```

**Adapters to build:**
- `WellfoundAdapter` — Wellfound API or authenticated scrape
- `GreenhouseAdapter` — Greenhouse public job board API (per-company)
- `LeverAdapter` — Lever public job board API (per-company)
- `HNHiringAdapter` — Parses monthly HN Who's Hiring thread via Algolia HN API

**Deduplication:** Before returning, each adapter checks State Layer for `seen_urls`. Duplicate URLs are dropped. Job fingerprint = normalized URL + company slug.

---

### Component 4: Normalization Pipeline

**Responsibility:** Transform `RawJob` (source-specific, unstructured) into `NormalizedJob` (typed, structured, consistent across sources). No LLM calls — pure deterministic transformation.

**Communicates with:** Source Adapters (receives `RawJob`), State Layer (writes `NormalizedJob`).

**NormalizedJob schema:**

```python
class NormalizedJob(SQLModel, table=True):
    id: str                    # uuid
    source: str                # adapter source_id
    source_url: str            # canonical URL (dedup key)
    title: str
    company: str
    company_slug: str          # normalized for filesystem paths
    location: str | None
    remote: bool | None
    salary_min: int | None     # USD annual
    salary_max: int | None
    description: str           # full text
    requirements: list[str]    # extracted bullet points
    posted_at: datetime | None
    fetched_at: datetime
    raw_json: dict             # original payload, always preserved
    status: JobStatus          # seen | scored | applied | rejected | archived
```

**Normalization responsibilities:**
- Title normalization (strip "Sr." vs "Senior", normalize seniority signals)
- Location parsing (extract remote/hybrid/onsite, city/state)
- Salary range extraction (parse "$150k-$200k", "competitive", None)
- Requirements extraction (parse JD bullet points into list)
- Company slug generation (for filesystem paths)

---

### Component 5: Score Pipeline

**Responsibility:** Evaluate job fit in two sequential stages. Stage 1 is heuristic (fast, cheap, no LLM). Stage 2 is LLM-based (slower, higher quality, only for jobs that pass Stage 1).

**Communicates with:** State Layer (reads `NormalizedJob`, writes `JobScore`), LLM Provider Abstraction (Stage 2 only), Budget Tracker (checks before LLM call).

**Two-stage design:**

```
NormalizedJob
    │
    ▼
[Stage 1: Heuristic Filter]  ← no LLM, no cost
    - Hard filters: location/remote match, salary floor, title seniority
    - Keyword blocklist: avoid "junior", "manager", excluded domains
    - Result: PASS | FAIL (with reason)
    │ PASS
    ▼
[Stage 2: LLM Scoring]  ← cheap model (Haiku/GPT-4o-mini)
    - Prompt: profile + job description → structured score JSON
    - Output: score 0-1, strengths[], gaps[], comp_estimate, priority
    - Result: JobScore record
    │
    ▼
[State Layer: write JobScore]
```

**JobScore schema:**

```python
class JobScore(SQLModel, table=True):
    id: str
    job_id: str               # FK to NormalizedJob
    heuristic_pass: bool
    heuristic_fail_reason: str | None
    llm_score: float | None   # 0.0 - 1.0
    strengths: list[str] | None
    gaps: list[str] | None
    comp_estimate: str | None
    priority: int | None      # 1-5
    model_used: str | None
    tokens_used: int | None
    scored_at: datetime
```

**LLM model selection:** Use the cheapest capable model for scoring. Haiku or GPT-4o-mini. The profile context is large but the task is straightforward structured extraction. Stage 2 is the highest-volume LLM operation in the system — model cost matters most here.

---

### Component 6: Generation Pipeline

**Responsibility:** Generate application materials for a specific `NormalizedJob` using a strong LLM. Produces: tailored resume (JSON Resume format), cover letter (Markdown), interview prep brief (Markdown).

**Communicates with:** State Layer (reads `NormalizedJob`, `JobScore`, writes `GeneratedMaterial`), LLM Provider Abstraction (strong model: Claude Sonnet / GPT-4), Budget Tracker, Output Layer (writes files).

**Material generation sequence:**

```
NormalizedJob + JobScore + BaseProfile
    │
    ▼
[Resume Tailoring]  ← Claude Sonnet or GPT-4
    - Input: JSON Resume base profile + job description + score.strengths/gaps
    - Output: tailored JSON Resume (subset of experience emphasized, no fabrication)
    - Render: JSON → PDF/Markdown via resume renderer
    │
    ▼
[Cover Letter Generation]  ← same strong model, same context window
    - Input: tailored resume + job description + company research brief
    - Output: Markdown cover letter (< 350 words, company+role specific)
    │
    ▼
[Interview Prep Brief]  ← same model
    - Input: job description + company + role context
    - Output: Markdown brief (company overview, likely Qs, talking points)
    │
    ▼
[Output Layer: write files]
~/jobinator-output/<company_slug>/<role_slug>/<timestamp>/
    resume.json
    resume.md (or .pdf)
    cover_letter.md
    prep_brief.md
```

**Key constraint:** All three materials for a job can share one extended context window — send them in sequence within the same conversation/context rather than three cold-start prompts. This reduces context re-loading cost and improves coherence between resume and cover letter.

**Truthfulness invariant:** The generation prompt must explicitly instruct the model to emphasize and reframe only skills and experiences that exist in the base profile. No fabrication. Any generated material that introduces experience not in the base profile is a defect.

---

### Component 7: LLM Provider Abstraction

**Responsibility:** Provide a uniform interface for LLM calls across providers (Anthropic, OpenAI). Route calls to the correct provider/model based on the `model_tier` parameter. Track usage for budget.

**Communicates with:** Score Pipeline, Generation Pipeline, Agent Loop (all callers), Budget Tracker (reports usage after every call).

**Interface:**

```python
class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[Message],
        model_tier: Literal["cheap", "strong"],
        tools: list[Tool] | None = None,
        response_format: type[BaseModel] | None = None,
    ) -> LLMResponse:
        ...

@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    model: str          # actual model used
    input_tokens: int
    output_tokens: int
    cost_usd: float     # calculated from provider pricing
```

**Model routing:**

| Tier | Primary | Fallback | Use Case |
|------|---------|---------|----------|
| cheap | claude-haiku-3-5 | gpt-4o-mini | Heuristic-assist scoring, filtering |
| strong | claude-sonnet-4-5 | gpt-4o | Resume/cover letter/prep brief generation |

**Structured output:** Use `response_format` (OpenAI) or tool-use-as-JSON (Anthropic) to enforce typed responses. Never parse free-form LLM text into structured data — always use the provider's structured output mechanism.

---

### Component 8: Budget Tracker

**Responsibility:** Track token and dollar spend per-session and per-job. Enforce configurable daily and per-job limits. Block LLM calls when limits would be exceeded. Persist spend history to State Layer.

**Communicates with:** LLM Provider Abstraction (receives usage after every call), Orchestrator (enforces limits, called as pre-call gate), State Layer (persists spend records).

**Budget model:**

```python
class BudgetConfig(BaseModel):
    daily_limit_usd: float = 5.00
    per_job_limit_usd: float = 0.50
    warn_threshold: float = 0.80  # warn at 80% of limit

class SpendRecord(SQLModel, table=True):
    id: str
    job_id: str | None     # None for non-job-specific spend
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    operation: str         # "score" | "generate_resume" | etc.
    recorded_at: datetime
```

**Limit enforcement:** The Budget Tracker exposes `assert_within_limits(job_id, estimated_cost)` which raises `BudgetExceeded` before the call is made. The Orchestrator calls this before every LLM dispatch. There is no retry — budget exceeded halts the current operation cleanly.

---

### Component 9: State Layer (SQLite + SQLModel)

**Responsibility:** Persistent storage for all system state. Single SQLite file, accessed read-write from all pipeline components. SQLModel provides typed models that double as Pydantic schemas.

**Communicates with:** Every other component (central store).

**Tables:**

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `normalized_job` | Canonical job records | id, source_url (unique), status |
| `job_score` | Scoring results per job | job_id, llm_score, priority |
| `generated_material` | Metadata for generated files | job_id, material_type, file_path |
| `application` | Application tracking | job_id, mode, submitted_at, outcome |
| `spend_record` | Token/cost tracking | job_id, model, cost_usd, operation |
| `decision_log` | Agent reasoning audit | job_id, decision, reasoning, timestamp |
| `outcome` | Interview/offer tracking | job_id, stage, date, notes |

**Migration strategy:** Alembic for schema migrations. Since this is single-user local-first, migrations can be run automatically on startup (no zero-downtime required).

**Concurrency:** SQLite with WAL mode. Since Jobinator is single-process CLI, no concurrent writers. WAL is still preferred to avoid read blocking during long write operations.

---

### Component 10: Output Layer (Filesystem)

**Responsibility:** Write generated application materials to a structured directory tree. Provide deterministic, human-readable paths. Never overwrite — each generation gets a timestamped subdirectory.

**Communicates with:** Generation Pipeline (receives file content), State Layer (paths stored in `generated_material`).

**Directory structure:**

```
~/jobinator-output/
└── <company_slug>/
    └── <role_slug>/
        └── <YYYYMMDD-HHMMSS>/
            ├── resume.json
            ├── resume.md
            ├── cover_letter.md
            └── prep_brief.md
```

**Slug generation:** `company_slug` and `role_slug` are lowercase alphanumeric + hyphens, max 40 chars, generated deterministically from company name and job title. Stored on `NormalizedJob`.

---

## Data Flow

### Discovery Flow

```
CLI: discover
    → Orchestrator
        → SourceAdapter.fetch(query)
            → External API/scraper
            ← RawJob[]
        → NormalizationPipeline.normalize(RawJob[])
            → Dedup check (State Layer)
            → NormalizedJob[]
        → State Layer: insert NormalizedJob (status=seen)
    ← "N new jobs discovered"
```

### Scoring Flow

```
CLI: score
    → Orchestrator
        → State Layer: fetch jobs (status=seen)
        → For each job:
            → ScorePipeline.score_heuristic(job)
                ← HeuristicResult (PASS | FAIL + reason)
            → if PASS:
                → BudgetTracker.assert_within_limits()
                → ScorePipeline.score_llm(job)
                    → LLMProvider.complete(messages, tier="cheap")
                        ← LLMResponse (structured JobScore)
                    → BudgetTracker.record(usage)
                ← JobScore
            → State Layer: insert JobScore, update job status=scored
    ← "N jobs scored, M above threshold"
```

### Application Flow

```
CLI: apply <job_id>  (or auto mode from orchestrator)
    → Orchestrator
        → State Layer: fetch NormalizedJob + JobScore
        → [human-in-the-loop: show score, request confirmation]
        → BudgetTracker.assert_within_limits(per_job)
        → GenerationPipeline.generate(job, ["resume", "cover_letter", "prep_brief"])
            → LLMProvider.complete(messages, tier="strong")
                (resume tailoring)
            → LLMProvider.complete(messages, tier="strong")
                (cover letter, continuing same context)
            → LLMProvider.complete(messages, tier="strong")
                (prep brief, continuing same context)
            → BudgetTracker.record(usage) [after each call]
            → OutputLayer.write(materials, company_slug, role_slug)
        → State Layer: insert GeneratedMaterial records, update job status=applied
        → DecisionLog: record decision + reasoning
    ← "Materials written to ~/jobinator-output/..."
```

### Budget Flow

```
Before any LLM call:
    → BudgetTracker.assert_within_limits(job_id?, estimated_cost?)
        → State Layer: SELECT SUM(cost_usd) WHERE date=today
        → If over daily limit: raise BudgetExceeded
        → If job_id provided: SELECT SUM WHERE job_id=?
        → If over per-job limit: raise BudgetExceeded
        ← OK (continue) | BudgetExceeded (halt)

After any LLM call:
    → LLMProvider returns LLMResponse with usage
    → BudgetTracker.record(SpendRecord)
        → State Layer: insert SpendRecord
```

---

## Suggested Build Order

Dependencies between components determine build order. The State Layer must exist before any component that writes state. The LLM abstraction must exist before Score or Generate pipelines. The CLI is last because it wraps everything.

### Phase 1: Foundation (no LLM, no external calls)

Build in this order — each depends on the previous:

1. **State Layer** — SQLModel models, SQLite setup, Alembic migrations
   - Unblocks: everything else (all components read/write state)
2. **NormalizedJob + JobScore + Material schemas** — Pydantic models (reused by all layers)
   - Unblocks: Normalization Pipeline, Score Pipeline, Generation Pipeline
3. **Normalization Pipeline** — pure Python, no external dependencies
   - Unblocks: Source Adapters (they produce input for this)
4. **Output Layer** — pure filesystem writes
   - Unblocks: Generation Pipeline

### Phase 2: Data Ingestion

5. **Source Adapters** — external API calls, one adapter at a time
   - Build HNHiringAdapter first (Algolia API, no auth, easy to test)
   - Then GreenhouseAdapter / LeverAdapter (public APIs, no auth)
   - Then WellfoundAdapter (may require auth, more complex)
   - Unblocks: end-to-end discovery flow

### Phase 3: LLM Integration

6. **Budget Tracker** — must exist before any LLM call
   - Unblocks: LLM Provider Abstraction, Score Pipeline (LLM stage)
7. **LLM Provider Abstraction** — Anthropic + OpenAI clients, model routing, structured output
   - Unblocks: Score Pipeline (Stage 2), Generation Pipeline
8. **Score Pipeline Stage 2 (LLM)** — depends on Budget Tracker + LLM Abstraction
   - Score Pipeline Stage 1 (heuristic) can be built in Phase 1 without LLM

### Phase 4: Generation and Agent Loop

9. **Generation Pipeline** — depends on LLM Abstraction, Output Layer, Budget Tracker
10. **Agent Loop / Orchestrator** — depends on all pipeline components, Budget Tracker, State Layer
    - Build last — it sequences the other components

### Phase 5: CLI

11. **CLI Layer** — wraps Orchestrator commands, handles human-in-the-loop confirmation
    - Build after Orchestrator so there is something to wire up

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Agent Loop as Monolith

**What:** Putting scoring logic, normalization logic, and generation logic inside the agent loop's prompt or tool implementations.

**Why bad:** The agent loop becomes untestable (requires LLM), expensive (every pipeline operation costs tokens), and opaque (reasoning lives in a black box). Most of Jobinator's work is deterministic — treat it as such.

**Instead:** Agent loop calls pipeline components as black boxes. Pipeline components are pure Python functions testable without any LLM.

---

### Anti-Pattern 2: One Model for Everything

**What:** Using the same strong (expensive) model for both job filtering/scoring and material generation.

**Why bad:** Scoring is high-volume (potentially hundreds of jobs per session). Using Claude Sonnet for scoring burns budget fast and provides marginal quality improvement over Haiku for a structured extraction task.

**Instead:** Hard model tier split. Cheap models for scoring (high volume, low stakes). Strong models for generation (low volume, high stakes output quality).

---

### Anti-Pattern 3: Parsing LLM Free-Form Text

**What:** Sending a prompt and regex-parsing the response to extract score, strengths, gaps.

**Why bad:** Brittle. Model output format changes with prompt variations. Impossible to guarantee schema compliance. Silent data corruption.

**Instead:** Always use structured output — Anthropic tool-use-as-JSON or OpenAI `response_format: {type: "json_schema"}`. Define Pydantic models for every LLM response type.

---

### Anti-Pattern 4: SQLite Without Status State Machine

**What:** Tracking job state with boolean flags (`is_scored`, `is_applied`, etc.).

**Why bad:** Multiple flags create invalid states (scored=True, applied=True, but no materials record). Pipeline logic must check multiple columns.

**Instead:** Single `status` enum column on `NormalizedJob` — `seen | scored | applied | rejected | archived`. Status transitions are the canonical state machine. No compound flag checking.

---

### Anti-Pattern 5: Unversioned Output Files

**What:** Writing `~/jobinator-output/acme/senior-ml-engineer/resume.md` with no versioning — overwriting on regeneration.

**Why bad:** Loses previous generation. Can't diff what changed. Can't compare two tailoring attempts.

**Instead:** Timestamp subdirectory per generation. State Layer `generated_material` table records all paths. The latest is deterministically findable via `ORDER BY created_at DESC LIMIT 1`.

---

### Anti-Pattern 6: Blocking on Budget After Work Is Done

**What:** Recording spend and checking limits after the LLM call completes.

**Why bad:** Can't prevent an over-budget call from happening. Budget limit enforcement must be a pre-call gate, not a post-call audit.

**Instead:** `BudgetTracker.assert_within_limits()` is called before every LLM call. If it raises, the call never happens. Spend is recorded after the call only to update the running total for future gates.

---

## Scalability Considerations

This is a single-user local-first tool. The relevant scaling axis is "jobs per session" not "users."

| Concern | At 50 jobs/session | At 500 jobs/session |
|---------|--------------------|---------------------|
| Scoring LLM cost | ~$0.05 (Haiku) | ~$0.50 (Haiku) — within budget |
| SQLite write throughput | Trivial | Trivial — single writer |
| Normalization performance | Instant | Instant — pure Python |
| Generation cost | $0.10/job (Sonnet) | Selective only — only apply to top 5-10 |
| HN Hiring parser | 1-2s | 1-2s — one thread per month |

No architectural changes needed for the expected usage scale. SQLite handles thousands of job records trivially. The budget tracker naturally caps LLM spend before it becomes a throughput concern.

---

## Component Dependency Graph

```
CLI
 └── Orchestrator / Agent Loop
      ├── Budget Tracker
      │    └── State Layer
      ├── LLM Provider Abstraction
      │    └── Budget Tracker
      ├── Source Adapters
      │    └── Normalization Pipeline
      │         └── State Layer
      ├── Score Pipeline
      │    ├── State Layer
      │    └── LLM Provider Abstraction (Stage 2 only)
      ├── Generation Pipeline
      │    ├── State Layer
      │    ├── LLM Provider Abstraction
      │    └── Output Layer
      └── State Layer
```

---

## Sources

- Architecture derived from project constraints in `.planning/PROJECT.md`
- Custom agent loop pattern: well-established Python tool-dispatch pattern (Anthropic cookbook, OpenAI function calling docs) — HIGH confidence from training data
- SQLModel + SQLite architecture: SQLModel documentation patterns — HIGH confidence
- Two-stage scoring (heuristic → LLM): standard retrieval-augmented pipeline pattern — HIGH confidence
- JSON Resume format: jsonresume.org spec — HIGH confidence
- Structured LLM output (tool-use-as-JSON): Anthropic and OpenAI official documentation — HIGH confidence
- Confidence overall: HIGH — all patterns are well-established; no experimental/unproven techniques recommended
