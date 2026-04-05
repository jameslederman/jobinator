"""SQLModel table definitions for job-related entities."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    """Event-sourced job application status values (D-03)."""

    discovered = "discovered"
    scored = "scored"
    applied = "applied"
    phone_screen = "phone_screen"
    interview = "interview"
    rejected = "rejected"
    offer = "offer"


class LocationType(str, Enum):
    """Location type classification (D-02)."""

    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class SalarySource(str, Enum):
    """Provenance of salary information (D-01)."""

    posted = "posted"
    estimated = "estimated"
    unknown = "unknown"


class NormalizedJob(SQLModel, table=True):
    """Normalized job posting record.

    Salary modeled as four fields: posted (salary_min, salary_max) and
    estimated (estimated_salary_min, estimated_salary_max), with a salary_source
    enum to track provenance (D-01).

    Location modeled as type enum + raw free text (D-02).

    Dedup key is compound: (company_slug, title_normalized) + description_hash (D-05).
    Freshness metadata: posted_at, first_seen_at, last_seen_at (DISC-06).
    """

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    source: str = Field(description="Source adapter name (greenhouse, lever, hn, wellfound)")
    source_url: str = Field(unique=True, index=True, description="Original posting URL")
    title: str = Field(description="Original title text")
    title_normalized: str = Field(index=True, description="Lowercased, normalized title (D-05)")
    company: str = Field(description="Original company name")
    company_slug: str = Field(index=True, description="Deterministic company slug (D-04)")

    # Location fields (D-02)
    location_raw: Optional[str] = Field(default=None, description="Free text from posting")
    location_type: Optional[str] = Field(default=None, description="LocationType enum value as str")

    # Salary quad (D-01)
    salary_min: Optional[int] = Field(default=None, description="Posted salary minimum")
    salary_max: Optional[int] = Field(default=None, description="Posted salary maximum")
    estimated_salary_min: Optional[int] = Field(default=None, description="Estimated salary minimum")
    estimated_salary_max: Optional[int] = Field(default=None, description="Estimated salary maximum")
    salary_source: Optional[str] = Field(default=None, description="SalarySource enum value as str")

    description: str = Field(description="Full job description text")
    requirements_raw: Optional[str] = Field(
        default=None, description="Extracted requirements section if available"
    )
    description_hash: str = Field(
        index=True,
        description="sha256 of first 500 chars of description, truncated to 16 hex chars (D-05)",
    )

    # Freshness metadata (DISC-06)
    posted_at: Optional[datetime] = Field(default=None, description="When job was posted")
    first_seen_at: datetime = Field(
        default_factory=datetime.utcnow, description="First discovery timestamp"
    )
    last_seen_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last sighting timestamp"
    )

    raw_json: str = Field(description="JSON string of original payload for debugging")

    @staticmethod
    def make_description_hash(description: str) -> str:
        """Generate a 16-char hex hash of the first 500 chars of a description."""
        return hashlib.sha256(description[:500].encode()).hexdigest()[:16]


class StatusEvent(SQLModel, table=True):
    """Append-only event log for job application status changes (D-03).

    Current status is derived from the latest event ordered by created_at.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = Field(foreign_key="normalizedjob.id", index=True)
    status: str = Field(description="JobStatus enum value as str")
    reason: Optional[str] = Field(default=None, description="Why status changed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
