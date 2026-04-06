"""Prompt builders for LLM-based materials generation.

Each builder produces a list of message dicts suitable for passing directly
to the Instructor-wrapped LiteLLM client. The system message contains the
full JSON Resume profile and grounding rules; the user message contains
job-specific context and generation instructions.

Requirements:
  MATL-02: Resume prompt must include grounding rules to prevent invented facts.
  MATL-03: Cover letter prompt must scope generation to specific company + role.
  MATL-04: Prep brief prompt must request company overview, questions, talking points.
"""

from __future__ import annotations

import json

from jobinator.models.job import NormalizedJob
from jobinator.models.score import JobScore

_GROUNDING_RULES = """CRITICAL TRUTHFULNESS RULES:
1. Every metric MUST appear verbatim in the provided profile.
2. Every skill MUST appear in the profile's skills section.
3. You may REPHRASE or EMPHASIZE but NOT INVENT any facts, metrics, or skills.
4. If profile lacks specific information, OMIT rather than fabricate.
5. The provided JSON Resume profile is the ONLY source of truth.
6. Do NOT invent companies, roles, dates, or accomplishments.
7. Do NOT add metrics (percentages, numbers) that do not appear in the profile."""


def build_resume_prompt(
    profile_data: dict,
    job: NormalizedJob,
    score: JobScore | None = None,
) -> list[dict]:
    """Build LLM messages for tailored resume generation.

    System message includes the full profile JSON and grounding rules (MATL-02).
    User message provides job context and tailoring instructions.

    Args:
        profile_data: JSON Resume dict (the complete profile).
        job: NormalizedJob to tailor the resume toward.
        score: Optional JobScore for emphasizing strengths/gaps alignment.

    Returns:
        List of message dicts: [{"role": "system", ...}, {"role": "user", ...}]
    """
    profile_json = json.dumps(profile_data, indent=2)

    system_content = f"""You are an expert resume writer helping a job seeker tailor their resume.

{_GROUNDING_RULES}

The following JSON Resume profile is the ONLY source of truth for all content:

```json
{profile_json}
```

Generate a tailored ResumeContent that emphasizes experience and skills most relevant
to the target job. Reorder highlights to lead with the most relevant ones. Rephrase
bullet points to use language from the job description where accurate, but never
add information not present in the profile."""

    # Build job context for user message
    description_section = job.description[:4000]
    requirements_section = ""
    if job.requirements_raw:
        requirements_section = f"\n\n**Requirements:**\n{job.requirements_raw[:2000]}"

    score_section = ""
    if score is not None:
        import json as _json

        strengths = _json.loads(score.strengths_json or "[]")
        gaps = _json.loads(score.gaps_json or "[]")
        if strengths:
            score_section += "\n\n**Key Strengths to Emphasize:**\n" + "\n".join(
                f"- {s}" for s in strengths
            )
        if gaps:
            score_section += "\n\n**Gaps to Address Carefully:**\n" + "\n".join(
                f"- {g}" for g in gaps
            )

    user_content = f"""Please generate a tailored resume for the following position.

**Target Role:** {job.title}
**Company:** {job.company}

**Job Description:**
{description_section}{requirements_section}{score_section}

Tailor the resume content to highlight experience and skills most relevant to this role.
Return structured content as specified."""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def build_cover_letter_prompt(
    profile_data: dict,
    job: NormalizedJob,
    score: JobScore | None = None,
) -> list[dict]:
    """Build LLM messages for cover letter generation.

    System message includes grounding rules and full profile JSON (MATL-03).
    Cover letter is scoped to the specific company and role.

    Args:
        profile_data: JSON Resume dict (the complete profile).
        job: NormalizedJob for the target position.
        score: Optional JobScore for highlighting strengths and addressing gaps.

    Returns:
        List of message dicts: [{"role": "system", ...}, {"role": "user", ...}]
    """
    profile_json = json.dumps(profile_data, indent=2)

    system_content = f"""You are an expert cover letter writer helping a job seeker craft a
compelling, concise cover letter tailored to a specific company and role.

{_GROUNDING_RULES}

The following JSON Resume profile is the ONLY source of truth for all content:

```json
{profile_json}
```

Write a concise 3-paragraph cover letter:
- Opening: Reference the specific company and role, express genuine interest
- Body (1-2 paragraphs): Connect specific profile experiences to job requirements
- Closing: Call to action, thank the reader

Keep it under 300 words total. Be specific, not generic."""

    description_section = job.description[:3000]

    score_section = ""
    if score is not None:
        import json as _json

        strengths = _json.loads(score.strengths_json or "[]")
        gaps = _json.loads(score.gaps_json or "[]")
        if strengths:
            score_section += "\n\n**Key Strengths to Highlight:**\n" + "\n".join(
                f"- {s}" for s in strengths
            )
        if gaps:
            score_section += "\n\n**Gaps to Address Tactfully:**\n" + "\n".join(
                f"- {g}" for g in gaps
            )

    user_content = f"""Please write a tailored cover letter for the following position.

**Target Role:** {job.title}
**Company:** {job.company}

**Job Description:**
{description_section}{score_section}

Write a concise, compelling cover letter that speaks directly to this role at {job.company}.
Return structured content as specified."""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def build_prep_brief_prompt(
    profile_data: dict,
    job: NormalizedJob,
    score: JobScore | None = None,
) -> list[dict]:
    """Build LLM messages for interview prep brief generation.

    System message includes profile JSON for talking points grounding (MATL-04).
    Brief includes company overview, likely questions, talking points, and gaps.

    Args:
        profile_data: JSON Resume dict (the complete profile).
        job: NormalizedJob for the interview prep.
        score: Optional JobScore for gap-based prep focus.

    Returns:
        List of message dicts: [{"role": "system", ...}, {"role": "user", ...}]
    """
    profile_json = json.dumps(profile_data, indent=2)

    system_content = f"""You are an expert interview coach preparing a candidate for an interview.

Generate a comprehensive interview prep brief with:
- company_overview: Brief company overview based on job description context
- role_summary: What the role entails, key responsibilities
- likely_questions: 5-10 likely interview questions based on job requirements
- talking_points: 5-8 talking points grounded in the candidate's profile strengths
- gaps_to_address: 2-4 potential gap areas and how to address them

For talking points, ground them in the candidate's actual experience:

```json
{profile_json}
```

All talking points MUST trace to real experience in the profile above.
Do NOT invent accomplishments."""

    description_section = job.description[:3500]

    score_section = ""
    if score is not None:
        import json as _json

        strengths = _json.loads(score.strengths_json or "[]")
        gaps = _json.loads(score.gaps_json or "[]")
        if strengths:
            score_section += "\n\n**Identified Strengths:**\n" + "\n".join(
                f"- {s}" for s in strengths
            )
        if gaps:
            score_section += "\n\n**Identified Gaps (prep focus areas):**\n" + "\n".join(
                f"- {g}" for g in gaps
            )

    user_content = f"""Prepare an interview prep brief for the following position.

**Role:** {job.title}
**Company:** {job.company}

**Job Description:**
{description_section}{score_section}

Generate a comprehensive prep brief to help the candidate succeed in interviews
for this {job.title} role at {job.company}."""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
