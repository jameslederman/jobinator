"""Prompt builder for LLM job scoring."""

from __future__ import annotations

from jobinator.models.job import NormalizedJob


def _format_salary(job: NormalizedJob) -> str | None:
    """Format salary range from job fields into a human-readable string.

    Returns a string like '150k-200k' or None if no salary data available.
    """
    if job.salary_min is not None and job.salary_max is not None:
        min_k = job.salary_min // 1000
        max_k = job.salary_max // 1000
        return f"${min_k}k-${max_k}k"
    if job.salary_min is not None:
        return f"${job.salary_min // 1000}k+"
    if job.salary_max is not None:
        return f"up to ${job.salary_max // 1000}k"
    return None


def _format_profile(profile_data: dict) -> str:
    """Extract and format candidate profile from JSON Resume dict.

    Extracts basics (name, label, summary), skills list, and recent work
    experience into a human-readable block.

    Args:
        profile_data: JSON Resume dict

    Returns:
        Formatted multi-line string for inclusion in prompt.
    """
    lines: list[str] = []

    basics = profile_data.get("basics", {})
    name = basics.get("name", "Unknown")
    label = basics.get("label", "")
    summary = basics.get("summary", "")

    lines.append(f"**Name:** {name}")
    if label:
        lines.append(f"**Current Role:** {label}")
    if summary:
        lines.append(f"**Summary:** {summary}")

    skills = profile_data.get("skills", [])
    if skills:
        skill_names = [s.get("name", "") for s in skills if s.get("name")]
        lines.append(f"**Key Skills:** {', '.join(skill_names)}")

    work = profile_data.get("work", [])
    if work:
        lines.append("**Recent Experience:**")
        for entry in work[:3]:  # Include up to 3 most recent roles
            company = entry.get("name", "")
            position = entry.get("position", "")
            start = entry.get("startDate", "")[:7]  # YYYY-MM
            end = entry.get("endDate", "Present")
            entry_summary = entry.get("summary", "")
            highlights = entry.get("highlights", [])

            role_line = f"  - {position} at {company} ({start} - {end})"
            lines.append(role_line)
            if entry_summary:
                lines.append(f"    {entry_summary}")
            for h in highlights[:2]:
                lines.append(f"    - {h}")

    return "\n".join(lines)


def build_scoring_prompt(job: NormalizedJob, profile_data: dict) -> list[dict]:
    """Build LLM messages list for job fit scoring.

    Creates a system message instructing the LLM to return a structured
    assessment, and a user message with the job posting and candidate
    profile formatted for easy evaluation.

    Args:
        job: NormalizedJob instance to score.
        profile_data: JSON Resume dict for the candidate.

    Returns:
        List of message dicts with 'role' and 'content' keys, suitable
        for passing to LLMClient.score().
    """
    system_message = (
        "You are a job fit evaluator. Analyze how well the candidate profile "
        "matches the job posting. Return a structured assessment with:\n"
        "- fit_score: 0.0-1.0 overall fit rating\n"
        "- strengths_match: 2-5 specific matching strengths\n"
        "- gaps: 0-5 gaps or concerns\n"
        "- compensation_estimate: salary estimate based on role/location/seniority "
        "or salary info in posting\n"
        "- priority_score: 0.0-1.0 combined priority rating\n"
        "- reasoning: 3-5 sentence human-readable explanation\n\n"
        "Be honest about gaps. Base compensation_estimate on posted salary if "
        "available, otherwise estimate from role, location, and seniority level."
    )

    salary_str = _format_salary(job)
    salary_display = salary_str if salary_str else "Not posted"

    location_raw = job.location_raw or "Not specified"
    location_type = job.location_type or "unknown"

    # Truncate description to 3000 chars to stay within token limits
    description = job.description[:3000]

    requirements_section = ""
    if job.requirements_raw:
        requirements_section = f"\n**Requirements:**\n{job.requirements_raw}"

    profile_block = _format_profile(profile_data)

    user_message = f"""## Job Posting
**Title:** {job.title}
**Company:** {job.company}
**Location:** {location_raw} ({location_type})
**Salary:** {salary_display}
**Description:**
{description}{requirements_section}

## Candidate Profile
{profile_block}"""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
