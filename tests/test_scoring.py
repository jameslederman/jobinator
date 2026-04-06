"""Tests for JobScore model, JobScoreOutput Pydantic model, and ScoringConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.exc import IntegrityError

# Import all models to register them with SQLModel.metadata
from jobinator.models import DecisionLog, NormalizedJob, SpendRecord, StatusEvent  # noqa: F401
from jobinator.models.score import JobScore, JobScoreOutput
from jobinator.configs.settings import ScoringConfig, get_scoring_config


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """SQLModel session backed by in-memory engine."""
    with Session(engine) as sess:
        yield sess


@pytest.fixture
def sample_job(session) -> NormalizedJob:
    """A persisted NormalizedJob for FK references."""
    job = NormalizedJob(
        source="greenhouse",
        source_url="https://example.com/jobs/1",
        title="Senior Data Scientist",
        title_normalized="senior data scientist",
        company="Acme Corp",
        company_slug="acme-corp",
        description="A great role",
        description_hash=NormalizedJob.make_description_hash("A great role"),
        raw_json="{}",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# JobScore model tests
# ---------------------------------------------------------------------------


class TestJobScore:
    def test_job_score_can_be_created_with_all_required_fields(self, session, sample_job):
        """JobScore can be created with all required fields."""
        score = JobScore(
            job_id=sample_job.id,
            fit_score=0.85,
            priority_score=0.75,
            strengths_json='["Strong Python skills", "ML experience"]',
            gaps_json='["No fintech experience"]',
            reasoning="The candidate has strong ML skills relevant to this role.",
            model_used="claude-3-haiku-20240307",
        )
        session.add(score)
        session.commit()
        session.refresh(score)

        assert score.id is not None
        assert score.job_id == sample_job.id
        assert score.fit_score == 0.85
        assert score.priority_score == 0.75
        assert score.strengths_json == '["Strong Python skills", "ML experience"]'
        assert score.gaps_json == '["No fintech experience"]'
        assert score.reasoning == "The candidate has strong ML skills relevant to this role."
        assert score.model_used == "claude-3-haiku-20240307"
        assert score.scored_at is not None

    def test_job_score_job_id_unique_constraint(self, session, sample_job):
        """Two JobScore records with same job_id should raise IntegrityError."""
        score1 = JobScore(
            job_id=sample_job.id,
            fit_score=0.8,
            priority_score=0.7,
            strengths_json="[]",
            gaps_json="[]",
            reasoning="Reasoning 1",
            model_used="claude-3-haiku-20240307",
        )
        session.add(score1)
        session.commit()

        score2 = JobScore(
            job_id=sample_job.id,
            fit_score=0.9,
            priority_score=0.8,
            strengths_json="[]",
            gaps_json="[]",
            reasoning="Reasoning 2",
            model_used="claude-3-haiku-20240307",
        )
        session.add(score2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_job_score_fit_score_stores_float(self, session, sample_job):
        """JobScore.fit_score accepts float values between 0.0 and 1.0."""
        score = JobScore(
            job_id=sample_job.id,
            fit_score=0.5,
            priority_score=0.5,
            strengths_json="[]",
            gaps_json="[]",
            reasoning="Neutral fit",
            model_used="claude-3-haiku-20240307",
        )
        session.add(score)
        session.commit()
        session.refresh(score)

        assert isinstance(score.fit_score, float)
        assert score.fit_score == 0.5

    def test_job_score_optional_compensation_estimate(self, session, sample_job):
        """compensation_estimate is optional and defaults to None."""
        score = JobScore(
            job_id=sample_job.id,
            fit_score=0.7,
            priority_score=0.7,
            strengths_json="[]",
            gaps_json="[]",
            reasoning="Some reasoning",
            model_used="claude-3-haiku-20240307",
        )
        session.add(score)
        session.commit()
        session.refresh(score)

        assert score.compensation_estimate is None


# ---------------------------------------------------------------------------
# JobScoreOutput Pydantic model tests
# ---------------------------------------------------------------------------


class TestJobScoreOutput:
    def test_job_score_output_validates_fit_score_range(self):
        """JobScoreOutput validates fit_score within [0.0, 1.0]."""
        output = JobScoreOutput(
            fit_score=0.75,
            strengths_match=["Strong Python"],
            gaps=["No domain experience"],
            priority_score=0.7,
            reasoning="Good overall fit for the role.",
        )
        assert output.fit_score == 0.75

    def test_job_score_output_rejects_fit_score_above_one(self):
        """JobScoreOutput rejects fit_score > 1.0."""
        with pytest.raises(ValidationError):
            JobScoreOutput(
                fit_score=1.5,
                strengths_match=["Strong Python"],
                gaps=[],
                priority_score=0.7,
                reasoning="Above range.",
            )

    def test_job_score_output_rejects_fit_score_below_zero(self):
        """JobScoreOutput rejects fit_score < 0.0."""
        with pytest.raises(ValidationError):
            JobScoreOutput(
                fit_score=-0.1,
                strengths_match=["Strong Python"],
                gaps=[],
                priority_score=0.7,
                reasoning="Below range.",
            )

    def test_job_score_output_rejects_priority_score_above_one(self):
        """JobScoreOutput rejects priority_score > 1.0."""
        with pytest.raises(ValidationError):
            JobScoreOutput(
                fit_score=0.8,
                strengths_match=[],
                gaps=[],
                priority_score=1.5,
                reasoning="Above range.",
            )

    def test_job_score_output_compensation_estimate_default(self):
        """JobScoreOutput compensation_estimate defaults to 'unknown'."""
        output = JobScoreOutput(
            fit_score=0.8,
            strengths_match=["Strong ML skills"],
            gaps=[],
            priority_score=0.75,
            reasoning="Great fit overall.",
        )
        assert output.compensation_estimate == "unknown"


# ---------------------------------------------------------------------------
# ScoringConfig tests
# ---------------------------------------------------------------------------


class TestScoringConfig:
    def test_scoring_config_default_cheap_model(self):
        """ScoringConfig defaults to claude-3-haiku-20240307 for cheap_model."""
        cfg = ScoringConfig()
        assert cfg.cheap_model == "claude-3-haiku-20240307"

    def test_scoring_config_default_strong_model(self):
        """ScoringConfig defaults to claude-3-5-sonnet-latest for strong_model."""
        cfg = ScoringConfig()
        assert cfg.strong_model == "claude-3-5-sonnet-latest"

    def test_scoring_config_default_score_batch_size(self):
        """ScoringConfig defaults score_batch_size to 10."""
        cfg = ScoringConfig()
        assert cfg.score_batch_size == 10

    def test_scoring_config_default_min_fit_score_threshold(self):
        """ScoringConfig defaults min_fit_score_threshold to 0.5."""
        cfg = ScoringConfig()
        assert cfg.min_fit_score_threshold == 0.5

    def test_scoring_config_can_be_overridden(self):
        """ScoringConfig can be overridden with keyword args (test-overridable BaseModel pattern)."""
        cfg = ScoringConfig(
            cheap_model="gpt-4o-mini",
            strong_model="gpt-4o",
            score_batch_size=5,
            min_fit_score_threshold=0.7,
        )
        assert cfg.cheap_model == "gpt-4o-mini"
        assert cfg.strong_model == "gpt-4o"
        assert cfg.score_batch_size == 5
        assert cfg.min_fit_score_threshold == 0.7

    def test_scoring_config_default_priority_weights(self):
        """ScoringConfig has default priority_weights with fit, recency, urgency."""
        cfg = ScoringConfig()
        assert "fit" in cfg.priority_weights
        assert "recency" in cfg.priority_weights
        assert "urgency" in cfg.priority_weights
        assert cfg.priority_weights["fit"] == 0.6
        assert cfg.priority_weights["recency"] == 0.2
        assert cfg.priority_weights["urgency"] == 0.2


class TestGetScoringConfig:
    def test_get_scoring_config_returns_defaults_when_no_config_toml(self, tmp_path):
        """get_scoring_config() returns ScoringConfig with defaults when no config.toml exists."""
        cfg = get_scoring_config(config_dir=str(tmp_path))
        assert isinstance(cfg, ScoringConfig)
        assert cfg.cheap_model == "claude-3-haiku-20240307"
        assert cfg.strong_model == "claude-3-5-sonnet-latest"
        assert cfg.score_batch_size == 10
        assert cfg.min_fit_score_threshold == 0.5

    def test_get_scoring_config_reads_from_config_toml(self, tmp_path):
        """get_scoring_config() reads [scoring] section from config.toml."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[scoring]\ncheap_model = "gpt-4o-mini"\nmin_fit_score_threshold = 0.6\n'
        )
        cfg = get_scoring_config(config_dir=str(tmp_path))
        assert cfg.cheap_model == "gpt-4o-mini"
        assert cfg.min_fit_score_threshold == 0.6
        # Unspecified fields should still be defaults
        assert cfg.strong_model == "claude-3-5-sonnet-latest"
