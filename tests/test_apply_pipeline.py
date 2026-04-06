"""Tests for the apply pipeline orchestrator (apply.py).

TDD: tests were written first. Run:
  uv run pytest tests/test_apply_pipeline.py -x -q
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from sqlmodel import Session, SQLModel, create_engine, select

from jobinator.budget.tracker import BudgetExceeded, BudgetTracker
from jobinator.configs.settings import MaterialsConfig
from jobinator.generation.models import (
    CoverLetterContent,
    PrepBriefContent,
    ResumeContent,
    TailoredWorkEntry,
)
from jobinator.models.budget import SpendRecord
from jobinator.models.job import NormalizedJob
from jobinator.models.material import GeneratedMaterial
from jobinator.models.score import JobScore
from jobinator.pipelines.apply import run_apply

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_session():
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def sample_job() -> NormalizedJob:
    return NormalizedJob(
        id="job-apply-001",
        source="greenhouse",
        source_url="https://example.com/jobs/apply-001",
        title="Senior ML Engineer",
        title_normalized="senior ml engineer",
        company="AcmeCorp",
        company_slug="acmecorp",
        description="We need a senior ML engineer to build large-scale models.",
        description_hash=NormalizedJob.make_description_hash(
            "We need a senior ML engineer to build large-scale models."
        ),
        raw_json="{}",
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        is_stale=False,
    )


@pytest.fixture()
def sample_score(sample_job: NormalizedJob) -> JobScore:
    return JobScore(
        job_id=sample_job.id,
        fit_score=0.85,
        priority_score=0.80,
        strengths_json=json.dumps(["Python", "ML systems"]),
        gaps_json=json.dumps(["Kubernetes"]),
        reasoning="Strong ML background, minor gap in k8s.",
        model_used="claude-3-haiku-20240307",
    )


@pytest.fixture()
def sample_profile() -> dict:
    return {
        "basics": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "label": "Senior Data Scientist",
        },
        "work": [
            {
                "company": "TechStartup",
                "position": "ML Engineer",
                "startDate": "2021-01",
                "endDate": "Present",
                "highlights": ["Built recommendation system", "Led ML platform"],
            }
        ],
        "skills": [{"name": "Python"}, {"name": "Machine Learning"}],
        "education": [
            {
                "institution": "MIT",
                "studyType": "MS",
                "area": "Computer Science",
            }
        ],
    }


@pytest.fixture()
def sample_resume_content() -> ResumeContent:
    return ResumeContent(
        summary="Experienced ML engineer with 5 years building production systems.",
        relevant_experience=[
            TailoredWorkEntry(
                company="TechStartup",
                position="ML Engineer",
                start_date="2021-01",
                end_date="Present",
                highlights=["Built recommendation system", "Led ML platform"],
            )
        ],
        highlighted_skills=["Python", "Machine Learning"],
        education=[{"institution": "MIT", "studyType": "MS", "area": "Computer Science"}],
    )


@pytest.fixture()
def sample_cover_content() -> CoverLetterContent:
    return CoverLetterContent(
        opening="I am excited to apply for the Senior ML Engineer position at AcmeCorp.",
        body_paragraphs=[
            "My experience building large-scale ML systems makes me a strong fit.",
            "I've led end-to-end model development at TechStartup.",
        ],
        closing="I look forward to discussing this opportunity.",
    )


@pytest.fixture()
def sample_prep_content() -> PrepBriefContent:
    return PrepBriefContent(
        company_overview="AcmeCorp is a leading technology company.",
        role_summary="Build large-scale ML models for production.",
        likely_questions=[
            "Describe your ML system design process.",
            "How do you handle model drift?",
            "Explain your approach to A/B testing.",
        ],
        talking_points=["Built recommendation system at scale", "Led ML platform"],
        gaps_to_address=["Kubernetes: can discuss learning approach"],
    )


@pytest.fixture()
def sample_spend() -> SpendRecord:
    return SpendRecord(
        job_id="job-apply-001",
        model_name="claude-3-5-sonnet-latest",
        provider="anthropic",
        operation="generate_resume",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.01,
    )


def make_mock_generator(resume_content, cover_content, prep_content, spend):
    """Create a mock MaterialsGenerator with fixed return values."""
    from jobinator.generation.generator import MaterialsGenerator

    mock_gen = MagicMock(spec=MaterialsGenerator)
    mock_gen.generate_resume.return_value = (resume_content, spend)
    mock_gen.generate_cover_letter.return_value = (cover_content, spend)
    mock_gen.generate_prep_brief.return_value = (prep_content, spend)
    return mock_gen


def make_mock_budget_tracker(session):
    """Create a mock BudgetTracker."""
    mock_tracker = MagicMock(spec=BudgetTracker)
    mock_tracker.daily_spend.return_value = 0.0
    return mock_tracker


def make_materials_config(output_dir: str, apply_threshold: float = 0.6) -> MaterialsConfig:
    return MaterialsConfig(
        strong_model="claude-3-5-sonnet-latest",
        apply_threshold=apply_threshold,
        profile_path=None,
        output_dir=output_dir,
        max_retries=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunApplyGeneratesAllMaterials:
    """test_run_apply_generates_all_three_materials"""

    def test_all_three_generate_methods_called(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        mock_gen.generate_resume.assert_called_once()
        mock_gen.generate_cover_letter.assert_called_once()
        mock_gen.generate_prep_brief.assert_called_once()
        assert result.success is True

    def test_all_three_render_pdf_calls_made(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test") as mock_pdf:
            run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        # render_pdf called for resume, cover_letter, prep_brief
        assert mock_pdf.call_count == 3
        call_args = [c.args[0] for c in mock_pdf.call_args_list]
        assert "resume" in call_args
        assert "cover_letter" in call_args
        assert "prep_brief" in call_args


class TestRunApplyWritesFiles:
    """test_run_apply_writes_files_after_confirm"""

    def test_all_expected_files_written(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        assert result.success is True
        bundle_path = Path(result.bundle_path)

        # Check all expected files
        assert (bundle_path / "resume.pdf").exists()
        assert (bundle_path / "cover_letter.pdf").exists()
        assert (bundle_path / "prep_brief.pdf").exists()
        assert (bundle_path / "resume.md").exists()
        assert (bundle_path / "cover_letter.md").exists()
        assert (bundle_path / "prep_brief.md").exists()
        assert (bundle_path / "metadata.json").exists()
        assert (bundle_path / "job_description.md").exists()
        assert (bundle_path / "scoring.json").exists()


class TestRunApplyAbortIfUserDeclines:
    """test_run_apply_aborts_if_user_declines"""

    def test_no_files_written_on_decline(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        def decline(*args, **kwargs):
            raise typer.Abort()

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=decline,
            )

        assert result.confirmed is False
        assert result.success is False

        # No output directories should have been created
        # (bundle_path is None because we never wrote)
        assert result.bundle_path is None

        # No files written: tmp_path should be empty (or only have base structure, not files)
        pdf_files = list(tmp_path.rglob("*.pdf"))
        assert len(pdf_files) == 0


class TestRunApplyVersionedDirectory:
    """test_run_apply_creates_versioned_directory"""

    def test_two_applies_create_different_dirs(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        import time

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result1 = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        time.sleep(1.1)  # ensure different timestamp

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result2 = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        assert result1.bundle_path != result2.bundle_path
        assert Path(result1.bundle_path).exists()
        assert Path(result2.bundle_path).exists()


class TestRunApplyBudgetExceeded:
    """test_run_apply_budget_exceeded"""

    def test_budget_exceeded_on_resume_generation(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        from jobinator.generation.generator import MaterialsGenerator

        mock_gen = MagicMock(spec=MaterialsGenerator)
        mock_gen.generate_resume.side_effect = BudgetExceeded("Daily budget exhausted")

        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        assert result.budget_stopped is True
        assert result.success is False
        assert result.bundle_path is None

        # No files should be written
        pdf_files = list(tmp_path.rglob("*.pdf"))
        assert len(pdf_files) == 0


class TestRunApplyPersistsRecord:
    """test_run_apply_persists_generated_material_record"""

    def test_generated_material_row_created(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        assert result.success is True

        # Verify GeneratedMaterial row in DB
        material = in_memory_session.exec(
            select(GeneratedMaterial).where(GeneratedMaterial.job_id == sample_job.id)
        ).first()

        assert material is not None
        assert material.job_id == sample_job.id
        assert material.bundle_path == result.bundle_path
        assert material.model_used == config.strong_model
        assert material.confirmed is True


class TestRunApplyThresholdCheck:
    """test_run_apply_checks_fit_score_threshold"""

    def test_below_threshold_returns_error(
        self,
        in_memory_session,
        sample_job,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        # Score below threshold
        low_score = JobScore(
            job_id=sample_job.id,
            fit_score=0.3,
            priority_score=0.2,
            strengths_json=json.dumps(["Python"]),
            gaps_json=json.dumps(["Kubernetes", "Spark"]),
            reasoning="Poor fit.",
            model_used="claude-3-haiku-20240307",
        )
        in_memory_session.add(sample_job)
        in_memory_session.add(low_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path), apply_threshold=0.6)

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=low_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        assert result.success is False
        assert len(result.errors) > 0
        assert "apply_threshold" in result.errors[0] or "threshold" in result.errors[0].lower()

        # No LLM calls made
        mock_gen.generate_resume.assert_not_called()


class TestRunApplyLogsDecision:
    """test_run_apply_logs_apply_decision"""

    def test_log_decision_called_with_apply_approve(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=lambda msg, abort=False: None,
            )

        assert result.success is True
        mock_tracker.log_decision.assert_called()
        calls = [
            c.kwargs.get("decision_type") or c.args[0]
            for c in mock_tracker.log_decision.call_args_list
        ]
        assert "apply_approve" in calls

    def test_log_decision_called_with_apply_decline_on_abort(
        self,
        in_memory_session,
        sample_job,
        sample_score,
        sample_profile,
        sample_resume_content,
        sample_cover_content,
        sample_prep_content,
        sample_spend,
        tmp_path,
    ):
        in_memory_session.add(sample_job)
        in_memory_session.add(sample_score)
        in_memory_session.commit()

        mock_gen = make_mock_generator(
            sample_resume_content, sample_cover_content, sample_prep_content, sample_spend
        )
        mock_tracker = make_mock_budget_tracker(in_memory_session)
        config = make_materials_config(str(tmp_path))

        def decline(*args, **kwargs):
            raise typer.Abort()

        with patch("jobinator.pipelines.apply.render_pdf", return_value=b"%PDF-test"):
            result = run_apply(
                session=in_memory_session,
                job=sample_job,
                score=sample_score,
                profile_data=sample_profile,
                generator=mock_gen,
                budget_tracker=mock_tracker,
                config=config,
                confirm_callback=decline,
            )

        assert result.confirmed is False
        mock_tracker.log_decision.assert_called()
        calls = [
            c.kwargs.get("decision_type") or c.args[0]
            for c in mock_tracker.log_decision.call_args_list
        ]
        assert "apply_decline" in calls
