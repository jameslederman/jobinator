---
phase: 2
slug: data-ingestion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.2 (already installed in dev deps) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_adapters.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_adapters.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | DISC-01 | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_wellfound_keyword_search -x` | Wave 0 | ⬜ pending |
| 02-01-02 | 01 | 0 | DISC-01 | unit | `uv run pytest tests/test_adapters.py::test_wellfound_broken_detection -x` | Wave 0 | ⬜ pending |
| 02-01-03 | 01 | 0 | DISC-02 | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_greenhouse_fetch -x` | Wave 0 | ⬜ pending |
| 02-01-04 | 01 | 0 | DISC-02 | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_lever_fetch -x` | Wave 0 | ⬜ pending |
| 02-01-05 | 01 | 0 | DISC-03 | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_hn_thread_discovery -x` | Wave 0 | ⬜ pending |
| 02-01-06 | 01 | 0 | DISC-03 | unit (respx mock) | `uv run pytest tests/test_adapters.py::test_hn_comment_parsing -x` | Wave 0 | ⬜ pending |
| 02-02-01 | 02 | 1 | Success #2 | integration | `uv run pytest tests/test_discover.py::test_cross_source_dedup -x` | Wave 0 | ⬜ pending |
| 02-02-02 | 02 | 1 | Success #3 | integration | `uv run pytest tests/test_discover.py::test_stale_marking -x` | Wave 0 | ⬜ pending |
| 02-02-03 | 02 | 1 | Success #4 | unit | `uv run pytest tests/test_discover.py::test_source_health_alert -x` | Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_adapters.py` — stubs for DISC-01, DISC-02, DISC-03 adapter unit tests
- [ ] `tests/test_discover.py` — stubs for discovery orchestrator, cross-source dedup, stale marking, health alerts
- [ ] `tests/fixtures/greenhouse_response.json` — sample Greenhouse API response for tests
- [ ] `tests/fixtures/lever_response.json` — sample Lever API response for tests
- [ ] `tests/fixtures/hn_thread.json` — sample HN Algolia items response for tests
- [ ] `tests/fixtures/wellfound_page.html` — sample Wellfound HTML with `__NEXT_DATA__` for tests
- [ ] Framework packages: `uv add httpx beautifulsoup4 lxml tenacity python-dateutil && uv add --dev respx`
- [ ] Schema migration: `alembic revision --autogenerate -m "add is_stale to normalized_job"`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Greenhouse endpoint returns real jobs | DISC-02 | Requires live API call to real board | Run `jobinator discover --source greenhouse --company {token}` and verify non-empty output |
| Live HN thread parsing returns jobs | DISC-03 | Requires live Algolia API | Run `jobinator discover --source hn` and verify non-empty output |
| Wellfound page structure still has `__NEXT_DATA__` | DISC-01 | Requires live HTTP to wellfound.com | Run `jobinator discover --source wellfound` and check for non-error output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
