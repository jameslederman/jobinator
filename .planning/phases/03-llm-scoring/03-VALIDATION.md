---
phase: 3
slug: llm-scoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-06
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `uv run pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `uv run pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | INFR-01, INFR-02, INFR-03 | unit | `uv run pytest tests/test_llm_client.py -v` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | SCOR-02, SCOR-03 | unit + integration | `uv run pytest tests/test_scoring.py -v` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | SCOR-04, SCOR-05 | unit + CLI | `uv run pytest tests/test_score_cli.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_llm_client.py` — stubs for LLM client wrapper, budget tracking integration
- [ ] `tests/test_scoring.py` — stubs for scoring pipeline, structured output validation
- [ ] `tests/test_score_cli.py` — stubs for CLI score command, budget gating
- [ ] LLM dependencies installed: `uv add litellm instructor anthropic openai tiktoken`

*Existing pytest infrastructure from Phase 1 covers framework setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM response quality | SCOR-03 | Reasoning quality is subjective | Review 3+ scoring outputs for coherent reasoning paragraphs |
| Cost accuracy vs provider invoice | INFR-01 | Requires real API spend comparison | Compare SQLite spend records against provider dashboard after test run |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
