"""Tests for the CLI `score` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from jobinator.cli import app
from jobinator.pipelines.score import ScoringResult

SAMPLE_RESUME_PATH = Path(__file__).parent / "fixtures" / "sample_resume.json"


runner = CliRunner(mix_stderr=False)


# ---------------------------------------------------------------------------
# Helper mocks
# ---------------------------------------------------------------------------


def make_mock_settings(
    anthropic_key: str = "",
    openai_key: str = "",
    daily_budget: float = 5.00,
    per_job_budget: float = 0.50,
    warn_threshold: float = 0.80,
):
    """Create a mock Settings object."""
    s = MagicMock()
    s.anthropic_api_key = anthropic_key
    s.openai_api_key = openai_key
    s.daily_budget_usd = daily_budget
    s.per_job_budget_usd = per_job_budget
    s.budget_warn_threshold = warn_threshold
    s.database_url = "sqlite:///:memory:"
    s.config_dir = "/tmp/jobinator-test"
    return s


def make_mock_scoring_config(profile_path: str | None = str(SAMPLE_RESUME_PATH)):
    """Create a ScoringConfig object."""
    from jobinator.configs.settings import ScoringConfig
    return ScoringConfig(
        cheap_model="claude-3-haiku-20240307",
        score_batch_size=10,
        profile_path=profile_path,
    )


# ---------------------------------------------------------------------------
# Test: score command exists
# ---------------------------------------------------------------------------


class TestScoreCommandExists:
    def test_score_command_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "score" in result.output

    def test_score_help_shows_limit_option(self):
        result = runner.invoke(app, ["score", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output

    def test_score_help_shows_dry_run_option(self):
        result = runner.invoke(app, ["score", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output


# ---------------------------------------------------------------------------
# Test: no API key error
# ---------------------------------------------------------------------------


class TestScoreNoApiKey:
    def test_score_no_api_key_prints_error(self):
        """When no API key is set, score should exit 1 with an API key error message."""
        mock_settings = make_mock_settings(anthropic_key="", openai_key="")
        mock_config = make_mock_scoring_config()

        with (
            patch("jobinator.configs.settings.get_settings", return_value=mock_settings),
            patch("jobinator.configs.settings.get_scoring_config", return_value=mock_config),
            # Patch where they're looked up inside the lazy import context
            patch("jobinator.cli.score.__wrapped__", create=True),
        ):
            # We need to patch the modules that get imported lazily inside the function.
            # The function imports from jobinator.configs.settings, so we patch there.
            with (
                patch("jobinator.configs.settings.get_settings", return_value=mock_settings),
            ):
                # Actually we need a different approach since imports are lazy inside function.
                # Patch at the module level where the lazy import resolves.
                pass

        # Use a simpler approach: patch the modules directly
        with (
            patch(
                "jobinator.configs.settings.get_settings",
                return_value=mock_settings,
            ),
        ):
            # The lazy import inside score() calls get_settings() from
            # jobinator.configs.settings — we need to inject our mock there.
            # Since the import is: from jobinator.configs.settings import get_settings
            # We patch the module attribute that will be imported.
            import jobinator.configs.settings as settings_module
            original = settings_module.get_settings
            settings_module.get_settings = lambda: mock_settings

            import jobinator.configs.settings as settings_module2
            orig_scoring = settings_module2.get_scoring_config
            settings_module2.get_scoring_config = lambda *a, **kw: mock_config

            try:
                result = runner.invoke(app, ["score"])
            finally:
                settings_module.get_settings = original
                settings_module2.get_scoring_config = orig_scoring

        assert result.exit_code == 1
        combined_output = result.output + (result.stderr or "")
        assert (
            "api key" in combined_output.lower()
            or "ANTHROPIC_API_KEY" in combined_output
            or "OPENAI_API_KEY" in combined_output
        )

    def test_score_with_anthropic_key_passes_key_check(self):
        """When ANTHROPIC_API_KEY is set, score should not print API key error."""
        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config(profile_path=None)

        import jobinator.configs.settings as settings_module
        original = settings_module.get_settings
        orig_scoring = settings_module.get_scoring_config

        settings_module.get_settings = lambda: mock_settings
        settings_module.get_scoring_config = lambda *a, **kw: mock_config

        with (
            patch("jobinator.db.get_engine"),
            patch("jobinator.db.init_db"),
            patch("jobinator.db.get_session") as mock_session_ctx,
        ):
            mock_session = MagicMock()
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
            try:
                result = runner.invoke(app, ["score"])
            finally:
                settings_module.get_settings = original
                settings_module.get_scoring_config = orig_scoring

        combined = result.output + (result.stderr or "")
        # Should fail on profile, not API key — no API key message
        assert "ANTHROPIC_API_KEY" not in combined or "profile" in combined.lower()


# ---------------------------------------------------------------------------
# Test: no profile configured error
# ---------------------------------------------------------------------------


class TestScoreNoProfile:
    def _run_score_with_settings(
        self,
        mock_settings,
        mock_config,
        extra_patches: dict | None = None,
    ):
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module

        original_settings = settings_module.get_settings
        orig_scoring = settings_module.get_scoring_config

        settings_module.get_settings = lambda: mock_settings
        settings_module.get_scoring_config = lambda *a, **kw: mock_config

        original_engine = db_module.get_engine
        original_init = db_module.init_db
        original_session = db_module.get_session

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        db_module.get_engine = lambda *a, **kw: mock_engine
        db_module.init_db = lambda *a, **kw: None
        db_module.get_session = lambda *a, **kw: mock_session_ctx

        try:
            result = runner.invoke(app, ["score"])
        finally:
            settings_module.get_settings = original_settings
            settings_module.get_scoring_config = orig_scoring
            db_module.get_engine = original_engine
            db_module.init_db = original_init
            db_module.get_session = original_session

        return result

    def test_score_no_profile_prints_error(self):
        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config(profile_path=None)
        result = self._run_score_with_settings(mock_settings, mock_config)
        assert result.exit_code == 1
        assert "profile" in result.output.lower()

    def test_score_nonexistent_profile_prints_error(self):
        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config(
            profile_path="/nonexistent/path/to/resume.json"
        )
        result = self._run_score_with_settings(mock_settings, mock_config)
        assert result.exit_code == 1
        assert "profile" in result.output.lower()


# ---------------------------------------------------------------------------
# Test: successful run
# ---------------------------------------------------------------------------


class TestScoreSuccess:
    def _run_with_full_mock(self, scoring_result: ScoringResult, limit: int = 10):
        """Run score command with all dependencies mocked."""
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module
        import jobinator.budget.tracker as tracker_module
        import jobinator.scoring.client as client_module
        import jobinator.scoring.scorer as scorer_module
        import jobinator.pipelines.score as pipeline_module

        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config()

        original_settings = settings_module.get_settings
        orig_scoring_cfg = settings_module.get_scoring_config
        original_engine = db_module.get_engine
        original_init = db_module.init_db
        original_session = db_module.get_session
        original_run_scoring = pipeline_module.run_scoring

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        mock_tracker = MagicMock()
        mock_tracker.daily_spend.return_value = 0.005
        original_budget_tracker = tracker_module.BudgetTracker
        tracker_module.BudgetTracker = MagicMock(return_value=mock_tracker)

        original_llm_client = client_module.LLMClient
        client_module.LLMClient = MagicMock()

        original_job_scorer = scorer_module.JobScorer
        scorer_module.JobScorer = MagicMock()

        settings_module.get_settings = lambda: mock_settings
        settings_module.get_scoring_config = lambda *a, **kw: mock_config
        db_module.get_engine = lambda *a, **kw: mock_engine
        db_module.init_db = lambda *a, **kw: None
        db_module.get_session = lambda *a, **kw: mock_session_ctx
        pipeline_module.run_scoring = lambda *a, **kw: scoring_result

        try:
            result = runner.invoke(app, ["score", "--limit", str(limit)])
        finally:
            settings_module.get_settings = original_settings
            settings_module.get_scoring_config = orig_scoring_cfg
            db_module.get_engine = original_engine
            db_module.init_db = original_init
            db_module.get_session = original_session
            tracker_module.BudgetTracker = original_budget_tracker
            client_module.LLMClient = original_llm_client
            scorer_module.JobScorer = original_job_scorer
            pipeline_module.run_scoring = original_run_scoring

        return result

    def test_score_success_exits_0(self):
        scoring_result = ScoringResult(scored=3, skipped=0, budget_stopped=False)
        result = self._run_with_full_mock(scoring_result)
        assert result.exit_code == 0

    def test_score_success_prints_scored_count(self):
        scoring_result = ScoringResult(scored=3, skipped=0, budget_stopped=False)
        result = self._run_with_full_mock(scoring_result)
        assert "3" in result.output

    def test_score_limit_passed_to_config(self):
        """--limit 5 should update score_batch_size to 5."""
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module
        import jobinator.budget.tracker as tracker_module
        import jobinator.scoring.client as client_module
        import jobinator.scoring.scorer as scorer_module
        import jobinator.pipelines.score as pipeline_module

        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config()
        captured = {}

        def capture_run_scoring(session, budget_tracker, scorer, config):
            captured["batch_size"] = config.score_batch_size
            return ScoringResult(scored=0)

        original_settings = settings_module.get_settings
        orig_scoring_cfg = settings_module.get_scoring_config
        original_engine = db_module.get_engine
        original_init = db_module.init_db
        original_session = db_module.get_session
        original_run_scoring = pipeline_module.run_scoring

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        mock_tracker = MagicMock()
        mock_tracker.daily_spend.return_value = 0.0
        original_budget_tracker = tracker_module.BudgetTracker
        tracker_module.BudgetTracker = MagicMock(return_value=mock_tracker)
        original_llm_client = client_module.LLMClient
        client_module.LLMClient = MagicMock()
        original_job_scorer = scorer_module.JobScorer
        scorer_module.JobScorer = MagicMock()

        settings_module.get_settings = lambda: mock_settings
        settings_module.get_scoring_config = lambda *a, **kw: mock_config
        db_module.get_engine = lambda *a, **kw: mock_engine
        db_module.init_db = lambda *a, **kw: None
        db_module.get_session = lambda *a, **kw: mock_session_ctx
        pipeline_module.run_scoring = capture_run_scoring

        try:
            runner.invoke(app, ["score", "--limit", "5"])
        finally:
            settings_module.get_settings = original_settings
            settings_module.get_scoring_config = orig_scoring_cfg
            db_module.get_engine = original_engine
            db_module.init_db = original_init
            db_module.get_session = original_session
            tracker_module.BudgetTracker = original_budget_tracker
            client_module.LLMClient = original_llm_client
            scorer_module.JobScorer = original_job_scorer
            pipeline_module.run_scoring = original_run_scoring

        assert captured.get("batch_size") == 5


# ---------------------------------------------------------------------------
# Test: budget exceeded
# ---------------------------------------------------------------------------


class TestScoreBudgetExceeded:
    def _run_budget_exceeded(self):
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module
        import jobinator.budget.tracker as tracker_module
        import jobinator.scoring.client as client_module
        import jobinator.scoring.scorer as scorer_module
        import jobinator.pipelines.score as pipeline_module

        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config()

        original_settings = settings_module.get_settings
        orig_scoring_cfg = settings_module.get_scoring_config
        original_engine = db_module.get_engine
        original_init = db_module.init_db
        original_session = db_module.get_session
        original_run_scoring = pipeline_module.run_scoring

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        mock_tracker = MagicMock()
        mock_tracker.daily_spend.return_value = 5.0
        original_budget_tracker = tracker_module.BudgetTracker
        tracker_module.BudgetTracker = MagicMock(return_value=mock_tracker)
        original_llm_client = client_module.LLMClient
        client_module.LLMClient = MagicMock()
        original_job_scorer = scorer_module.JobScorer
        scorer_module.JobScorer = MagicMock()

        settings_module.get_settings = lambda: mock_settings
        settings_module.get_scoring_config = lambda *a, **kw: mock_config
        db_module.get_engine = lambda *a, **kw: mock_engine
        db_module.init_db = lambda *a, **kw: None
        db_module.get_session = lambda *a, **kw: mock_session_ctx
        pipeline_module.run_scoring = lambda *a, **kw: ScoringResult(scored=1, budget_stopped=True)

        try:
            result = runner.invoke(app, ["score"])
        finally:
            settings_module.get_settings = original_settings
            settings_module.get_scoring_config = orig_scoring_cfg
            db_module.get_engine = original_engine
            db_module.init_db = original_init
            db_module.get_session = original_session
            tracker_module.BudgetTracker = original_budget_tracker
            client_module.LLMClient = original_llm_client
            scorer_module.JobScorer = original_job_scorer
            pipeline_module.run_scoring = original_run_scoring

        return result, mock_tracker

    def test_budget_exceeded_exits_1(self):
        result, _ = self._run_budget_exceeded()
        assert result.exit_code == 1

    def test_budget_exceeded_prints_warning(self):
        result, _ = self._run_budget_exceeded()
        output = result.output.lower()
        assert "budget" in output


# ---------------------------------------------------------------------------
# Test: dry-run
# ---------------------------------------------------------------------------


class TestScoreDryRun:
    def _run_dry_run(self, jobs=None):
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module
        import jobinator.pipelines.score as pipeline_module

        if jobs is None:
            jobs = []

        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_scoring_config()

        original_settings = settings_module.get_settings
        orig_scoring_cfg = settings_module.get_scoring_config
        original_engine = db_module.get_engine
        original_init = db_module.init_db
        original_session = db_module.get_session
        original_get_unscored = pipeline_module.get_unscored_jobs
        original_run_scoring = pipeline_module.run_scoring

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        settings_module.get_settings = lambda: mock_settings
        settings_module.get_scoring_config = lambda *a, **kw: mock_config
        db_module.get_engine = lambda *a, **kw: mock_engine
        db_module.init_db = lambda *a, **kw: None
        db_module.get_session = lambda *a, **kw: mock_session_ctx
        pipeline_module.get_unscored_jobs = lambda *a, **kw: jobs
        run_scoring_called = []
        pipeline_module.run_scoring = lambda *a, **kw: run_scoring_called.append(True) or ScoringResult()

        try:
            result = runner.invoke(app, ["score", "--dry-run"])
        finally:
            settings_module.get_settings = original_settings
            settings_module.get_scoring_config = orig_scoring_cfg
            db_module.get_engine = original_engine
            db_module.init_db = original_init
            db_module.get_session = original_session
            pipeline_module.get_unscored_jobs = original_get_unscored
            pipeline_module.run_scoring = original_run_scoring

        return result, run_scoring_called

    def test_dry_run_exits_0_with_no_jobs(self):
        result, _ = self._run_dry_run(jobs=[])
        assert result.exit_code == 0

    def test_dry_run_does_not_call_run_scoring(self):
        """dry-run should display jobs without calling run_scoring."""
        from datetime import datetime
        from jobinator.models.job import NormalizedJob

        fake_job = NormalizedJob(
            id="job-dry-001",
            source="greenhouse",
            source_url="https://example.com/1",
            title="ML Engineer",
            title_normalized="ml engineer",
            company="TestCorp",
            company_slug="testcorp",
            description="Job description.",
            description_hash="abc123def456aabb",
            raw_json="{}",
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            is_stale=False,
        )

        result, run_scoring_called = self._run_dry_run(jobs=[fake_job])
        assert len(run_scoring_called) == 0
        assert result.exit_code == 0
