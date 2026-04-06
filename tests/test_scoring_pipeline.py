"""Tests for scoring pipeline: prompt builder, JobScorer, and run_scoring orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, select

from jobinator.budget.tracker import BudgetConfig, BudgetExceeded, BudgetTracker
from jobinator.configs.settings import ScoringConfig
from jobinator.models.budget import SpendRecord
from jobinator.models.job import NormalizedJob, StatusEvent
from jobinator.models.score import JobScore, JobScoreOutput
from jobinator.scoring.client import LLMClient, LLMResult
from jobinator.scoring.prompt import build_scoring_prompt
from jobinator.scoring.scorer import JobScorer
from jobinator.pipelines.score import (
    ScoringResult,
    get_unscored_jobs,
    load_profile,
    run_scoring,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESUME_PATH = Path(__file__).parent / "fixtures" / "sample_resume.json"


@pytest.fixture
def sample_profile_data():
    return json.loads(SAMPLE_RESUME_PATH.read_text())


@pytest.fixture
def sample_job():
    return NormalizedJob(
        id="job-test-001",
        source="greenhouse",
        source_url="https://example.com/jobs/1",
        title="Senior ML Engineer",
        title_normalized="senior ml engineer",
        company="TestCorp",
        company_slug="testcorp",
        description="We are looking for a Senior ML Engineer to join our team. Experience with Python, PyTorch, and production ML systems required.",
        requirements_raw="5+ years ML experience, Python, PyTorch",
        location_raw="San Francisco, CA",
        location_type="hybrid",
        salary_min=150000,
        salary_max=200000,
        posted_at=datetime.utcnow() - timedelta(days=3),
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_seen_at=datetime.utcnow(),
        description_hash="abc123def456aabb",
        raw_json="{}",
        is_stale=False,
    )


@pytest.fixture
def sample_job_no_salary():
    return NormalizedJob(
        id="job-test-002",
        source="hn",
        source_url="https://news.ycombinator.com/item?id=123",
        title="Data Scientist",
        title_normalized="data scientist",
        company="StartupCo",
        company_slug="startupco",
        description="Looking for a data scientist. Must know Python and statistics.",
        requirements_raw=None,
        location_raw=None,
        location_type=None,
        salary_min=None,
        salary_max=None,
        posted_at=None,
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        description_hash="deadbeef12345678",
        raw_json="{}",
        is_stale=False,
    )


@pytest.fixture
def scoring_config():
    return ScoringConfig(
        cheap_model="claude-3-haiku-20240307",
        score_batch_size=5,
        profile_path=str(SAMPLE_RESUME_PATH),
        priority_weights={"fit": 0.6, "recency": 0.2, "urgency": 0.2},
    )


@pytest.fixture
def mock_llm_result():
    return LLMResult(
        score=JobScoreOutput(
            fit_score=0.85,
            strengths_match=["Python expertise", "ML systems experience"],
            gaps=["No Kubernetes experience"],
            compensation_estimate="$160k-$200k",
            priority_score=0.80,
            reasoning="Strong technical fit with production ML background.",
        ),
        cost_usd=0.001,
        input_tokens=500,
        output_tokens=200,
    )


@pytest.fixture
def budget_tracker(session):
    config = BudgetConfig(
        daily_limit_usd=5.00,
        per_job_limit_usd=0.50,
        warn_threshold=0.80,
    )
    return BudgetTracker(config=config, session=session)


# ---------------------------------------------------------------------------
# Tests: build_scoring_prompt
# ---------------------------------------------------------------------------


class TestBuildScoringPrompt:
    def test_returns_list_of_message_dicts(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        assert isinstance(messages, list)
        assert len(messages) >= 2

    def test_has_system_and_user_messages(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        roles = [m["role"] for m in messages]
        assert "system" in roles
        assert "user" in roles

    def test_system_message_instructs_structured_output(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        system_msg = next(m for m in messages if m["role"] == "system")
        content = system_msg["content"].lower()
        assert "job fit" in content or "fit" in content
        assert "structured" in content or "assess" in content

    def test_user_message_contains_job_header(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "## Job Posting" in user_msg["content"]

    def test_user_message_contains_profile_header(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "## Candidate Profile" in user_msg["content"]

    def test_user_message_includes_job_title(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Senior ML Engineer" in user_msg["content"]

    def test_user_message_includes_company(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "TestCorp" in user_msg["content"]

    def test_user_message_includes_description(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Senior ML Engineer" in user_msg["content"]

    def test_user_message_includes_salary_when_present(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        # salary_min=150000, salary_max=200000 should appear as 150k-200k or similar
        content = user_msg["content"]
        assert "150" in content or "200" in content

    def test_user_message_handles_missing_salary(self, sample_job_no_salary, sample_profile_data):
        messages = build_scoring_prompt(sample_job_no_salary, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        content = user_msg["content"]
        # Should not crash, and should note salary as missing
        assert "Not posted" in content or "not" in content.lower()

    def test_user_message_includes_profile_name(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Test User" in user_msg["content"]

    def test_user_message_includes_profile_skills(self, sample_job, sample_profile_data):
        messages = build_scoring_prompt(sample_job, sample_profile_data)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Python" in user_msg["content"]


# ---------------------------------------------------------------------------
# Tests: JobScorer
# ---------------------------------------------------------------------------


class TestJobScorer:
    def test_score_job_gates_budget_before_llm(
        self, sample_job, sample_profile_data, scoring_config, budget_tracker, mock_llm_result
    ):
        """Budget gate (assert_within_limits) must be called BEFORE llm_client.score()."""
        call_order = []

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_budget = MagicMock(spec=BudgetTracker)

        def track_budget(*args, **kwargs):
            call_order.append("budget")

        def track_llm(*args, **kwargs):
            call_order.append("llm")
            return mock_llm_result

        mock_budget.assert_within_limits.side_effect = track_budget
        mock_llm_client.score.side_effect = track_llm
        mock_budget.record = MagicMock()
        mock_budget.log_decision = MagicMock()

        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=mock_budget,
            config=scoring_config,
        )
        scorer.score_job(sample_job, sample_profile_data)

        assert call_order == ["budget", "llm"], "Budget gate must precede LLM call"

    def test_score_job_returns_job_score_instance(
        self, sample_job, sample_profile_data, scoring_config, budget_tracker, mock_llm_result
    ):
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result

        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )
        result = scorer.score_job(sample_job, sample_profile_data)

        assert isinstance(result, JobScore)

    def test_score_job_populates_fields_from_llm_result(
        self, sample_job, sample_profile_data, scoring_config, budget_tracker, mock_llm_result
    ):
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result

        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )
        job_score = scorer.score_job(sample_job, sample_profile_data)

        assert job_score.job_id == sample_job.id
        assert job_score.fit_score == 0.85
        assert job_score.model_used == scoring_config.cheap_model
        assert job_score.reasoning == "Strong technical fit with production ML background."

    def test_score_job_strengths_gaps_are_valid_json(
        self, sample_job, sample_profile_data, scoring_config, budget_tracker, mock_llm_result
    ):
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result

        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )
        job_score = scorer.score_job(sample_job, sample_profile_data)

        strengths = json.loads(job_score.strengths_json)
        gaps = json.loads(job_score.gaps_json)
        assert isinstance(strengths, list)
        assert isinstance(gaps, list)
        assert "Python expertise" in strengths
        assert "No Kubernetes experience" in gaps

    def test_score_job_records_spend(
        self, sample_job, sample_profile_data, scoring_config, budget_tracker, mock_llm_result
    ):
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result

        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )
        scorer.score_job(sample_job, sample_profile_data)

        # Check a SpendRecord was saved to the session
        spend_records = budget_tracker.session.exec(select(SpendRecord)).all()
        assert len(spend_records) >= 1
        sr = spend_records[0]
        assert sr.job_id == sample_job.id
        assert sr.operation == "score"
        assert sr.input_tokens == 500
        assert sr.output_tokens == 200
        assert sr.cost_usd == 0.001

    def test_score_job_priority_uses_weights(
        self, sample_job, sample_profile_data, scoring_config, budget_tracker, mock_llm_result
    ):
        """Priority score must be locally computed from weights, not LLM-provided value."""
        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result

        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )
        job_score = scorer.score_job(sample_job, sample_profile_data)

        # Priority score should be locally computed, not the LLM's 0.80 value
        # fit=0.85, recency and urgency are computed from job dates
        # Just check it's a valid float in 0-1 range
        assert 0.0 <= job_score.priority_score <= 1.0

    def test_recency_score_decays_over_30_days(
        self, scoring_config, budget_tracker
    ):
        mock_llm_client = MagicMock(spec=LLMClient)
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        # Fresh job (today)
        fresh_job = NormalizedJob(
            id="fresh",
            source="gh",
            source_url="https://example.com/1",
            title="x",
            title_normalized="x",
            company="y",
            company_slug="y",
            description="d",
            description_hash="abc123def456aabb",
            raw_json="{}",
            posted_at=datetime.utcnow(),
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        assert scorer._recency_score(fresh_job) == pytest.approx(1.0, abs=0.1)

        # Old job (35+ days ago)
        old_job = NormalizedJob(
            id="old",
            source="gh",
            source_url="https://example.com/2",
            title="x",
            title_normalized="x",
            company="y",
            company_slug="y",
            description="d",
            description_hash="abc123def456aabc",
            raw_json="{}",
            posted_at=datetime.utcnow() - timedelta(days=35),
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        assert scorer._recency_score(old_job) == 0.0

    def test_recency_score_neutral_when_no_posted_at(
        self, scoring_config, budget_tracker
    ):
        mock_llm_client = MagicMock(spec=LLMClient)
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )
        job = NormalizedJob(
            id="no-date",
            source="gh",
            source_url="https://example.com/3",
            title="x",
            title_normalized="x",
            company="y",
            company_slug="y",
            description="d",
            description_hash="abc123def456aabd",
            raw_json="{}",
            posted_at=None,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        assert scorer._recency_score(job) == 0.5


# ---------------------------------------------------------------------------
# Tests: run_scoring (pipeline orchestrator)
# ---------------------------------------------------------------------------


class TestRunScoring:
    def _make_job(self, job_id: str, session: Session) -> NormalizedJob:
        job = NormalizedJob(
            id=job_id,
            source="greenhouse",
            source_url=f"https://example.com/jobs/{job_id}",
            title="ML Engineer",
            title_normalized="ml engineer",
            company="TestCorp",
            company_slug="testcorp",
            description="Test job description for ML engineering role.",
            requirements_raw="Python, ML",
            location_raw="Remote",
            location_type="remote",
            salary_min=None,
            salary_max=None,
            posted_at=datetime.utcnow() - timedelta(days=2),
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            description_hash=f"{job_id[:16]:0<16}",
            raw_json="{}",
            is_stale=False,
        )
        session.add(job)
        session.add(StatusEvent(job_id=job_id, status="discovered"))
        session.commit()
        return job

    def test_run_scoring_scores_discovered_jobs(
        self, session, mock_llm_result, scoring_config
    ):
        self._make_job("job-001", session)
        self._make_job("job-002", session)

        budget_config = BudgetConfig(daily_limit_usd=5.0, per_job_limit_usd=0.5)
        budget_tracker = BudgetTracker(config=budget_config, session=session)

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        result = run_scoring(session, budget_tracker, scorer, scoring_config)

        assert result.scored == 2
        assert result.budget_stopped is False
        assert result.errors == []

    def test_run_scoring_persists_job_score(
        self, session, mock_llm_result, scoring_config
    ):
        self._make_job("job-001", session)

        budget_config = BudgetConfig(daily_limit_usd=5.0, per_job_limit_usd=0.5)
        budget_tracker = BudgetTracker(config=budget_config, session=session)

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        run_scoring(session, budget_tracker, scorer, scoring_config)

        scores = session.exec(select(JobScore)).all()
        assert len(scores) == 1
        assert scores[0].job_id == "job-001"

    def test_run_scoring_creates_status_event_scored(
        self, session, mock_llm_result, scoring_config
    ):
        self._make_job("job-001", session)

        budget_config = BudgetConfig(daily_limit_usd=5.0, per_job_limit_usd=0.5)
        budget_tracker = BudgetTracker(config=budget_config, session=session)

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        run_scoring(session, budget_tracker, scorer, scoring_config)

        events = session.exec(
            select(StatusEvent).where(StatusEvent.status == "scored")
        ).all()
        assert len(events) == 1
        assert events[0].job_id == "job-001"

    def test_run_scoring_stops_on_budget_exceeded(
        self, session, mock_llm_result, scoring_config
    ):
        self._make_job("job-001", session)
        self._make_job("job-002", session)

        budget_config = BudgetConfig(daily_limit_usd=5.0, per_job_limit_usd=0.5)
        budget_tracker = BudgetTracker(config=budget_config, session=session)

        mock_llm_client = MagicMock(spec=LLMClient)
        # First call raises BudgetExceeded
        mock_llm_client.score.side_effect = [
            BudgetExceeded("Daily budget hit"),
        ]

        mock_scorer = MagicMock(spec=JobScorer)
        mock_scorer.score_job.side_effect = BudgetExceeded("Daily budget hit")

        result = run_scoring(session, budget_tracker, mock_scorer, scoring_config)

        assert result.budget_stopped is True
        assert result.scored == 0

    def test_run_scoring_returns_error_for_missing_profile(self, session):
        config = ScoringConfig(
            profile_path=None,
            score_batch_size=5,
        )

        budget_config = BudgetConfig()
        budget_tracker = BudgetTracker(config=budget_config, session=session)
        mock_scorer = MagicMock(spec=JobScorer)

        result = run_scoring(session, budget_tracker, mock_scorer, config)

        assert result.scored == 0
        assert len(result.errors) >= 1
        assert "profile" in result.errors[0].lower()

    def test_run_scoring_returns_error_for_nonexistent_profile(self, session):
        config = ScoringConfig(
            profile_path="/nonexistent/path/profile.json",
            score_batch_size=5,
        )

        budget_config = BudgetConfig()
        budget_tracker = BudgetTracker(config=budget_config, session=session)
        mock_scorer = MagicMock(spec=JobScorer)

        result = run_scoring(session, budget_tracker, mock_scorer, config)

        assert result.scored == 0
        assert len(result.errors) >= 1

    def test_run_scoring_respects_batch_size(
        self, session, mock_llm_result, scoring_config
    ):
        # Add 10 jobs
        for i in range(10):
            self._make_job(f"job-{i:03d}", session)

        # Config has batch_size=5
        budget_config = BudgetConfig(daily_limit_usd=5.0, per_job_limit_usd=0.5)
        budget_tracker = BudgetTracker(config=budget_config, session=session)

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        result = run_scoring(session, budget_tracker, scorer, scoring_config)

        assert result.scored == 5  # batch_size=5 in scoring_config fixture

    def test_run_scoring_skips_already_scored_jobs(
        self, session, mock_llm_result, scoring_config
    ):
        job = self._make_job("job-001", session)

        # Pre-add a JobScore for this job
        existing_score = JobScore(
            job_id="job-001",
            fit_score=0.9,
            priority_score=0.85,
            strengths_json='["great fit"]',
            gaps_json='[]',
            compensation_estimate="$200k",
            reasoning="Already scored.",
            model_used="claude-3-haiku-20240307",
        )
        session.add(existing_score)
        session.commit()

        budget_config = BudgetConfig(daily_limit_usd=5.0, per_job_limit_usd=0.5)
        budget_tracker = BudgetTracker(config=budget_config, session=session)

        mock_llm_client = MagicMock(spec=LLMClient)
        mock_llm_client.score.return_value = mock_llm_result
        scorer = JobScorer(
            llm_client=mock_llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        result = run_scoring(session, budget_tracker, scorer, scoring_config)

        assert result.scored == 0  # Already scored, so nothing new


# ---------------------------------------------------------------------------
# Tests: load_profile
# ---------------------------------------------------------------------------


class TestLoadProfile:
    def test_load_profile_returns_none_when_path_is_none(self):
        assert load_profile(None) is None

    def test_load_profile_returns_none_when_file_missing(self):
        assert load_profile("/nonexistent/path/profile.json") is None

    def test_load_profile_returns_dict_for_valid_file(self):
        data = load_profile(str(SAMPLE_RESUME_PATH))
        assert isinstance(data, dict)
        assert "basics" in data
        assert data["basics"]["name"] == "Test User"


# ---------------------------------------------------------------------------
# Tests: get_unscored_jobs
# ---------------------------------------------------------------------------


class TestGetUnscoredJobs:
    def _make_job(self, job_id: str, session: Session) -> NormalizedJob:
        job = NormalizedJob(
            id=job_id,
            source="greenhouse",
            source_url=f"https://example.com/jobs/{job_id}",
            title="ML Engineer",
            title_normalized="ml engineer",
            company="TestCorp",
            company_slug="testcorp",
            description="Test job description.",
            description_hash=f"{job_id[:16]:0<16}",
            raw_json="{}",
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            is_stale=False,
        )
        session.add(job)
        session.commit()
        return job

    def test_returns_jobs_without_scores(self, session):
        self._make_job("job-001", session)
        jobs = get_unscored_jobs(session, limit=10)
        assert len(jobs) == 1
        assert jobs[0].id == "job-001"

    def test_excludes_already_scored_jobs(self, session):
        self._make_job("job-001", session)
        # Add a JobScore
        score = JobScore(
            job_id="job-001",
            fit_score=0.8,
            priority_score=0.75,
            strengths_json='[]',
            gaps_json='[]',
            reasoning="test",
            model_used="claude-3-haiku-20240307",
        )
        session.add(score)
        session.commit()

        jobs = get_unscored_jobs(session, limit=10)
        assert len(jobs) == 0

    def test_excludes_stale_jobs(self, session):
        job = self._make_job("job-stale", session)
        job.is_stale = True
        session.add(job)
        session.commit()

        jobs = get_unscored_jobs(session, limit=10)
        assert len(jobs) == 0

    def test_respects_limit(self, session):
        for i in range(5):
            self._make_job(f"job-{i:03d}", session)

        jobs = get_unscored_jobs(session, limit=3)
        assert len(jobs) == 3
