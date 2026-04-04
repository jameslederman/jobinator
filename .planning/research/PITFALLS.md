# Domain Pitfalls

**Domain:** Job search automation / AI application optimization pipeline
**Project:** Jobinator
**Researched:** 2026-04-04
**Confidence note:** Web search unavailable during this research pass. Findings are based on training data (cutoff Aug 2025) from post-mortems, community discussions, open-source job automation projects (JobSpy, LazyApply, Discord communities, HN threads), and direct experience with LLM tooling pitfalls. Confidence levels assigned per finding quality.

---

## Critical Pitfalls

Mistakes that cause rewrites, reputational damage, or complete project abandonment.

---

### Pitfall 1: Scraping Fragility as a Load-Bearing Dependency

**Confidence:** HIGH (well-documented across job board communities and open-source scraping projects)

**What goes wrong:** Job board HTML structures change without notice. A single DOM restructure at Indeed, Wellfound, or Greenhouse breaks the entire discovery pipeline. Projects built around tightly-coupled CSS selector scrapers fail silently — returning zero results with no error — or loudly crash every morning.

**Why it happens:** Developers write a scraper that works on day one, test it a few times, then ship it as stable infrastructure. Job boards actively fight scraping (rate limiting, CAPTCHAs, bot fingerprinting) and also do routine frontend deploys with no API-stability guarantees. The scraper is effectively depending on an undocumented, un-versioned interface.

**Consequences:**
- Pipeline runs silently return 0 jobs — hard to distinguish from "no new jobs" vs "scraper is broken"
- A week of missed opportunities before the owner notices
- Constant maintenance burden that crowds out feature development

**Prevention:**
- Treat each source adapter as a replaceable plug-in, not core infrastructure. Source adapters implement a standard interface (`JobSource`) and are independently testable.
- Emit a `source_health` metric: if a source returns 0 results 3 runs in a row, alert loudly.
- For Greenhouse and Lever, use their **unofficial but stable JSON APIs** (`/jobs.json`, `/api/v1/postings`) rather than scraping HTML. These are not officially documented but are far more stable than HTML selectors.
- For HN Who's Hiring, parse the monthly thread text — much more stable than scraping a general job board.
- Wellfound has no public API; HTML scraping is unavoidable. Isolate this adapter and plan for monthly maintenance.

**Detection (warning signs):**
- Source returns exactly 0 results two runs in a row
- `requests` response code 403, 429, or 200 with suspiciously small HTML body
- HTML structure change: `AttributeError` or `NoneType` errors in parser

**Phase to address:** Foundation phase (source adapters). Build health-check assertions into the adapter contract from day one.

---

### Pitfall 2: Rate Limiting and IP Bans Leading to Full Blocks

**Confidence:** HIGH (extensively documented; Indeed and LinkedIn have banned entire IP ranges)

**What goes wrong:** Running discovery in a tight loop without delays triggers rate-limit responses (429), then temporary blocks, then permanent IP bans. For a local tool running on a home IP, a permanent ban is essentially permanent — the user's home IP gets blacklisted.

**Why it happens:** Developers test locally with small batches, see it working, then set the cron job to run every 15 minutes. At scale, that's 96 requests/day to the same endpoint. Job boards actively detect this pattern.

**Consequences:**
- Home IP blocked from job board — affects manual browsing too, not just the tool
- Discovery pipeline silently returns 0 for banned sources
- No clean recovery path — IP rotation for home users is non-trivial

**Prevention:**
- Per-source rate limit configuration with conservative defaults (e.g., Wellfound: max 1 request/5s, no more than 20 pages/session).
- Randomize inter-request delays: `random.uniform(2, 5)` seconds rather than a fixed delay.
- Run discovery sessions at most 1-2x/day, not continuously.
- Respect `Retry-After` headers on 429 responses — exponential backoff with jitter.
- Cache raw HTML/JSON responses locally during development so you're not hitting live endpoints repeatedly.
- Set a realistic `User-Agent` string that doesn't advertise bot behavior.

**Detection (warning signs):**
- Consistent 429 or 403 responses from a source that was working
- Response body contains CAPTCHA challenge HTML
- Suspiciously fast "0 results" — check if you're actually getting blocked HTML back

**Phase to address:** Foundation phase. Rate limiting must be baked into the HTTP layer from day one — retrofitting it is painful.

---

### Pitfall 3: LLM Hallucination in Generated Application Materials

**Confidence:** HIGH (well-documented LLM behavior; specific to resume/cover letter generation)

**What goes wrong:** The LLM invents plausible-sounding but false details in generated resumes and cover letters: wrong dates, fabricated metrics ("increased revenue by 40%"), non-existent technologies in a skill list, incorrect company names or roles, or entirely invented projects. The output reads confidently and the user submits it without noticing.

**Why it happens:** LLMs fill gaps when the input prompt is underspecified. If the job description asks for experience with X and the user's profile JSON doesn't mention X explicitly, the model may infer "close enough" and include it. Cover letters especially encourage creative synthesis that can drift into fabrication.

**Consequences:**
- User submits materials with false claims — discovered in interviews or background checks
- Reputational damage with specific employers
- In regulated industries, this could be legally problematic
- At minimum, wastes the user's time when they get caught

**Prevention:**
- **Strict grounding rule:** All facts in generated materials must be traceable to the source JSON Resume profile. Prompt explicitly: "Only use information from the provided profile. Do not infer, extrapolate, or add information not present."
- **Post-generation fact check:** Run a second LLM call that compares the generated document against the source profile and flags any claim not directly supported. Simple and cheap with a smaller model.
- **No-fabricate validation pass:** Before saving materials, run a structured check for specific hallucination-prone patterns: percentages, dates, company names, technologies.
- Treat generated output as a draft that requires human review — never auto-submit without inspection.
- The human-in-the-loop application mode (already in scope) is the correct default for this reason.

**Detection (warning signs):**
- Generated cover letter mentions specific metrics not in the profile JSON
- Resume lists technologies or tools not in the profile's skills section
- Cover letter addresses the hiring manager by a plausible-but-invented name

**Phase to address:** Materials generation phase. Build the grounding prompt and fact-check pass into generation from the start, not as a post-launch fix.

---

### Pitfall 4: LLM Cost Overruns from Unbudgeted High-Volume Calls

**Confidence:** HIGH (common failure in LLM tooling projects; Claude/GPT-4 pricing is easy to underestimate at scale)

**What goes wrong:** The scoring pipeline processes 50 jobs with Claude Sonnet (full job description + full profile in context) and the daily bill is $15-30. Run that for a week and you've spent more on the tool than it saved. Or a bug causes the agent loop to retry a failed call 100 times.

**Why it happens:** Developers test with 5-10 jobs in development, math looks fine, then enable discovery from 5 sources. 50-200 new jobs/day with large contexts at premium-model prices compounds fast. Retry loops without circuit breakers are a common cause of sudden large bills.

**Consequences:**
- API bill spike that exceeds budget before the tool has proven value
- Provider rate limit hit (OpenAI/Anthropic enforce per-minute token limits separately from billing)
- Retroactive spend discovery — "I had no idea it was costing that much"

**Prevention:**
- **Hard per-job budget cap:** Calculate max cost per job before processing. Refuse to process if the job would exceed the cap (e.g., $0.05/job for scoring, $0.20/job for full generation).
- **Daily spend ceiling:** Track cumulative tokens and dollars per day in SQLite. Halt the pipeline with a clear error message when ceiling is hit.
- **Model tiering (already in scope):** Haiku/GPT-4o-mini for hard filtering and initial scoring — these are 10-50x cheaper than frontier models. Only invoke strong models for jobs that pass pre-filters.
- **Token budget per call:** Count estimated tokens before making API calls. Truncate job descriptions to `max_jd_tokens` (e.g., 2000 tokens) — most of the signal is in the first 1000 tokens anyway.
- **Circuit breaker on retries:** Max 2 retries per LLM call. After that, log the failure and move on. Never loop-retry without a hard counter.
- Track cumulative spend in the DB from day one — this is already in scope and must not be deferred.

**Detection (warning signs):**
- Daily spend significantly higher than expected after first real run
- Agent loop running much longer than expected (potential retry storm)
- Per-job cost log shows outlier jobs consuming 10x expected tokens (usually from very long job descriptions)

**Phase to address:** Foundation phase for budget tracking infrastructure; materials generation phase for per-call budgeting.

---

### Pitfall 5: Stale Job Data Leading to Wasted Application Effort

**Confidence:** HIGH (common failure; job postings close faster than many developers expect)

**What goes wrong:** A job discovered Monday gets scored, queued, and material-generated by Wednesday. The posting was filled or pulled Tuesday. The user applies Thursday to a ghost job. At scale, 20-40% of discovered jobs may be stale within 48-72 hours.

**Why it happens:** Job boards don't reliably surface posting close dates or filled status. Scrapers cache discovered jobs indefinitely. The pipeline treats "discovered" as equivalent to "currently open."

**Consequences:**
- Wasted materials generation cost and user time
- Diluted metrics — apparent "apply" rate doesn't reflect real open positions
- User frustration when links return 404 or "position filled" pages

**Prevention:**
- **TTL on discovered jobs:** Mark jobs as `stale` if not re-seen in source within N days (e.g., 3 days for active boards). Don't generate materials for stale jobs without user confirmation.
- **Freshness field:** Store `first_seen_at` and `last_seen_at` separately. The gap tells you how long the job has been active and whether it's still surfacing.
- **URL liveness check:** Before expensive generation, do a cheap HEAD or GET to the job URL. 404 or redirect to job listing page = stale, skip.
- **Priority on fresh jobs:** Score `last_seen_at` recency as a signal in the priority ranking — freshness matters.

**Detection (warning signs):**
- Job URL returns 404 at application time
- Job description page says "This position has been filled"
- Job has been in `discovered` state for more than 5 days with no re-sighting

**Phase to address:** Discovery / normalization phase. Freshness tracking must be designed into the schema from the start.

---

### Pitfall 6: Poor Deduplication Leading to Duplicate Applications

**Confidence:** HIGH (classic data pipeline problem; severe consequences for applications)

**What goes wrong:** The same job posting appears on Wellfound, the company's Greenhouse ATS, and a job board aggregator. Each source gives it a different URL and slightly different title. The system treats them as three separate jobs, generates three sets of materials, and the user applies to the same role three times from the same company.

**Why it happens:** Naive deduplication matches on URL only. Cross-source duplicates have different URLs, different title formatting, sometimes different description text. Fuzzy matching is deferred as "nice to have."

**Consequences:**
- Multiple applications to same company for same role — appears disorganized or automated to recruiters
- Wasted LLM generation costs on duplicate work
- Corrupted metrics — apparent pipeline throughput looks larger than it is

**Prevention:**
- **Multi-signal deduplication:** Match on `(company_name_normalized, title_normalized)` as a compound key, not URL alone. Normalize: lowercase, strip punctuation, expand abbreviations ("Sr." -> "Senior", "Eng" -> "Engineer").
- **Content hash as secondary signal:** Hash the first 500 chars of job description. Identical-or-near-identical descriptions from different URLs are the same job.
- **Canonical job record:** When duplicates are detected, keep one canonical record and link the other source URLs to it. Don't discard — preserve provenance.
- **Cross-source duplicate report:** Log detected duplicates for inspection. This is also a useful quality signal.
- Do NOT rely on external deduplication libraries — this is simple enough to build correctly and must be domain-aware.

**Detection (warning signs):**
- Same company + similar title appearing from multiple sources in same day's run
- Two jobs with near-identical descriptions but different URLs
- User notices same company name in scored jobs list multiple times

**Phase to address:** Discovery / normalization phase. Deduplication logic must be in the ingestion pipeline, not retrofitted later.

---

## Moderate Pitfalls

### Pitfall 7: Over-Automation Producing Low-Quality Applications

**Confidence:** HIGH (the core tension in all job automation tooling)

**What goes wrong:** The "run --auto" mode generates and queues applications without human review. The cover letters are technically correct but generic. The tailored resume emphasizes the wrong experience for the specific role. The user sends 30 applications, gets 2 responses, assumes the tool doesn't work — but the real problem is the output quality wasn't inspected.

**Why it happens:** Automation is the point, so the human-in-the-loop step feels like friction. Users skip review. The LLM produces plausible output that looks correct at a glance.

**Prevention:**
- Default mode should be `human-in-the-loop`, not `--auto`. Make auto-submit a deliberate opt-in with an explicit warning.
- Display a diff or summary of what was tailored vs. the base resume — makes it easy to spot wrong emphasis without reading everything.
- Score application materials quality (a second LLM pass rating fit of materials to role) before presenting for review. Flag low-confidence tailorings.
- Enforce a minimum review time — don't let the UI rush users through.

**Phase to address:** Application modes phase. Require explicit `--auto` flag; default to interactive review.

---

### Pitfall 8: ATS Keyword Optimization Becoming Gaming Instead of Fit Signal

**Confidence:** MEDIUM (observed pattern in job automation communities; ATS behavior varies by vendor)

**What goes wrong:** The fit scoring optimizes for keyword density match between job description and resume. This rewards stuffing the resume with keywords that technically appear in the profile but aren't genuinely representative of the user's strength. Results in high "fit scores" for poor-fit jobs.

**Why it happens:** Keyword overlap is easy to measure. Semantic fit is harder. Early implementations default to TF-IDF or simple keyword matching.

**Prevention:**
- Fit scoring should be LLM-based semantic evaluation (already in scope), not keyword overlap. Prompt: "Given this person's actual experience and this job's requirements, assess genuine fit — not surface keyword alignment."
- Separate "ATS pass probability" from "genuine fit score" as different signals. ATS pass probability informs whether to include specific keywords in materials; genuine fit score drives prioritization.
- Avoid prompting the LLM to "maximize keyword match" — this produces gaming behavior in the generated materials.

**Phase to address:** Scoring phase.

---

### Pitfall 9: SQLite Concurrency and Schema Migration Debt

**Confidence:** HIGH (SQLite WAL mode and Alembic are well-documented)

**What goes wrong:** The schema evolves across phases (adding `last_seen_at`, `materials_quality_score`, `feedback_outcome`). Without a migration system, schema changes require manual database surgery or wiping the database and losing all historical data.

**Why it happens:** SQLite "just works" for the MVP, so developers skip the migration setup. Alembic feels like overkill for a single-user tool. Then the schema changes and the existing DB is incompatible.

**Prevention:**
- Set up Alembic from day one, even if the first migration is trivial. The cost is 30 minutes; the benefit is never losing your job history.
- SQLite WAL mode (`PRAGMA journal_mode=WAL`) for better read/write concurrency if CLI commands ever run in parallel.
- Version the schema in the DB itself (`schema_version` table) so the tool can detect and refuse to run against an incompatible database.

**Phase to address:** Foundation phase. Schema migration setup is 30 minutes of work that prevents a painful rewrite of historical data.

---

### Pitfall 10: Agent Loop Runaway and Missing Circuit Breakers

**Confidence:** HIGH (well-documented failure mode in custom agent loops)

**What goes wrong:** A custom agent loop encounters a persistent error (LLM returns malformed JSON, tool call fails, job URL times out) and retries indefinitely. On a local machine, this means a process that runs for hours, burns API budget, and potentially corrupts state.

**Why it happens:** Custom loops are written optimistically — "retry until it works" without hard limits. Error states that should terminate the loop instead cause it to spin.

**Prevention:**
- Every tool call in the agent loop gets a hard retry limit (max 2-3 retries).
- Global max iterations per job: if a job takes more than N agent steps to process, mark it `failed` and move on.
- Structured error logging: every failure writes to the DB with error type and context. This enables post-hoc debugging without infinite retries.
- The agent loop should be interruptible with Ctrl+C at any step, with graceful state save.

**Phase to address:** Agent loop / foundation phase.

---

### Pitfall 11: Job Board ToS Violations Creating Legal Exposure

**Confidence:** MEDIUM (varies by jurisdiction and ToS; consult legal counsel for production use)

**What goes wrong:** Most job board Terms of Service prohibit automated scraping. Indeed's ToS explicitly prohibits scraping. LinkedIn's ToS is aggressively enforced (hiQ Labs v. LinkedIn is the landmark case, outcome was mixed). For a personal-use local tool, enforcement risk is low but non-zero.

**Why it happens:** Developers ignore ToS as "unenforceable for personal use." This is often true in practice but not always legally clear.

**Prevention:**
- **For this project specifically:** Personal/single-user local tool materially reduces risk vs. commercial scraping. This is the right call.
- Prefer official APIs and documented endpoints where they exist (Greenhouse `/jobs.json`, Lever `/postings`).
- HN Who's Hiring is community content with permissive norms.
- Wellfound HTML scraping is the highest-risk source — limit session depth and rate.
- Document in the README that this is for personal use only, not redistribution.
- Do NOT build any feature that would allow sharing scraped data with other users.

**Note:** LinkedIn is explicitly out of scope for v1 — this is the right call for both legal and technical reasons.

**Phase to address:** Source adapter phase. Document ToS posture per source before implementing each adapter.

---

## Minor Pitfalls

### Pitfall 12: JSON Resume Schema Drift Between Profile and Generated Materials

**Confidence:** MEDIUM

**What goes wrong:** The user updates their `profile.json` (adds a new job, updates a skill), but the generated materials in `~/jobinator-output/` are based on the old profile. Stale materials get submitted.

**Prevention:**
- Hash the profile at materials generation time. Store the hash in the DB alongside the materials.
- At review/submit time, check if profile hash has changed. If yes, warn the user that materials may be stale and offer to regenerate.

**Phase to address:** Materials generation phase.

---

### Pitfall 13: Fit Score Calibration Drift

**Confidence:** MEDIUM

**What goes wrong:** The LLM scoring prompt produces scores clustered at 0.7-0.9 for most jobs, making prioritization useless. Or it's miscalibrated to flag junior roles as high-fit because the description mentions Python.

**Why it happens:** Fit scoring prompts are written once and never calibrated against real outcomes. The user applies to all "high-fit" jobs and notices 50% are obviously wrong.

**Prevention:**
- Include few-shot examples in the scoring prompt: 2-3 examples of jobs with known fit levels (high/medium/low) specific to this user's profile.
- Score calibration: after 10 scored jobs, display a distribution report. If scores are clustered (std dev < 0.1), the prompt needs adjustment.
- Use the feedback loop (already in scope) — track which "high-fit" jobs led to interviews. This is the ground truth.

**Phase to address:** Scoring phase. Include calibration examples in initial prompt design.

---

### Pitfall 14: Output Directory Sprawl and Unclear Material Versioning

**Confidence:** HIGH (common filesystem organization failure)

**What goes wrong:** `~/jobinator-output/` accumulates hundreds of files with no clear versioning. Which cover letter version was actually submitted? Multiple runs for the same job create overlapping files with timestamp suffixes.

**Prevention:**
- Directory structure: `~/jobinator-output/{company}/{role_slug}/{version}/` where version is an integer.
- DB records the canonical path to each version of generated materials.
- Mark submitted versions in the DB — filesystem structure alone is not enough.

**Phase to address:** Materials generation phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Source adapter implementation | Scraper fragility (Pitfall 1), IP bans (Pitfall 2) | Source health checks, conservative rate limits from day 1 |
| Job ingestion / normalization | Deduplication failures (Pitfall 6), stale data (Pitfall 5) | Multi-signal dedup, freshness TTL in schema |
| Fit scoring | Keyword gaming (Pitfall 8), score calibration drift (Pitfall 13) | Semantic LLM scoring, few-shot calibration examples |
| LLM cost management | Cost overruns (Pitfall 4) | Hard per-job and daily caps before first real run |
| Materials generation | Hallucination (Pitfall 3), profile drift (Pitfall 12) | Grounding prompt + fact-check pass + profile hash |
| Agent loop | Runaway retries (Pitfall 10) | Circuit breakers, hard iteration limits |
| Application modes | Over-automation (Pitfall 7) | Default to human-in-the-loop; explicit --auto opt-in |
| Foundation / DB | Schema migration debt (Pitfall 9) | Alembic from day one |
| Output management | Directory sprawl (Pitfall 14) | Structured versioned directory scheme |

---

## Confidence Assessment

| Pitfall | Confidence | Basis |
|---------|------------|-------|
| Scraper fragility | HIGH | Extensive open-source history (JobSpy, py-jobberwocky), community reports |
| Rate limiting / IP bans | HIGH | Documented enforcement by Indeed, LinkedIn; open-source project READMEs |
| LLM hallucination | HIGH | Core LLM behavior, documented in Anthropic/OpenAI safety literature |
| LLM cost overruns | HIGH | Common failure in LLM tooling; pricing math is deterministic |
| Stale job data | HIGH | Common data pipeline failure; 48-72h TTL is well-known in recruiting |
| Poor deduplication | HIGH | Classic data pipeline problem, well-understood |
| Over-automation | HIGH | Core tension in job automation tooling, universally reported |
| ATS keyword gaming | MEDIUM | Observed pattern, but ATS behavior varies by vendor |
| SQLite migration debt | HIGH | Standard SQLite + SQLAlchemy/Alembic pattern |
| Agent loop runaway | HIGH | Documented in custom agent loop implementations |
| ToS violations | MEDIUM | Legal landscape varies; enforcement risk for personal use is low |
| JSON Resume schema drift | MEDIUM | Specific to this project's architecture |
| Fit score calibration drift | MEDIUM | LLM scoring calibration is project-specific |
| Output directory sprawl | HIGH | Common filesystem organization failure |

---

## Sources

Note: Web search was unavailable during this research pass. Findings are drawn from training data with Aug 2025 cutoff.

- Open-source job automation projects: JobSpy (GitHub), py-jobberwocky, AutoApply community discussions
- HN threads on job automation and job board scraping (2023-2025)
- Anthropic and OpenAI documentation on LLM hallucination and grounding techniques
- hiQ Labs v. LinkedIn (9th Circuit, 2022) — ToS enforcement case law
- General LLM tooling pitfalls literature (Simon Willison's weblog, LLM engineering community)
- SQLAlchemy/Alembic official documentation for SQLite migration patterns

**Recommended verification:** Run web searches for "job scraping rate limiting 2025", "LLM resume hallucination examples", and "Greenhouse Lever API unofficial endpoints" to validate and update these findings with current sources.
