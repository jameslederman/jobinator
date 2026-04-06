---
status: partial
phase: 04-materials-generation
source: [04-VERIFICATION.md]
started: 2026-04-06T20:00:00Z
updated: 2026-04-06T20:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. PDF Visual Quality
expected: Resume renders with header (name, label, contact), Summary, Experience with dates, Skills grid, Education. Cover letter renders with date, paragraphs, name at close. Prep brief renders with company overview, questions, talking points, gaps. No overlapping elements, no garbled text, correct margins.
result: [pending]

### 2. End-to-End HITL Confirmation Gate
expected: Running `jobinator apply <scored_job_id>` shows generation output, Rich Panel preview, then "Write these files to disk?" prompt. Answering "n" produces no files. Answering "y" creates all 9 files in `<output_dir>/<company>/<role>/<timestamp>/`.
result: [pending]

### 3. Versioned Directory Behavior (Confirmed Run)
expected: Running `apply` twice for the same job, confirming both times, creates two separate timestamped directories side-by-side. Neither overwrites the other.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
