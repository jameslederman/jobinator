"""SQLModel table definitions and Pydantic output models for LLM scoring."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField


class JobScore(SQLModel, table=True):
    """LLM-generated fit score for a NormalizedJob.

    One-to-one with NormalizedJob: the unique=True constraint on job_id
    ensures a job can only have a single active score record.
    """

    id: str = SQLField(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = SQLField(foreign_key="normalizedjob.id", unique=True, index=True)
    fit_score: float = SQLField(description="LLM-assigned fit score 0-1")
    priority_score: float = SQLField(description="Combined priority 0-1")
    strengths_json: str = SQLField(description="JSON array of matching strengths")
    gaps_json: str = SQLField(description="JSON array of gaps/concerns")
    compensation_estimate: Optional[str] = SQLField(default=None)
    reasoning: str = SQLField(description="Human-readable reasoning paragraph")
    model_used: str = SQLField(description="Model that produced this score")
    scored_at: datetime = SQLField(default_factory=datetime.utcnow)


class JobScoreOutput(BaseModel):
    """Structured LLM output for job scoring via Instructor.

    This is the response_model passed to Instructor — it is NOT a SQLModel
    table. After validation it is serialized into a JobScore row.
    """

    fit_score: float = Field(ge=0.0, le=1.0, description="Overall fit 0-1")
    strengths_match: list[str] = Field(
        description="Matching strengths (2-5 bullet points)"
    )
    gaps: list[str] = Field(description="Gaps or concerns (0-5 bullet points)")
    compensation_estimate: str = Field(
        default="unknown", description="Estimated comp range or 'unknown'"
    )
    priority_score: float = Field(
        ge=0.0, le=1.0, description="Combined priority (fit + urgency + recency)"
    )
    reasoning: str = Field(
        description="Human-readable explanation paragraph (3-5 sentences)"
    )
