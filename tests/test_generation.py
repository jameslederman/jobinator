"""Tests for MaterialsGenerator: structured content generation and budget gating."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from jobinator.budget.tracker import BudgetExceeded
from jobinator.configs.settings import MaterialsConfig
from jobinator.generation.models import (
    CoverLetterContent,
    PrepBriefContent,
    ResumeContent,
    TailoredWorkEntry,
)
from jobinator.models.budget import SpendRecord
from jobinator.models.job import NormalizedJob
from jobinator.models.score import JobScore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_PROFILE = {
    "basics": {
        "name": "Test User",
        "label": "Senior ML Engineer",
        "email": "test@example.com",
    },
    "work": [
        {
            "company": "TestCo",
            "position": "ML Engineer",
            "startDate": "2020-01",
            "endDate": "2023-06",
            "highlights": ["Built ML pipeline processing 1M records/day"],
        }
    ],
    "skills": [
        {"name": "Python", "level": "Expert"},
        {"name": "PyTorch", "level": "Advanced"},
    ],
    "education": [
        {
            "institution": "Test University",
            "area": "Computer Science",
            "studyType": "MS",
        }
    ],
}


def _make_job() -> NormalizedJob:
    return NormalizedJob(
        source="greenhouse",
        source_url="https://example.com/jobs/1",
        title="Senior ML Engineer",
        title_normalized="senior ml engineer",
        company="Acme Corp",
        company_slug="acme-corp",
        description="We are looking for a senior ML engineer to lead our ML efforts.",
        requirements_raw="Python, PyTorch, 5+ years experience",
        description_hash=NormalizedJob.make_description_hash("We are looking"),
        raw_json="{}",
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )


def _make_score() -> JobScore:
    return JobScore(
        job_id="test-job-id",
        fit_score=0.85,
        priority_score=0.80,
        strengths_json=json.dumps(["Python expertise", "ML experience"]),
        gaps_json=json.dumps(["Limited cloud experience"]),
        compensation_estimate="$150k-$180k",
        reasoning="Strong overall fit.",
        model_used="claude-3-haiku-20240307",
    )


def _make_resume_content() -> ResumeContent:
    return ResumeContent(
        summary="Experienced ML engineer with 3+ years building production ML systems.",
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
        opening="I am excited to apply for the Senior ML Engineer role at Acme Corp.",
        body_paragraphs=[
            "My experience at TestCo building ML pipelines directly aligns.",
            "I have strong Python and PyTorch expertise.",
        ],
        closing="I look forward to discussing how I can contribute to Acme Corp.",
    )


def _make_prep_brief_content() -> PrepBriefContent:
    return PrepBriefContent(
        company_overview="Acme Corp is a technology company focused on ML.",
        role_summary="Lead ML efforts and build production systems.",
        likely_questions=[
            "Tell me about your experience with ML pipelines.",
            "How do you handle model degradation in production?",
        ],
        talking_points=[
            "Built ML pipeline at TestCo processing 1M records/day.",
        ],
        gaps_to_address=["Limited cloud experience — address by mentioning cloud course."],
    )


def _make_mock_raw(cost: float = 0.005) -> MagicMock:
    """Create a mock raw LiteLLM response with _hidden_params and usage."""
    raw = MagicMock()
    raw._hidden_params = {"response_cost": cost}
    raw.usage.prompt_tokens = 1000
    raw.usage.completion_tokens = 500
    return raw


def _make_budget_tracker() -> MagicMock:
    """Create a mock BudgetTracker that does nothing by default.

    Uses spec=BudgetTracker so that assert_within_limits (which starts with
    'assert') is recognized as a valid attribute, not a pytest assertion.
    """
    from jobinator.budget.tracker import BudgetTracker

    tracker = MagicMock(spec=BudgetTracker)
    tracker.assert_within_limits.return_value = None
    tracker.record.return_value = None
    return tracker


def _make_config() -> MaterialsConfig:
    return MaterialsConfig(strong_model="claude-3-5-sonnet-latest", max_retries=2)


# ---------------------------------------------------------------------------
# Tests: generate_resume
# ---------------------------------------------------------------------------


def test_generate_resume_returns_structured_content():
    """MaterialsGenerator.generate_resume() returns (ResumeContent, SpendRecord)."""
    from jobinator.generation.generator import MaterialsGenerator

    resume_content = _make_resume_content()
    mock_raw = _make_mock_raw()
    tracker = _make_budget_tracker()
    config = _make_config()
    job = _make_job()

    with patch("jobinator.generation.generator._client") as mock_client:
        mock_client.create_with_completion.return_value = (resume_content, mock_raw)
        generator = MaterialsGenerator(budget_tracker=tracker, config=config)
        result_content, spend = generator.generate_resume(job, MOCK_PROFILE)

    assert isinstance(result_content, ResumeContent)
    assert isinstance(spend, SpendRecord)
    assert result_content.summary == resume_content.summary


def test_generate_cover_letter():
    """MaterialsGenerator.generate_cover_letter() returns (CoverLetterContent, SpendRecord)."""
    from jobinator.generation.generator import MaterialsGenerator

    cl_content = _make_cover_letter_content()
    mock_raw = _make_mock_raw()
    tracker = _make_budget_tracker()
    config = _make_config()
    job = _make_job()

    with patch("jobinator.generation.generator._client") as mock_client:
        mock_client.create_with_completion.return_value = (cl_content, mock_raw)
        generator = MaterialsGenerator(budget_tracker=tracker, config=config)
        result_content, spend = generator.generate_cover_letter(job, MOCK_PROFILE)

    assert isinstance(result_content, CoverLetterContent)
    assert isinstance(spend, SpendRecord)
    assert result_content.opening == cl_content.opening


def test_generate_prep_brief():
    """MaterialsGenerator.generate_prep_brief() returns (PrepBriefContent, SpendRecord)."""
    from jobinator.generation.generator import MaterialsGenerator

    brief_content = _make_prep_brief_content()
    mock_raw = _make_mock_raw()
    tracker = _make_budget_tracker()
    config = _make_config()
    job = _make_job()

    with patch("jobinator.generation.generator._client") as mock_client:
        mock_client.create_with_completion.return_value = (brief_content, mock_raw)
        generator = MaterialsGenerator(budget_tracker=tracker, config=config)
        result_content, spend = generator.generate_prep_brief(job, MOCK_PROFILE)

    assert isinstance(result_content, PrepBriefContent)
    assert isinstance(spend, SpendRecord)
    assert result_content.company_overview == brief_content.company_overview


# ---------------------------------------------------------------------------
# Tests: budget gating
# ---------------------------------------------------------------------------


def test_budget_gated_before_each_call():
    """assert_within_limits is called BEFORE each LLM call, once per generate method."""
    from jobinator.generation.generator import MaterialsGenerator

    tracker = _make_budget_tracker()
    config = _make_config()
    job = _make_job()

    resume_content = _make_resume_content()
    cl_content = _make_cover_letter_content()
    brief_content = _make_prep_brief_content()
    mock_raw = _make_mock_raw()

    with patch("jobinator.generation.generator._client") as mock_client:
        # Each call returns a different content type
        mock_client.create_with_completion.side_effect = [
            (resume_content, mock_raw),
            (cl_content, mock_raw),
            (brief_content, mock_raw),
        ]
        generator = MaterialsGenerator(budget_tracker=tracker, config=config)
        generator.generate_resume(job, MOCK_PROFILE)
        generator.generate_cover_letter(job, MOCK_PROFILE)
        generator.generate_prep_brief(job, MOCK_PROFILE)

    # assert_within_limits called exactly 3 times (once per method)
    assert tracker.assert_within_limits.call_count == 3

    # Each call was with job.id
    expected_calls = [call(job_id=job.id)] * 3
    tracker.assert_within_limits.assert_has_calls(expected_calls)


def test_budget_exceeded_stops_generation():
    """When assert_within_limits raises BudgetExceeded, LLM call is NOT made."""
    from jobinator.generation.generator import MaterialsGenerator

    tracker = _make_budget_tracker()
    tracker.assert_within_limits.side_effect = BudgetExceeded("Daily budget exhausted")
    config = _make_config()
    job = _make_job()

    with patch("jobinator.generation.generator._client") as mock_client:
        generator = MaterialsGenerator(budget_tracker=tracker, config=config)
        with pytest.raises(BudgetExceeded):
            generator.generate_resume(job, MOCK_PROFILE)

        # LLM must NOT have been called
        mock_client.create_with_completion.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: prompt grounding
# ---------------------------------------------------------------------------


def test_resume_grounding_no_invented_content():
    """build_resume_prompt system message contains full profile JSON and grounding rules."""
    from jobinator.generation.prompts import build_resume_prompt

    job = _make_job()
    messages = build_resume_prompt(MOCK_PROFILE, job)

    assert len(messages) == 2
    system_content = messages[0]["content"]

    # Must contain the full profile JSON
    assert "Test User" in system_content
    assert "TestCo" in system_content

    # Must contain grounding instructions
    assert "ONLY source of truth" in system_content
    # Either "Do NOT invent" or "NOT INVENT" (from plan acceptance criteria)
    assert "NOT INVENT" in system_content.upper() or "Do NOT invent" in system_content


# ---------------------------------------------------------------------------
# Tests: spend record operation names
# ---------------------------------------------------------------------------


def test_spend_record_operation_names():
    """SpendRecord.operation matches generate_resume/generate_cover_letter/generate_prep_brief."""
    from jobinator.generation.generator import MaterialsGenerator

    resume_content = _make_resume_content()
    cl_content = _make_cover_letter_content()
    brief_content = _make_prep_brief_content()
    mock_raw = _make_mock_raw()
    tracker = _make_budget_tracker()
    config = _make_config()
    job = _make_job()

    with patch("jobinator.generation.generator._client") as mock_client:
        mock_client.create_with_completion.side_effect = [
            (resume_content, mock_raw),
            (cl_content, mock_raw),
            (brief_content, mock_raw),
        ]
        generator = MaterialsGenerator(budget_tracker=tracker, config=config)
        _, spend_resume = generator.generate_resume(job, MOCK_PROFILE)
        _, spend_cl = generator.generate_cover_letter(job, MOCK_PROFILE)
        _, spend_brief = generator.generate_prep_brief(job, MOCK_PROFILE)

    assert spend_resume.operation == "generate_resume"
    assert spend_cl.operation == "generate_cover_letter"
    assert spend_brief.operation == "generate_prep_brief"
