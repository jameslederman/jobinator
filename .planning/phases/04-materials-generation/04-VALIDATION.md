---
phase: 4
slug: materials-generation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-06
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v --tb=long` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=long`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | MATL-01 | unit | `uv run pytest tests/test_materials.py -k resume` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | MATL-02 | unit | `uv run pytest tests/test_materials.py -k grounding` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | MATL-03 | unit | `uv run pytest tests/test_materials.py -k cover_letter` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | MATL-04 | unit | `uv run pytest tests/test_materials.py -k prep_brief` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | MATL-05 | unit | `uv run pytest tests/test_materials.py -k pdf` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 2 | MATL-06 | unit | `uv run pytest tests/test_output.py -k application_dir` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_materials.py` — stubs for MATL-01 through MATL-05
- [ ] `tests/conftest.py` — fixtures for sample Job, Profile, and JSON Resume data

*Existing test infrastructure (pytest, conftest.py) already in place from Phase 1-3.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PDF visual quality | MATL-05 | Visual inspection of rendered PDF layout and formatting | Generate a test PDF, open in viewer, verify sections render correctly |
| Human confirmation gate | MATL-04 | Interactive CLI prompt requires human input | Run `apply <job_id>`, verify preview is shown, verify prompt appears before file write |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
