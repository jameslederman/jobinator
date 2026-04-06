"""Materials generation module for Jobinator.

Provides LLM-based generation of tailored resumes, cover letters, and
interview prep briefs for job applications.
"""

from jobinator.generation.generator import MaterialsGenerator
from jobinator.generation.models import (
    CoverLetterContent,
    PrepBriefContent,
    ResumeContent,
    TailoredWorkEntry,
)
from jobinator.generation.renderer import render_html, render_pdf

__all__ = [
    "MaterialsGenerator",
    "ResumeContent",
    "CoverLetterContent",
    "PrepBriefContent",
    "TailoredWorkEntry",
    "render_html",
    "render_pdf",
]
