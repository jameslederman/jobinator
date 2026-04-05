---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (Wave 0 creates) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-02 | 01 | 1 | INFR-04 | unit | `uv run pytest tests/test_models.py -x` | W0 | pending |
| 01-02-01 | 02 | 2 | DISC-04 | unit | `uv run pytest tests/test_normalize.py -x` | W0 | pending |
| 01-02-02 | 02 | 2 | DISC-05 | unit | `uv run pytest tests/test_dedup.py -x` | W0 | pending |
| 01-02-03 | 02 | 2 | DISC-06, SCOR-01 | unit | `uv run pytest tests/test_filter.py -x` | W0 | pending |
| 01-03-01 | 03 | 2 | INFR-06 | unit | `uv run pytest tests/test_budget.py -x` | W0 | pending |
| 01-03-02 | 03 | 2 | INFR-04 | unit | `uv run pytest tests/test_output.py -x` | W0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (temp SQLite DB, sample job dicts)
- [ ] `tests/test_models.py` — stubs for model and database tests
- [ ] `tests/test_normalize.py` — stubs for normalization pipeline tests
- [ ] `tests/test_dedup.py` — stubs for deduplication tests
- [ ] `tests/test_filter.py` — stubs for heuristic filter tests
- [ ] `tests/test_budget.py` — stubs for budget tracker tests
- [ ] `tests/test_output.py` — stubs for output directory structure tests
- [ ] pytest installed via `uv add --dev pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Output dir symlink `latest/` | INFR-04 | Symlink behavior varies by OS | Create two timestamp dirs, verify `latest/` points to newest |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
