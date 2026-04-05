"""SQLModel table definitions for budget tracking and decision logging."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class SpendRecord(SQLModel, table=True):
    """Record of a single LLM API call and its cost.

    Used for budget enforcement and cost tracking across sessions.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: Optional[str] = Field(
        default=None,
        foreign_key="normalizedjob.id",
        index=True,
        description="Associated job, if applicable",
    )
    model_name: str = Field(description="LLM model used (e.g. 'claude-3-haiku')")
    provider: str = Field(description="Provider name (anthropic, openai, etc)")
    operation: str = Field(
        description="What the call was for (score, generate_resume, etc)"
    )
    input_tokens: int
    output_tokens: int
    cost_usd: float
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionLog(SQLModel, table=True):
    """Append-only log of agent decisions with reasoning (INFR-06).

    Every filter rejection, score skip, budget enforcement action,
    and apply approval is recorded here for auditability and
    feedback loop analysis.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: Optional[str] = Field(
        default=None,
        foreign_key="normalizedjob.id",
        description="Associated job, if applicable",
    )
    decision_type: str = Field(
        description="e.g. 'filter_reject', 'score_skip', 'budget_exceeded', 'apply_approve'"
    )
    decision: str = Field(description="What was decided")
    reason: str = Field(description="Why the decision was made")
    context_json: Optional[str] = Field(
        default=None, description="Additional context as JSON string"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
