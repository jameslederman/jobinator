# Phase 2: Data Ingestion - Research

**Researched:** 2026-04-05
**Domain:** HTTP scraping / API integration, adapter pattern, source health monitoring, staleness tracking
**Confidence:** HIGH (Greenhouse/Lever/HN APIs verified), MEDIUM (Wellfound — SPA architecture confirmed fragile)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Target companies in `[discovery]` section of config.toml. No separate config file.
- **D-02:** Each company entry specifies its source explicitly: `greenhouse = ["anthropic", "stripe"]`, `lever = ["figma", "notion"]`. No auto-detection.
- **D-03:** Adapters fetch ALL open roles from each target company. Local heuristic filter (Phase 1) handles relevance. No server-side keyword filtering.
- **D-04:** Default config ships with empty company lists. User populates their own targets.
- **D-05:** Build Wellfound scraper using httpx + BS4, accept fragility. Mark adapter as fragile in code. Include health checks so breakage is immediately obvious.
- **D-06:** Wellfound uses two discovery modes: keyword search AND company page scraping. Both combined for comprehensive coverage.
- **D-07:** `discover` command runs all configured sources by default. `--source greenhouse` flag available to run a single source.
- **D-08:** Staleness TTL configurable in config.toml (`stale_after_days = 14`). Jobs not re-sighted within TTL get a stale flag. Default 14 days.
- **D-09:** Source failures log warning and continue to other sources. Use tenacity for retries (3 attempts, exponential backoff). Surface failure in CLI output summary.
- **D-10:** Discovery runs sources sequentially (sync httpx). No async complexity for v1.

### Claude's Discretion

- Adapter base class/protocol design and module structure
- HN Who's Hiring thread selection strategy (latest vs configurable months, Algolia API query approach)
- Exact TOML config key names and structure within `[discovery]`
- Health alert implementation for consecutive zero-result runs (success criteria #4)
- Rate limiting / request throttling approach per source

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DISC-01 | User can discover jobs from Wellfound/AngelList with structured output | Wellfound SPA architecture documented; `__NEXT_DATA__` extraction pattern confirmed; keyword search and company pages both accessible without auth |
| DISC-02 | User can discover jobs from Greenhouse/Lever ATS career pages with structured output | Greenhouse API verified: `boards-api.greenhouse.io/v1/boards/{board_token}/jobs`; Lever API verified: `api.lever.co/v0/postings/{company}`; both public, no auth required |
| DISC-03 | User can discover jobs from HN Who's Hiring threads with structured output | HN Algolia API verified: `hn.algolia.com/api/v1/search`; query `author_whoishiring` + `tags=story` to find thread; `items/{id}` endpoint to fetch comments |
</phase_requirements>

---

## Summary

Phase 2 builds source adapters for three job discovery channels — Greenhouse/Lever ATS APIs, HN Who's Hiring, and Wellfound — wires them into a `discover` CLI command, and integrates with the existing normalization/dedup pipeline from Phase 1. The adapters produce `list[RawJobDict]` which flows directly into `normalize_job()` and `is_duplicate()` already built in Phase 1. No LLM calls in this phase.

Greenhouse and Lever both expose reliable public JSON APIs that require no authentication. The HN Algolia API is stable and publicly documented; the strategy is to query for the most recent `whoishiring` story, fetch its comments, parse each comment as a job posting. Wellfound is the problem child: it's a Next.js SPA that embeds all page data in a `__NEXT_DATA__` JSON blob in the HTML. This is accessible without login but is fragile — the data graph structure can change without notice. Wellfound is intentionally marked as fragile in code (per D-05).

The discover orchestration layer loads company lists from config.toml, calls each adapter sequentially, pipes results through normalize + dedup, persists new records, updates `last_seen_at` on re-sighted jobs, and runs stale-marking against the configured TTL. A source health tracker counts consecutive zero-result runs and fires a Rich alert at run 3.

**Primary recommendation:** Build adapters in order HN → Greenhouse → Lever → Wellfound. HN is the easiest to test (no per-company config needed), Greenhouse/Lever are reliable APIs, Wellfound is last because it is highest-maintenance.

---

## Standard Stack

### Core (not yet in pyproject.toml — must be added in Wave 0)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | >=0.28.1 | HTTP client for API + scraping | Sync and async capable; already specified in CLAUDE.md; cleaner API than requests |
| beautifulsoup4 | >=4.14.3 | HTML parsing for Wellfound | Standard; pairs with lxml backend |
| lxml | >=6.0.2 | BS4 parser backend | Faster and more robust than html.parser for malformed HTML |
| tenacity | >=9.1.4 | Retry logic with exponential backoff | Composable decorators; already specified in CLAUDE.md |
| python-dateutil | >=2.9.0 | Flexible date string parsing | Already used in normalize.py; handles all job board date formats |

### Testing Only (not yet in dev dependencies)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| respx | >=0.22.0 | httpx mock router for tests | More flexible URL pattern routing than pytest-httpx; specified in CLAUDE.md |

### Already Present (no action needed)

| Library | Purpose | Current Version in pyproject.toml |
|---------|---------|-----------------------------------|
| rapidfuzz | Dedup fuzzy matching | >=3.9 (already installed) |
| rich | Terminal output for alerts | >=13.7 (already installed) |
| typer | CLI framework | >=0.12 (already installed) |

**Installation (Wave 0 task):**
```bash
uv add httpx>=0.28.1 beautifulsoup4>=4.14.3 lxml>=6.0.2 tenacity>=9.1.4 python-dateutil>=2.9.0
uv add --dev respx>=0.22.0
```

**Version verification confirmed:** All versions above verified against PyPI registry on 2026-04-05.

---

## Architecture Patterns

### Recommended Module Structure

```
src/jobinator/
├── adapters/                    # NEW — source adapters (Claude's discretion: adapters/ not tools/)
│   ├── __init__.py
│   ├── base.py                  # SourceAdapter Protocol + RawJobDict type alias
│   ├── greenhouse.py            # GreenhouseAdapter
│   ├── lever.py                 # LeverAdapter
│   ├── hn_hiring.py             # HNHiringAdapter
│   └── wellfound.py             # WellfoundAdapter (fragile — marked in code)
├── pipelines/
│   ├── discover.py              # NEW — discovery orchestrator (load config, run adapters, persist)
│   ├── normalize.py             # EXISTS — no changes needed
│   ├── dedup.py                 # EXISTS — no changes needed
│   └── filter.py                # EXISTS — no changes needed
├── configs/
│   └── settings.py              # EXISTS — extend Settings with DiscoveryConfig
└── cli.py                       # EXISTS — add `discover` command
```

### Pattern 1: SourceAdapter Protocol

**What:** A structural Protocol (not ABC) defines the adapter interface. Concrete adapters implement `fetch() -> list[RawJobDict]` without subclassing.

**When to use:** All source adapters. Protocol enables duck typing — adapters can be tested independently without registering with a base class.

```python
# Source: ARCHITECTURE.md pattern + Python typing.Protocol docs
from typing import Protocol
from jobinator.pipelines.normalize import RawJobDict

class SourceAdapter(Protocol):
    source_id: str  # "greenhouse", "lever", "hn_hiring", "wellfound"
    fragile: bool   # True for Wellfound — signals health monitoring priority

    def fetch(self) -> list[RawJobDict]:
        """Return raw job dicts for all configured targets."""
        ...
```

### Pattern 2: Greenhouse Adapter

**What:** Per-company HTTP GET to Greenhouse public board API. `?content=true` adds description. Pagination by iterating until `meta.total` is satisfied.

**Endpoint (verified):** `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`

**Response fields (verified):**
- `jobs[].id` — numeric job ID
- `jobs[].title` — job title
- `jobs[].updated_at` — ISO datetime
- `jobs[].location.name` — location string
- `jobs[].absolute_url` — canonical job URL
- `jobs[].content` — HTML job description (only with `?content=true`)
- `jobs[].departments[].name` — department name
- `meta.total` — total job count

**RawJobDict mapping:**
```python
{
    "title": job["title"],
    "company": company_name,   # from config, not returned by API
    "description": BeautifulSoup(job.get("content", ""), "lxml").get_text(),
    "source_url": job["absolute_url"],
    "location": job["location"]["name"] if job.get("location") else None,
    "posted_at": job.get("updated_at"),  # best available proxy for posted date
}
```

**No auth required (verified).** No official rate limit documented. Use conservative 0.5s inter-request delay.

### Pattern 3: Lever Adapter

**What:** Per-company HTTP GET to Lever public postings API. Offset pagination with `skip` + `limit`.

**Endpoint (verified):** `GET https://api.lever.co/v0/postings/{company}?mode=json&skip=0&limit=50`

**Response fields (verified):**
- `[].id` — UUID
- `[].text` — job title
- `[].categories.location` — location string
- `[].categories.team` — team/department
- `[].workplaceType` — "on-site", "remote", "hybrid", "unspecified"
- `[].descriptionPlain` — full job description in plaintext
- `[].lists[].text` / `[].lists[].content` — supplemental sections (requirements, benefits)
- `[].hostedUrl` — canonical job URL
- `[].applyUrl` — application URL
- `[].salaryRange` — object with `currency`, `interval`, `min`, `max` (optional)

**RawJobDict mapping:**
```python
{
    "title": posting["text"],
    "company": company_name,   # from config
    "description": posting.get("descriptionPlain", ""),
    "source_url": posting["hostedUrl"],
    "location_raw": posting.get("categories", {}).get("location"),
    "salary_raw": posting.get("salaryRange"),  # already a dict — parse_salary handles it
    "posted_at": None,   # Lever API does not expose posted date in public endpoint
}
```

**No auth required (verified).** Rate limit: 2 POST requests/second (applies only to application submission, not GET).

### Pattern 4: HN Who's Hiring Adapter

**What:** Two-step process. Step 1: find the latest "Ask HN: Who is Hiring?" story ID using Algolia search. Step 2: fetch all top-level comments from that story via HN items API.

**Step 1 — Find latest thread (verified):**
```python
# Algolia search for whoishiring stories, sorted by date
# Source: Algolia HN Search API (hn.algolia.com/api/v1)
url = "https://hn.algolia.com/api/v1/search_by_date"
params = {
    "tags": "story,author_whoishiring",
    "hitsPerPage": 1,
}
# hits[0]["objectID"] is the story ID
```

**Step 2 — Fetch all comments:**
```python
# Fetch the story object which includes children comment IDs
url = f"https://hn.algolia.com/api/v1/items/{story_id}"
# response["children"] is list of top-level comment objects
# Each comment: {"id", "text" (HTML), "author", "created_at", "children": [...]}
```

**Comment parsing strategy:** Each top-level comment is one job posting. Comments are free-text HTML (e.g., "Anthropic | Senior ML Engineer | Remote | $200k-$250k | ..."). Parse by extracting plain text from HTML (BS4), then use heuristic field extraction with regex: pipe-delimited segments often encode company | title | location | salary | apply_url.

**RawJobDict mapping:**
```python
{
    "title": extracted_title_or_first_segment,
    "company": extracted_company_or_first_segment,
    "description": full_comment_text,
    "source_url": f"https://news.ycombinator.com/item?id={comment_id}",
    "location_raw": extracted_location,
    "salary_raw": extracted_salary_string,
    "posted_at": comment["created_at"],
}
```

**Configurable months:** Claude's discretion. Recommendation: default to latest 1 thread; config option `hn_months_back = 1` to fetch N previous months (capped at 3 to avoid stale data).

**No auth required. HN Algolia API is stable and officially maintained (HIGH confidence).**

### Pattern 5: Wellfound Adapter (Fragile)

**What:** Next.js SPA that embeds page data as JSON in `<script id="__NEXT_DATA__">` HTML tag. Extract the JSON blob, navigate the Apollo state graph to find job listing nodes.

**Architecture confirmed (MEDIUM confidence — site structure can change without notice):**
- Wellfound renders initial data in `__NEXT_DATA__` JSON blob in HTML response
- Data uses Apollo GraphQL client caching: top-level `props.pageProps.apolloState` object
- Job listing nodes are referenced as `"JobListingSearchResult:{id}"` keys
- Must implement custom unpacking: collect all keys matching `JobListingSearchResult:*`, dereference ID-based pointers

**Keyword search URL (no auth required, verified):**
```
GET https://wellfound.com/role/data-scientist?page=1
GET https://wellfound.com/role/l/machine-learning-engineer/remote?page=1
```

**Company page URL (no auth required, verified):**
```
GET https://wellfound.com/company/{slug}/jobs
```

**Extraction pattern:**
```python
import json
from bs4 import BeautifulSoup

resp = httpx.get(url, headers={"User-Agent": USER_AGENT})
soup = BeautifulSoup(resp.text, "lxml")
script_tag = soup.find("script", id="__NEXT_DATA__")
data = json.loads(script_tag.string)
apollo_state = data["props"]["pageProps"]["apolloState"]
job_nodes = {k: v for k, v in apollo_state.items() if k.startswith("JobListingSearchResult:")}
```

**Mark fragile in code (per D-05):**
```python
class WellfoundAdapter:
    source_id = "wellfound"
    fragile = True  # SPA structure may change; health monitoring is critical
    FRAGILE_NOTICE = "Wellfound adapter uses __NEXT_DATA__ extraction. May break on site updates."
```

**Rate limiting:** Wellfound has anti-scrape measures (IP rate limiting, CAPTCHA on suspicious activity). Use randomized delays `random.uniform(3, 7)` seconds between requests. Do not exceed 20 pages per session. Set realistic User-Agent.

### Pattern 6: Discovery Orchestrator

**What:** `pipelines/discover.py` function that loads config, instantiates adapters, runs them sequentially, pipes results through Phase 1 pipeline, persists records, marks stale jobs.

```python
# Source: ARCHITECTURE.md discovery flow
def run_discovery(session: Session, settings: Settings) -> DiscoveryResult:
    """Run all configured source adapters and persist results."""
    adapters = build_adapters(settings)
    health = load_source_health(session)

    for adapter in adapters:
        try:
            raw_jobs = adapter.fetch()
            new_count, dedup_count = persist_jobs(session, raw_jobs, adapter.source_id)
            health.record_success(adapter.source_id, new_count)
        except Exception as e:
            log.warning(f"Source {adapter.source_id} failed: {e}")
            health.record_failure(adapter.source_id)

    mark_stale_jobs(session, stale_after_days=settings.discovery.stale_after_days)
    fire_health_alerts(health)   # Rich warning if 3 consecutive zero-result runs
    return DiscoveryResult(...)
```

### Pattern 7: Persist + Stale Flow

**What:** For each normalized job: check `is_duplicate()` against existing keys. If new: `session.add()` + `StatusEvent(status="discovered")`. If existing: update `last_seen_at` only.

```python
def persist_jobs(session: Session, raw_jobs: list[RawJobDict], source: str) -> tuple[int, int]:
    existing_keys = get_existing_job_keys(session)
    new_count = dedup_count = 0

    for raw in raw_jobs:
        job = normalize_job(raw, source)
        is_dup, reason = is_duplicate(job.company_slug, job.title_normalized,
                                       job.description_hash, existing_keys)
        if is_dup:
            # Update last_seen_at on the existing record
            update_last_seen(session, job.company_slug, job.title_normalized)
            dedup_count += 1
        else:
            session.add(job)
            session.add(StatusEvent(job_id=job.id, status="discovered"))
            existing_keys.append({...})  # add to in-memory set for this run
            new_count += 1

    session.commit()
    return new_count, dedup_count
```

**Stale marking:**
```python
def mark_stale_jobs(session: Session, stale_after_days: int) -> int:
    """Mark jobs not re-sighted within TTL as stale."""
    cutoff = datetime.utcnow() - timedelta(days=stale_after_days)
    statement = (
        select(NormalizedJob)
        .where(NormalizedJob.last_seen_at < cutoff)
        .where(NormalizedJob.is_stale == False)  # noqa
    )
    jobs = session.exec(statement).all()
    for job in jobs:
        job.is_stale = True
    session.commit()
    return len(jobs)
```

**IMPORTANT:** `NormalizedJob` needs an `is_stale: bool` field (default `False`) added to the model and a new Alembic migration. This is Wave 0 work.

### Pattern 8: Source Health Tracking

**What:** Track consecutive zero-result runs per source. If source returns > 0 jobs OR errors, reset counter. At 3 consecutive zero-result runs, fire a Rich warning. Persist state across CLI invocations.

**Storage options (Claude's discretion):** Simplest is a `source_health` SQLite table or a JSON sidecar file in `~/.config/jobinator/source_health.json`. Recommendation: JSON sidecar (simpler, no migration needed, not critical data).

```python
# Simplified health alert logic
def fire_health_alerts(health: SourceHealth, console: Console) -> None:
    for source_id, consecutive_zeros in health.items():
        if consecutive_zeros >= 3:
            console.print(
                f"[bold yellow]WARNING[/bold yellow] Source '{source_id}' "
                f"returned 0 results for {consecutive_zeros} consecutive runs. "
                "Check adapter health or configuration.",
                style="yellow"
            )
```

### Pattern 9: DiscoveryConfig Extension

**What:** New Pydantic model `DiscoveryConfig` nested in Settings. Loaded from `[discovery]` section of config.toml.

```python
class DiscoveryConfig(BaseModel):
    """Discovery configuration from [discovery] section of config.toml."""
    greenhouse: list[str] = Field(default_factory=list)  # e.g. ["anthropic", "stripe"]
    lever: list[str] = Field(default_factory=list)        # e.g. ["figma", "notion"]
    wellfound_keywords: list[str] = Field(default_factory=list)  # keyword search terms
    wellfound_companies: list[str] = Field(default_factory=list) # company slugs
    stale_after_days: int = 14
    hn_months_back: int = 1    # how many past Who's Hiring threads to fetch
    rate_limit_delay_min: float = 2.0
    rate_limit_delay_max: float = 5.0
```

**Config.toml example:**
```toml
[discovery]
greenhouse = ["anthropic", "stripe"]
lever = ["figma", "notion"]
wellfound_keywords = ["data scientist", "ml engineer", "machine learning"]
wellfound_companies = ["openai", "cohere"]
stale_after_days = 14
hn_months_back = 1
```

### Pattern 10: CLI `discover` Command

**What:** Typer command wired to `run_discovery()`. `--source` flag for single-source runs.

```python
# In cli.py
import typer
from typing import Optional

@app.command()
def discover(
    source: Optional[str] = typer.Option(None, "--source", help="Run a single source (greenhouse, lever, hn_hiring, wellfound)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch but do not persist"),
) -> None:
    """Discover new jobs from all configured sources."""
    ...
```

### Anti-Patterns to Avoid

- **Auto-detect ATS from company domain:** Wastes API calls trying Greenhouse, then Lever, then giving up. D-02 locks explicit source-per-company config.
- **Per-page dedup only:** Calling `get_existing_job_keys()` once per adapter run (not per page) avoids N+1 DB queries. Load all keys once before the loop.
- **Scraping HTML for Greenhouse/Lever:** Both have stable JSON APIs — never scrape their HTML.
- **Storing raw HTML in `raw_json`:** Only store the extracted job dict, not the full page HTML. `raw_json` in NormalizedJob stores the `RawJobDict`, not the source page.
- **Single User-Agent for all sources:** Wellfound bot detection checks UA strings. Use a realistic browser UA only for Wellfound, not for Greenhouse/Lever APIs.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retries with backoff | Custom retry loop | tenacity `@retry(wait=wait_exponential(...), stop=stop_after_attempt(3))` | Edge cases: status 429, connection reset, timeout — tenacity handles all variants |
| Date string parsing | Custom regex for "2 days ago", "Jan 5, 2025", ISO dates | python-dateutil `dateutil.parser.parse()` | Already used in normalize.py; handles 100+ date formats including relative dates |
| httpx test mocking | Manual mock objects | respx `MockRouter` | respx routes by URL pattern, method, request body — exact match or regex; resurrects httpx transport layer cleanly |
| HTML entity decoding | Custom HTML cleaning | BeautifulSoup `.get_text()` with `lxml` parser | Handles `&amp;`, `&#x27;`, encoded Unicode, and nested tags in one call |

**Key insight:** The hard problems in this phase are not HTTP or parsing — they are schema mapping (each source uses different field names) and dedup (same job on two sources has different URLs). Both are already solved in Phase 1. Adapters just need to produce valid `RawJobDict` values.

---

## Common Pitfalls

### Pitfall 1: Greenhouse `board_token` vs Company Slug

**What goes wrong:** The Greenhouse `board_token` in the API URL is NOT always the company's common name or slug. "Anthropic Inc." uses board token `anthropic`, but some companies use `companyname-engineering` or an opaque ID.

**Why it happens:** Greenhouse lets companies configure their own board token. There's no lookup API — you must know the token in advance.

**How to avoid:** Document this clearly in config.toml comments. Recommend users verify their target company's board token by visiting `https://boards.greenhouse.io/{token}` before adding it to config. Provide a `discover --verify-boards` subcommand or just a note in CLI help text.

**Warning signs:** 404 from `boards-api.greenhouse.io/v1/boards/{token}/jobs` means wrong board token, not "company not on Greenhouse."

### Pitfall 2: HN Comment Parsing Quality

**What goes wrong:** HN job comments are entirely free-text. Many follow the pattern "Company | Role | Location | Salary | URL" but many do not. About 20-30% of comments in a typical Who's Hiring thread are replies, meta-discussions, or non-job content.

**Why it happens:** HN has no posting schema. The pipe-delimited convention is community-emergent, not enforced.

**How to avoid:** Accept low field extraction quality for HN jobs. The full comment text goes into `description` (which is used for scoring). Only extract fields that appear reliably in the first line (company, title). Use `source = "hn_hiring"` and accept that `salary_raw`, `location_raw` will often be None for HN jobs. Dedup handles re-posts correctly since `source_url` = comment URL (unique per comment).

**Warning signs:** Large number of HN jobs with empty `title` field indicates parsing failure, not source breakage.

### Pitfall 3: Wellfound `__NEXT_DATA__` Structure Instability

**What goes wrong:** Wellfound deploys a new frontend version and the `apolloState` key structure changes. The adapter silently returns 0 jobs because `JobListingSearchResult:` key prefix no longer exists or the data graph structure is different.

**Why it happens:** `__NEXT_DATA__` is an internal implementation detail of Next.js SSR hydration, not a public API. Wellfound has no obligation to maintain its structure.

**How to avoid:** Health monitoring (3 consecutive zero runs = alert). Add an explicit assert at adapter load time: if no `__NEXT_DATA__` script tag found, raise `AdapterBrokenError` immediately (do not silently return empty list). Log the raw HTML snippet for debugging when extraction fails.

**Warning signs:** `script_tag` is None, or `apolloState` key missing from `__NEXT_DATA__`, or zero `JobListingSearchResult` keys found despite successful HTTP response.

### Pitfall 4: Cross-Source Dedup Performance

**What goes wrong:** `get_existing_job_keys()` is called N times during a discovery run (once per job), resulting in thousands of SELECT queries against SQLite for a large database.

**Why it happens:** Naive implementation calls `get_existing_job_keys()` inside the per-job loop.

**How to avoid:** Call `get_existing_job_keys()` ONCE per adapter run to load all keys into memory. Update the in-memory set as new jobs are added. This is O(1) for subsequent dedup checks within the same run. With thousands of jobs the in-memory set is still <10MB.

### Pitfall 5: Lever `posted_at` is Not Available

**What goes wrong:** Lever's public postings API does not include a `posted_at` or `createdAt` field in the response. Jobs appear without a `posted_at` date, causing stale-detection logic to treat all Lever jobs as stale immediately if the field is required.

**Why it happens:** Lever's public API intentionally omits the posting date from the public endpoint.

**How to avoid:** Set `posted_at = None` for Lever jobs. The staleness TTL logic uses `last_seen_at`, not `posted_at` — so this is handled correctly as long as stale detection uses `last_seen_at` (which it does). Document the absence in adapter code comments.

### Pitfall 6: Source Failure Masking Other Sources

**What goes wrong:** An uncaught exception in the Wellfound adapter aborts the entire discovery run, so Greenhouse and HN jobs are never fetched.

**Why it happens:** Sequential execution without per-adapter exception isolation.

**How to avoid:** Wrap each adapter call in try/except. Log the exception with the source name. Continue to next adapter. Surface the failure in the DiscoveryResult summary shown to the user (D-09). This is the correct behavior per locked decisions.

### Pitfall 7: config.toml `[discovery]` Section Not Present

**What goes wrong:** User hasn't added a `[discovery]` section to config.toml. pydantic-settings raises a validation error instead of using defaults, blocking the first run.

**Why it happens:** pydantic-settings with TomlConfigSettingsSource will parse only keys that are present; missing sections should default gracefully if handled correctly. But nested Pydantic models in Settings require careful handling.

**How to avoid:** `DiscoveryConfig` should be a standalone `BaseModel` (same pattern as `FilterConfig` in Phase 1 — confirmed working pattern from STATE.md learnings). Load it via a `get_discovery_config()` factory that catches missing config gracefully and returns defaults. Do NOT embed it as a nested field in `Settings` if TOML parsing of nested models is fragile.

---

## Code Examples

### Greenhouse API call (verified endpoint)
```python
# Source: developers.greenhouse.io/job-board.html — verified 2026-04-05
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def fetch_greenhouse_jobs(board_token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    resp = httpx.get(url, params={"content": "true"}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()["jobs"]
```

### Lever API call (verified endpoint)
```python
# Source: github.com/lever/postings-api — verified 2026-04-05
def fetch_lever_postings(company: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{company}"
    resp = httpx.get(url, params={"mode": "json", "limit": 50}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()
```

### HN Algolia thread discovery (verified API)
```python
# Source: hn.algolia.com/api/v1 — structure verified 2026-04-05
def find_latest_hn_hiring_thread() -> int:
    """Return story_id of the most recent Ask HN: Who is Hiring? post."""
    resp = httpx.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"tags": "story,author_whoishiring", "hitsPerPage": 1},
        timeout=15.0,
    )
    resp.raise_for_status()
    hits = resp.json()["hits"]
    if not hits:
        raise RuntimeError("No Who is Hiring thread found via Algolia")
    return int(hits[0]["objectID"])


def fetch_hn_thread_comments(story_id: int) -> list[dict]:
    """Return top-level comments from the Who is Hiring thread."""
    resp = httpx.get(
        f"https://hn.algolia.com/api/v1/items/{story_id}",
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("children", [])
```

### Wellfound `__NEXT_DATA__` extraction
```python
# Source: scrapfly.io/blog analysis — MEDIUM confidence (SPA structure can change)
import json
from bs4 import BeautifulSoup

def extract_wellfound_next_data(html: str) -> dict:
    """Extract __NEXT_DATA__ JSON blob from Wellfound HTML response."""
    soup = BeautifulSoup(html, "lxml")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag is None:
        raise AdapterBrokenError("Wellfound __NEXT_DATA__ script tag not found. Adapter may be broken.")
    return json.loads(script_tag.string)


def extract_job_nodes(next_data: dict) -> list[dict]:
    """Navigate Apollo state graph to find job listing nodes."""
    apollo_state = next_data["props"]["pageProps"]["apolloState"]
    return [
        v for k, v in apollo_state.items()
        if k.startswith("JobListingSearchResult:")
    ]
```

### respx mock for testing
```python
# Source: respx docs (github.com/lundberg/respx) — HIGH confidence
import respx
import httpx
import pytest

@pytest.fixture
def greenhouse_mock():
    with respx.mock:
        respx.get("https://boards-api.greenhouse.io/v1/boards/anthropic/jobs").mock(
            return_value=httpx.Response(200, json={
                "jobs": [
                    {"id": 1, "title": "ML Engineer", "absolute_url": "https://...", ...}
                ],
                "meta": {"total": 1}
            })
        )
        yield
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AngelList API (deprecated) | Wellfound `__NEXT_DATA__` scraping | 2022 (Wellfound rebrand) | No public API; scraping is the only option |
| JobSpy-style multi-source aggregator | Per-source custom adapters | Ongoing | JobSpy has ToS issues + maintenance burden; custom adapters give control |
| Greenhouse HTML scraping | Greenhouse `/jobs.json` public API | ~2018 | API is stable; HTML scraping is unnecessary |
| Requests library | httpx | 2023+ | httpx async-capable, better timeout semantics; async migration path open |

**Deprecated/outdated:**
- AngelList v1 API: completely retired, replaced by Wellfound with no public API
- Wellfound iOS API endpoints: unofficial endpoints found in old repos often 403 in 2025 — do not use
- `requests` for new HTTP code: httpx is the correct default per CLAUDE.md

---

## Open Questions

1. **Greenhouse board token validation**
   - What we know: board token is configured by each company; 404 means wrong token
   - What's unclear: is there a way to search for a company's board token programmatically?
   - Recommendation: No lookup API exists. Document the manual verification step in CLI help. Consider adding a `jobinator discover --verify-config` subcommand in a later phase.

2. **Wellfound keyword search result completeness**
   - What we know: `/role/data-scientist` returns paginated results; `__NEXT_DATA__` is accessible without login
   - What's unclear: does Wellfound show all remote jobs in keyword search, or only jobs near a geolocation? Is there a location=remote filter parameter?
   - Recommendation: Test manually before implementing. Start with `/role/l/machine-learning-engineer/remote` pattern for remote-filtered results. Accept incomplete coverage for v1.

3. **HN comment parsing edge cases**
   - What we know: ~70-80% of comments follow pipe-delimited format; 20-30% are noise or replies
   - What's unclear: best heuristic to distinguish job posts from meta-comments (reply indicators, thread depth)
   - Recommendation: Filter to `children` at depth=1 (top-level comments only, not nested replies). Accept that some noise will reach the normalize/filter pipeline — heuristic filter will reject non-job entries.

4. **`is_stale` field — NormalizedJob schema migration**
   - What we know: NormalizedJob in Phase 1 has no `is_stale` field; Phase 2 needs it
   - What's unclear: will Alembic autogenerate correctly detect the new boolean column with `False` default?
   - Recommendation: Add `is_stale: bool = Field(default=False)` to NormalizedJob. Run `alembic revision --autogenerate -m "add is_stale to normalized_job"`. Based on Phase 1 learnings (STATE.md): bake `import sqlmodel` into `script.py.mako` template before autogenerate.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Check below | — | — |
| httpx | HTTP calls | Not installed (not in pyproject.toml yet) | — | Wave 0: `uv add httpx>=0.28.1` |
| beautifulsoup4 | Wellfound parsing | Not installed | — | Wave 0: `uv add beautifulsoup4>=4.14.3` |
| lxml | BS4 backend | Not installed | — | Wave 0: `uv add lxml>=6.0.2` |
| tenacity | Retry logic | Not installed | — | Wave 0: `uv add tenacity>=9.1.4` |
| python-dateutil | Date parsing | Not installed | — | Wave 0: `uv add python-dateutil>=2.9.0` |
| respx | Test mocking | Not installed | — | Wave 0: `uv add --dev respx>=0.22.0` |
| Greenhouse API | DISC-02 | Public, no auth | — | — |
| Lever API | DISC-02 | Public, no auth | — | — |
| HN Algolia API | DISC-03 | Public, no auth | — | — |
| Wellfound | DISC-01 | Public HTML, no auth required | — | Fallback: skip wellfound adapter in v1 (fragile) |

**Missing dependencies with no fallback:**
- None blocking — all packages are addable via `uv add`; all external APIs are public with no auth

**Missing dependencies with fallback:**
- All scraping packages are missing from pyproject.toml. Wave 0 must add them before any adapter code.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8.2 (already installed in dev deps) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (already configured) |
| Quick run command | `uv run pytest tests/test_adapters.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISC-01 | Wellfound adapter returns RawJobDict list from `__NEXT_DATA__` | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_wellfound_keyword_search -x` | Wave 0 |
| DISC-01 | Wellfound raises AdapterBrokenError when `__NEXT_DATA__` missing | unit | `uv run pytest tests/test_adapters.py::test_wellfound_broken_detection -x` | Wave 0 |
| DISC-02 | Greenhouse adapter returns normalized RawJobDict list | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_greenhouse_fetch -x` | Wave 0 |
| DISC-02 | Lever adapter returns normalized RawJobDict list | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_lever_fetch -x` | Wave 0 |
| DISC-03 | HN adapter finds latest Who's Hiring thread | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_hn_thread_discovery -x` | Wave 0 |
| DISC-03 | HN adapter parses comments into RawJobDict list | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_hn_comment_parsing -x` | Wave 0 |
| Success #2 | Cross-source dedup: same job from two sources stored once | integration | `uv run pytest tests/test_discover.py::test_cross_source_dedup -x` | Wave 0 |
| Success #3 | Jobs not re-sighted within TTL get is_stale=True | integration | `uv run pytest tests/test_discover.py::test_stale_marking -x` | Wave 0 |
| Success #4 | 3 consecutive zero-result runs fires health alert | unit | `uv run pytest tests/test_discover.py::test_source_health_alert -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_adapters.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_adapters.py` — covers DISC-01, DISC-02, DISC-03 adapter unit tests
- [ ] `tests/test_discover.py` — covers discovery orchestrator, cross-source dedup, stale marking, health alerts
- [ ] `tests/fixtures/greenhouse_response.json` — sample Greenhouse API response for tests
- [ ] `tests/fixtures/lever_response.json` — sample Lever API response for tests
- [ ] `tests/fixtures/hn_thread.json` — sample HN Algolia items response for tests
- [ ] `tests/fixtures/wellfound_page.html` — sample Wellfound HTML with `__NEXT_DATA__` for tests
- [ ] Framework packages: `uv add httpx beautifulsoup4 lxml tenacity python-dateutil && uv add --dev respx`
- [ ] Schema migration: `alembic revision --autogenerate -m "add is_stale to normalized_job"`

---

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Python, SQLite + SQLModel, CLI (Typer), JSON Resume format — no deviations
- **No LangChain/LangGraph** — Phase 2 has no LLM calls; not relevant here
- **Agent framework**: Custom loop only — adapter orchestration in `pipelines/discover.py`, not a framework
- **Storage**: SQLite for state (`NormalizedJob`, `StatusEvent`), filesystem for generated materials (not relevant Phase 2)
- **Budget**: Phase 2 has zero LLM spend; budget tracker not used
- **httpx** preferred over requests (per CLAUDE.md stack table)
- **No Scrapy** — explicitly ruled out in CLAUDE.md alternatives table
- **tenacity** for retry logic (per CLAUDE.md stack table)
- **respx** for httpx mocking (per CLAUDE.md testing table)
- **uv** for package management — use `uv add`, not `pip install`
- **ruff** for formatting — all new code must pass `uv run ruff check` and `uv run ruff format`
- **Pre-existing code patterns**: `FilterConfig` as standalone `BaseModel` (not Settings subclass); `dateutil` for date parsing (already used in normalize.py); `get_settings()` factory with `@lru_cache`; `RawJobDict = dict[str, Any]` as the adapter output contract

---

## Sources

### Primary (HIGH confidence)
- Greenhouse Job Board API: `https://developers.greenhouse.io/job-board.html` — endpoints, response fields, auth requirements verified 2026-04-05
- Lever Postings API: `https://github.com/lever/postings-api/blob/master/README.md` — endpoints, response fields, pagination verified 2026-04-05
- HN Algolia API: `https://hn.algolia.com/api/v1/` — search endpoint, tag filters (`author_whoishiring`), items endpoint verified via Medium article citing official docs 2026-04-05
- Phase 1 code: `src/jobinator/pipelines/` — existing normalize.py, dedup.py contracts verified by direct code reading
- PyPI registry: httpx 0.28.1, beautifulsoup4 4.14.3, lxml 6.0.2, tenacity 9.1.4, python-dateutil 2.9.0, respx 0.22.0 — all verified 2026-04-05

### Secondary (MEDIUM confidence)
- ScrapFly Wellfound guide: `https://scrapfly.io/blog/posts/how-to-scrape-wellfound-aka-angellist` — `__NEXT_DATA__` architecture, Apollo state graph structure, URL patterns, no-auth access confirmed. Structure can change without notice.
- CLAUDE.md stack table — technology choices verified against project instructions

### Tertiary (LOW confidence)
- Wellfound `apolloState` key prefix `JobListingSearchResult:` — derived from ScrapFly analysis; needs empirical validation against live site before relying on it
- HN comment parsing pipe-delimiter prevalence (~70-80%) — training data estimate, not empirically measured

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI registry 2026-04-05
- Greenhouse/Lever APIs: HIGH — official or official-equivalent API docs verified
- HN Algolia API: HIGH — stable, officially maintained by Algolia
- Wellfound approach: MEDIUM — architecture confirmed but `__NEXT_DATA__` structure needs live validation
- Architecture patterns: HIGH — consistent with established Phase 1 patterns and ARCHITECTURE.md

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 for stable APIs; Wellfound findings should be re-verified if > 2 weeks elapse before implementation (site structure can change on any deploy)
