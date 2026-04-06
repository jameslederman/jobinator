"""Tests for Jinja2 HTML rendering and WeasyPrint PDF conversion."""

from __future__ import annotations

from jobinator.generation.models import (
    CoverLetterContent,
    PrepBriefContent,
    ResumeContent,
    TailoredWorkEntry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_CONTEXT = {
    "basics": {
        "name": "Test User",
        "label": "Senior ML Engineer",
        "email": "test@example.com",
    },
    "company": "TestCo",
    "job_title": "ML Engineer",
    "date": "April 6, 2026",
}


def _make_resume_content() -> ResumeContent:
    return ResumeContent(
        summary="Experienced ML engineer with 3+ years building production systems.",
        relevant_experience=[
            TailoredWorkEntry(
                company="TestCo",
                position="ML Engineer",
                start_date="2020-01",
                end_date="2023-06",
                highlights=["Built ML pipeline processing 1M records/day"],
            )
        ],
        highlighted_skills=["Python", "PyTorch"],
        education=[
            {"institution": "Test University", "area": "Computer Science", "studyType": "MS"}
        ],
    )


def _make_cover_letter_content() -> CoverLetterContent:
    return CoverLetterContent(
        opening="I am excited to apply for the ML Engineer role at TestCo.",
        body_paragraphs=[
            "My experience building ML pipelines directly aligns with your requirements.",
            "I have extensive Python and PyTorch expertise.",
        ],
        closing="I look forward to discussing my fit for this role.",
    )


def _make_prep_brief_content() -> PrepBriefContent:
    return PrepBriefContent(
        company_overview="TestCo is a technology company focused on ML solutions.",
        role_summary="Lead ML efforts and build production ML systems.",
        likely_questions=[
            "Tell me about your experience with ML pipelines.",
            "How do you handle model drift in production?",
        ],
        talking_points=[
            "Built ML pipeline at TestCo processing 1M records/day.",
        ],
        gaps_to_address=["Limited cloud experience — address by highlighting on-prem scale."],
    )


# ---------------------------------------------------------------------------
# Tests: HTML rendering
# ---------------------------------------------------------------------------


def test_render_resume_html():
    """render_html('resume', ...) returns HTML containing summary and experience."""
    from jobinator.generation.renderer import render_html

    content = _make_resume_content()
    html = render_html("resume", content, MOCK_CONTEXT)

    assert isinstance(html, str)
    assert "Test User" in html
    assert content.summary in html
    assert "TestCo" in html
    assert "ML Engineer" in html
    assert "1M records/day" in html


def test_render_cover_letter_html():
    """render_html('cover_letter', ...) returns HTML containing opening and paragraphs."""
    from jobinator.generation.renderer import render_html

    content = _make_cover_letter_content()
    html = render_html("cover_letter", content, MOCK_CONTEXT)

    assert isinstance(html, str)
    assert content.opening in html
    assert content.body_paragraphs[0] in html
    assert content.closing in html


def test_render_prep_brief_html():
    """render_html('prep_brief', ...) returns HTML containing questions and talking points."""
    from jobinator.generation.renderer import render_html

    content = _make_prep_brief_content()
    html = render_html("prep_brief", content, MOCK_CONTEXT)

    assert isinstance(html, str)
    assert content.company_overview in html
    assert content.likely_questions[0] in html
    assert content.talking_points[0] in html


# ---------------------------------------------------------------------------
# Tests: PDF rendering
# ---------------------------------------------------------------------------


def test_render_pdf_produces_valid_bytes():
    """render_pdf('resume', ...) returns bytes starting with PDF magic bytes."""
    from jobinator.generation.renderer import render_pdf

    content = _make_resume_content()
    pdf_bytes = render_pdf("resume", content, MOCK_CONTEXT)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 100


def test_render_pdf_cover_letter():
    """render_pdf('cover_letter', ...) returns valid PDF bytes."""
    from jobinator.generation.renderer import render_pdf

    content = _make_cover_letter_content()
    pdf_bytes = render_pdf("cover_letter", content, MOCK_CONTEXT)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 100


def test_render_pdf_prep_brief():
    """render_pdf('prep_brief', ...) returns valid PDF bytes."""
    from jobinator.generation.renderer import render_pdf

    content = _make_prep_brief_content()
    pdf_bytes = render_pdf("prep_brief", content, MOCK_CONTEXT)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 100
