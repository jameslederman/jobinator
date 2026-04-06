"""SQLModel table definition for generated application materials."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class GeneratedMaterial(SQLModel, table=True):
    """Persisted record of a generated materials bundle for a job.

    Only created after the user confirms they want to keep the generated
    materials (confirmed=True is always set — unconfirmed bundles are not
    persisted to this table).

    bundle_path points to the versioned output directory on disk containing
    the generated resume PDF, cover letter PDF, and prep brief markdown.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = Field(
        foreign_key="normalizedjob.id",
        index=True,
        description="The job this materials bundle was generated for",
    )
    bundle_path: str = Field(description="Absolute path to the versioned output directory on disk")
    resume_word_count: int = Field(
        default=0,
        description="Word count of the generated resume content",
    )
    cover_letter_word_count: int = Field(
        default=0,
        description="Word count of the generated cover letter content",
    )
    prep_brief_question_count: int = Field(
        default=0,
        description="Number of interview questions in the prep brief",
    )
    model_used: str = Field(
        description="LLM model used for generation (e.g. 'claude-3-5-sonnet-latest')"
    )
    total_cost_usd: float = Field(
        default=0.0,
        description="Total API cost for generating this materials bundle",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the materials bundle was generated",
    )
    confirmed: bool = Field(
        default=True,
        description="Always True — only persisted after user confirmation",
    )
