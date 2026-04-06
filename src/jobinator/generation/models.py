"""Pydantic response models for LLM-based materials generation.

These are NOT SQLModel tables — they define the structured output schema
for Instructor-based LLM generation calls. After validation, content is
rendered to files and a GeneratedMaterial row is persisted to DB.

Requirements:
  MATL-02: Resume content must trace to profile data (no invented facts).
  MATL-03: Cover letter must be scoped to specific company + role.
  MATL-04: Prep brief provides company overview, likely questions, talking points.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TailoredWorkEntry(BaseModel):
    """A single work experience entry, rephrased for relevance.

    All fields trace directly to the profile's work history — no invented
    content. Highlights are rephrased to emphasize relevance to the target
    role but must each correspond to a highlight in the source profile.
    """

    company: str = Field(description="Company name verbatim from profile")
    position: str = Field(description="Position title verbatim from profile")
    start_date: str = Field(description="Start date verbatim from profile")
    end_date: str = Field(description="End date verbatim from profile, or 'Present'")
    highlights: list[str] = Field(
        description=(
            "Bullet points rephrased to emphasize relevance to target role. "
            "Each highlight MUST trace to a highlight in the profile."
        )
    )


class ResumeContent(BaseModel):
    """Structured resume output — all fields must trace to profile data (MATL-02).

    Used as Instructor response_model for tailored resume generation. After
    validation this is rendered to HTML/PDF via Jinja2 + WeasyPrint.
    """

    summary: str = Field(
        description=(
            "Tailored professional summary (2-3 sentences). "
            "Use ONLY facts from the provided profile."
        )
    )
    relevant_experience: list[TailoredWorkEntry] = Field(
        description=(
            "Work entries from the profile, reordered/rephrased to emphasize "
            "job-relevant aspects. Do NOT add metrics or dates not in the profile."
        )
    )
    highlighted_skills: list[str] = Field(
        description=("Skills from profile.skills relevant to this job. Do NOT invent skills.")
    )
    education: list[dict] = Field(
        description="Education entries verbatim from profile -- no modification."
    )


class CoverLetterContent(BaseModel):
    """Structured cover letter output scoped to company+role (MATL-03).

    Used as Instructor response_model for cover letter generation. All claims
    must trace to profile data — no invented accomplishments.
    """

    opening: str = Field(description="Opening paragraph referencing the specific company and role.")
    body_paragraphs: list[str] = Field(
        description=(
            "2-3 body paragraphs connecting profile experience to job requirements. "
            "All claims must trace to profile."
        )
    )
    closing: str = Field(description="Closing paragraph with call to action.")


class PrepBriefContent(BaseModel):
    """Interview prep brief with company overview and talking points (MATL-04).

    Used as Instructor response_model for prep brief generation. Provides
    interview preparation context grounded in the job description and profile.
    """

    company_overview: str = Field(
        description="Brief company overview based on job description context."
    )
    role_summary: str = Field(description="What the role entails based on job description.")
    likely_questions: list[str] = Field(
        description="5-10 likely interview questions based on job requirements."
    )
    talking_points: list[str] = Field(
        description=("5-8 talking points grounded in profile strengths relevant to this role.")
    )
    gaps_to_address: list[str] = Field(
        description=("2-4 potential gap areas from scoring and how to address them.")
    )
