# Requirements: Jobinator

**Defined:** 2026-04-04
**Core Value:** Surface high-fit opportunities I'd miss manually and generate application materials good enough to submit with minimal editing.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Discovery

- [x] **DISC-01**: User can discover jobs from Wellfound/AngelList with structured output
- [x] **DISC-02**: User can discover jobs from Greenhouse/Lever ATS career pages with structured output
- [x] **DISC-03**: User can discover jobs from HN Who's Hiring threads with structured output
- [x] **DISC-04**: All discovered jobs are normalized to a standard schema (title, company, location, description, requirements, salary_range, url, source)
- [x] **DISC-05**: Jobs are deduplicated across sources using compound key (company_normalized, title_normalized) plus description content hash
- [x] **DISC-06**: Jobs include freshness metadata (posted date, first_seen, last_seen) and stale postings are deprioritized

### Scoring

- [x] **SCOR-01**: User can configure hard filters (salary floor, location type, title keywords, exclusion keywords)
- [x] **SCOR-02**: Jobs passing hard filters are scored by LLM for nuanced fit (0-1 score)
- [x] **SCOR-03**: Each scored job includes strengths match, gaps analysis, and compensation estimate
- [x] **SCOR-04**: Each scored job has a priority score combining fit, urgency, recency, and user preferences
- [x] **SCOR-05**: Every score includes human-readable reasoning explaining why the job scored as it did

### Materials

- [x] **MATL-01**: User can generate a tailored resume from JSON Resume base that emphasizes relevant experience per role
- [x] **MATL-02**: Generated resumes are truthful — no hallucinated metrics, dates, or skills
- [x] **MATL-03**: User can generate a concise, company+role-specific cover letter per job
- [x] **MATL-04**: User can generate an interview prep brief per job (company overview, likely questions, talking points)
- [x] **MATL-05**: All generated materials are rendered to PDF
- [x] **MATL-06**: Materials are saved to configurable output directory organized by company/role with versioning

### Application

- [ ] **APPL-01**: User can track application status through pipeline stages (discovered, scored, applied, phone_screen, interview, rejected, offer)
- [ ] **APPL-02**: System prevents duplicate applications to the same role
- [ ] **APPL-03**: User can review scored jobs and generated materials before any apply action (human-in-the-loop)
- [ ] **APPL-04**: System tracks response/interview/offer rates per source, role type, and company type for feedback loop
- [ ] **APPL-05**: Decision logging captures reasoning for every ignore/track/apply decision

### Infrastructure

- [x] **INFR-01**: LLM calls route through multi-provider abstraction (cheap models for filtering/scoring, strong models for generation)
- [x] **INFR-02**: Token and API spend is tracked per call with configurable daily and per-job budget limits
- [x] **INFR-03**: Budget enforcement gates LLM calls — hard stop when limit is reached
- [x] **INFR-04**: All job and application state persists in SQLite via SQLModel with schema migrations
- [ ] **INFR-05**: CLI interface provides commands: discover, score, apply, run --auto, review, status
- [x] **INFR-06**: Agent loop is interruptible and logs all decisions

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Discovery Enhancements

- **DISC-07**: Company-first discovery (target companies -> find open roles)
- **DISC-08**: Company research enrichment (funding stage, headcount, tech stack)

### Application Enhancements

- **APPL-06**: Form-filling assist for web application forms
- **APPL-07**: ATS API submission where available (Greenhouse/Lever)

### Scoring Enhancements

- **SCOR-06**: Learned scoring model trained on user's outcome data
- **SCOR-07**: Salary intelligence from market data sources

## Out of Scope

| Feature | Reason |
|---------|--------|
| LinkedIn scraping | Legal/ToS risk, aggressive anti-bot measures — not worth it for v1 |
| Full auto-apply without confirmation | Career damage risk from wrong roles, wrong answers, duplicates |
| Browser automation for apply | Brittle, high maintenance, breaks on DOM changes |
| SaaS / multi-user features | Single-user developer tool by design |
| Mobile app or web UI | CLI-first; optional dashboard deferred |
| Video resume / portfolio | Text materials only — video adds enormous complexity |
| Bulk spray-and-apply mode | Explicitly anti-pattern — quality over quantity |
| ATS keyword score optimization | Gaming ATS scores produces keyword-stuffed resumes that repel humans |
| Email outreach / cold messaging | Legal (CAN-SPAM), deliverability, reputational complexity |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DISC-01 | Phase 2 | Complete |
| DISC-02 | Phase 2 | Complete |
| DISC-03 | Phase 2 | Complete |
| DISC-04 | Phase 1 | Complete |
| DISC-05 | Phase 1 | Complete |
| DISC-06 | Phase 1 | Complete |
| SCOR-01 | Phase 1 | Complete |
| SCOR-02 | Phase 3 | Complete |
| SCOR-03 | Phase 3 | Complete |
| SCOR-04 | Phase 3 | Complete |
| SCOR-05 | Phase 3 | Complete |
| MATL-01 | Phase 4 | Complete |
| MATL-02 | Phase 4 | Complete |
| MATL-03 | Phase 4 | Complete |
| MATL-04 | Phase 4 | Complete |
| MATL-05 | Phase 4 | Complete |
| MATL-06 | Phase 4 | Complete |
| APPL-01 | Phase 5 | Pending |
| APPL-02 | Phase 5 | Pending |
| APPL-03 | Phase 5 | Pending |
| APPL-04 | Phase 5 | Pending |
| APPL-05 | Phase 5 | Pending |
| INFR-01 | Phase 3 | Complete |
| INFR-02 | Phase 3 | Complete |
| INFR-03 | Phase 3 | Complete |
| INFR-04 | Phase 1 | Complete |
| INFR-05 | Phase 5 | Pending |
| INFR-06 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0

---
*Requirements defined: 2026-04-04*
*Last updated: 2026-04-04 after roadmap creation — all 28 requirements mapped*
