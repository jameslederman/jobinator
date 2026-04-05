---
phase: 02-data-ingestion
plan: 02
subsystem: data-ingestion
tags: [adapters, hn-hiring, wellfound, discovery, scraping]
dependency_graph:
  requires:
    - SourceAdapter Protocol (adapters/base.py) — from Plan 01
    - GreenhouseAdapter, LeverAdapter — from Plan 01
    - RawJobDict type (pipelines/normalize.py) — from Plan 01
    - AdapterBrokenError (adapters/base.py) — from Plan 01
  provides:
    - HNHiringAdapter (adapters/hn_hiring.py)
    - WellfoundAdapter (adapters/wellfound.py)
    - All four adapters exported from adapters/__init__.py
  affects:
    - Discovery orchestrator (consumes all four adapters)
    - Health monitoring (fragile=True flag on WellfoundAdapter)
tech_stack:
  added: []
  patterns:
    - HN discovery: Algolia search_by_date API -> items/{id} for comments
    - Pipe-delimiter parsing: Company | Title | Location | Salary | URL
    - BeautifulSoup HTML text extraction for HN comment HTML stripping
    - __NEXT_DATA__ extraction: find script[id="__NEXT_DATA__"], json.loads
    - Apollo state traversal: JobListingSearchResult: keys + StartupResult: __ref dereference
    - fragile=True: structural breakage guard, AdapterBrokenError raised on missing script tag
    - USER_AGENT: realistic Chrome/Mac string for Wellfound bot avoidance
    - random.uniform() delay between Wellfound requests (configurable min/max)
    - Pagination cap: _MAX_PAGES=20 per session to avoid rate-limit blowout
key_files:
  created:
    - src/jobinator/adapters/hn_hiring.py
    - src/jobinator/adapters/wellfound.py
    - tests/fixtures/hn_thread.json
    - tests/fixtures/wellfound_page.html
  modified:
    - src/jobinator/adapters/__init__.py (exports all four adapters)
    - tests/test_adapters.py (HN and Wellfound test classes added)
decisions:
  - "HNHiringAdapter fragile=False — Algolia API is officially provided by HN and long-stable"
  - "WellfoundAdapter fragile=True — __NEXT_DATA__ extraction will break on Next.js structure changes"
  - "Pagination heuristic for Wellfound: stop when page returns < 10 nodes (no explicit total count in Apollo state)"
  - "parse_hn_comment returns result even for non-job meta-comments (caller decides to use or discard)"
  - "WellfoundAdapter raises AdapterBrokenError immediately on missing __NEXT_DATA__ — propagates up to caller"
metrics:
  duration: 4 minutes
  completed: "2026-04-05"
  tasks: 2
  files: 6
---

# Phase 2 Plan 2: HN Hiring + Wellfound Adapters Summary

**One-liner:** HNHiringAdapter (Algolia thread discovery + pipe-delimiter comment parsing) and WellfoundAdapter (__NEXT_DATA__ Apollo state extraction, fragile=True) completing all four discovery sources.

## What Was Built

### HNHiringAdapter (`src/jobinator/adapters/hn_hiring.py`)

Discovers the latest "Ask HN: Who is Hiring?" threads via the Algolia HN Search API and parses top-level comments.

Key behaviors:
- `find_latest_hn_hiring_threads(months_back)`: `GET search_by_date?tags=story,author_whoishiring&hitsPerPage=N` — raises RuntimeError if no results
- `fetch_thread_comments(story_id)`: `GET items/{id}` — returns top-level children only, does NOT recurse
- `parse_hn_comment(comment)`: HTML-strips text with BeautifulSoup, splits by `|`, extracts company/title/location/salary/URL; returns None for very short (<20 char) texts
- Salary regex: matches `$200k-$300k`, `$150,000-$200,000` etc.
- URL regex: extracts `https?://` links from comment segments
- `source_url` always points to `https://news.ycombinator.com/item?id={comment_id}`
- `source_id="hn_hiring"`, `fragile=False`

### WellfoundAdapter (`src/jobinator/adapters/wellfound.py`)

Extracts job listings from the `__NEXT_DATA__` JSON blob embedded in Wellfound's Next.js pages.

Key behaviors:
- `extract_wellfound_next_data(html)`: BeautifulSoup finds `script[id="__NEXT_DATA__"]`, raises `AdapterBrokenError` if missing
- `extract_job_nodes(next_data)`: navigates `props.pageProps.apolloState`, collects `JobListingSearchResult:*` keys, dereferences `startup.__ref` to resolve company name from `StartupResult:*`
- `job_node_to_raw(node, company_name)`: maps to RawJobDict; `posted_at=None` (Wellfound does not expose dates)
- Two fetch modes: keyword search (`/role/l/{slug}/remote`) and company pages (`/company/{slug}/jobs`)
- Pagination: up to `_MAX_PAGES=20`, stops when 0 nodes returned or partial page (<10 nodes)
- `random.uniform(delay_min, delay_max)` between requests
- Realistic Chrome/Mac `USER_AGENT` header on all requests
- `source_id="wellfound"`, `fragile=True`, `FRAGILE_NOTICE` documented in class

### All Four Adapters Exported (`src/jobinator/adapters/__init__.py`)

Updated to export `GreenhouseAdapter`, `LeverAdapter`, `HNHiringAdapter`, `WellfoundAdapter`, `SourceAdapter`, `AdapterBrokenError`.

## Tests

16 new tests added to `tests/test_adapters.py`:

**TestHNHiringAdapter (8 tests):**
- `test_find_latest_thread_returns_story_id` — Algolia search returns story ID
- `test_find_latest_thread_raises_on_empty_hits` — RuntimeError on no results
- `test_parse_hn_comment_pipe_delimited` — extracts company/title/location correctly
- `test_parse_hn_comment_non_pipe_delimited` — handles plain text comments
- `test_fetch_returns_raw_job_dicts` — fetch returns 2 job dicts from fixture
- `test_fetch_skips_nested_replies` — nested reply IDs absent from results
- `test_fetch_source_url_points_to_hn_comment` — source_url format verified
- `test_source_id_and_fragile` — source_id="hn_hiring", fragile=False

**TestWellfoundAdapter (8 tests):**
- `test_extract_next_data_parses_json` — parses fixture HTML correctly
- `test_extract_next_data_raises_on_missing_script_tag` — AdapterBrokenError raised
- `test_extract_job_nodes_finds_job_listings` — finds 2 JobListingSearchResult nodes
- `test_extract_job_nodes_resolves_company_name` — DataCo and MLOps Inc resolved
- `test_fetch_returns_raw_job_dicts_from_keyword_search` — keyword URL fetch
- `test_fetch_fetches_company_page_urls` — company slug URL fetch
- `test_source_id_and_fragile` — source_id="wellfound", fragile=True
- `test_uses_realistic_user_agent` — Mozilla/Chrome UA sent in request

Full test suite: 96 tests, all passing.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all adapters return fully wired RawJobDicts. Wellfound `posted_at=None` is intentional and documented (Wellfound does not expose posting date), not a stub.

## Self-Check: PASSED

Files verified to exist:
- `src/jobinator/adapters/hn_hiring.py` ✓
- `src/jobinator/adapters/wellfound.py` ✓
- `src/jobinator/adapters/__init__.py` (updated) ✓
- `tests/fixtures/hn_thread.json` ✓
- `tests/fixtures/wellfound_page.html` ✓
- `tests/test_adapters.py` (updated) ✓

Commits verified:
- Task 1 (RED): a2fecb0 ✓
- Task 1 (GREEN): 47c16aa ✓
- Task 2 (RED): d5a6330 ✓
- Task 2 (GREEN): d3b3fd0 ✓
