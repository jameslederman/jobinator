"""Tests for the CLI `apply` command.

Follows the module-level monkey-patching pattern from test_score_cli.py
because lazy imports inside the CLI function body prevent standard
unittest.mock.patch() from working at the jobinator.cli module level.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from jobinator.cli import app
from jobinator.configs.settings import MaterialsConfig
from jobinator.models.job import NormalizedJob
from jobinator.models.score import JobScore
from jobinator.pipelines.apply import ApplyResult

SAMPLE_RESUME_PATH = Path(__file__).parent / "fixtures" / "sample_resume.json"

runner = CliRunner(mix_stderr=False)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_settings(
    anthropic_key: str = "",
    openai_key: str = "",
    daily_budget: float = 5.00,
    per_job_budget: float = 0.50,
    warn_threshold: float = 0.80,
):
    s = MagicMock()
    s.anthropic_api_key = anthropic_key
    s.openai_api_key = openai_key
    s.daily_budget_usd = daily_budget
    s.per_job_budget_usd = per_job_budget
    s.budget_warn_threshold = warn_threshold
    s.database_url = "sqlite:///:memory:"
    s.config_dir = "/tmp/jobinator-test"
    return s


def make_mock_materials_config(
    profile_path: str | None = str(SAMPLE_RESUME_PATH),
    apply_threshold: float = 0.6,
) -> MaterialsConfig:
    return MaterialsConfig(
        strong_model="claude-3-5-sonnet-latest",
        apply_threshold=apply_threshold,
        profile_path=profile_path,
        output_dir="/tmp/jobinator-test-output",
        max_retries=1,
    )


def make_fake_job() -> NormalizedJob:
    return NormalizedJob(
        id="job-cli-001",
        source="greenhouse",
        source_url="https://example.com/job-001",
        title="Senior ML Engineer",
        title_normalized="senior ml engineer",
        company="AcmeCorp",
        company_slug="acmecorp",
        description="Great ML job.",
        description_hash=NormalizedJob.make_description_hash("Great ML job."),
        raw_json="{}",
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        is_stale=False,
    )


def make_fake_score(job_id: str, fit_score: float = 0.85) -> JobScore:
    return JobScore(
        job_id=job_id,
        fit_score=fit_score,
        priority_score=0.80,
        strengths_json=json.dumps(["Python", "ML systems"]),
        gaps_json=json.dumps(["Kubernetes"]),
        reasoning="Strong ML fit.",
        model_used="claude-3-haiku-20240307",
    )


def _run_apply_with_mocks(
    job_id: str = "job-cli-001",
    mock_settings=None,
    mock_materials_config=None,
    mock_scoring_config=None,
    fake_job_and_score=None,
    apply_result: ApplyResult | None = None,
    extra_args: list[str] | None = None,
):
    """Helper: run `jobinator apply <job_id>` with all lazy-import modules mocked."""
    import jobinator.budget.tracker as tracker_module
    import jobinator.configs.settings as settings_module
    import jobinator.db as db_module
    import jobinator.generation.generator as gen_module
    import jobinator.pipelines.apply as apply_module
    import jobinator.pipelines.score as score_module

    if mock_settings is None:
        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
    if mock_materials_config is None:
        mock_materials_config = make_mock_materials_config()
    if mock_scoring_config is None:
        from jobinator.configs.settings import ScoringConfig

        mock_scoring_config = ScoringConfig(profile_path=str(SAMPLE_RESUME_PATH))
    if apply_result is None:
        apply_result = ApplyResult(
            success=True,
            confirmed=True,
            bundle_path="/tmp/jobinator-test-output/acmecorp/senior-ml-engineer/20260101T120000Z",
            total_cost_usd=0.03,
        )

    # DB mocks
    mock_engine = MagicMock()
    mock_session = MagicMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
    mock_session_ctx.__exit__ = MagicMock(return_value=False)

    # Setup originals for cleanup
    orig_settings = settings_module.get_settings
    orig_materials = settings_module.get_materials_config
    orig_scoring = settings_module.get_scoring_config
    orig_engine = db_module.get_engine
    orig_init = db_module.init_db
    orig_session = db_module.get_session
    orig_budget_tracker = tracker_module.BudgetTracker
    orig_materials_generator = gen_module.MaterialsGenerator
    orig_get_job = apply_module.get_job_with_score
    orig_run_apply = apply_module.run_apply
    orig_load_profile = score_module.load_profile

    mock_tracker = MagicMock()
    mock_tracker.daily_spend.return_value = 0.0

    # If fake_job_and_score provided, use it; otherwise return (None, None) to simulate not-found
    if fake_job_and_score is not None:
        job, score = fake_job_and_score
    else:
        job, score = (None, None)

    settings_module.get_settings = lambda: mock_settings  # type: ignore[assignment]
    settings_module.get_materials_config = lambda *a, **kw: mock_materials_config  # type: ignore[assignment]
    settings_module.get_scoring_config = lambda *a, **kw: mock_scoring_config  # type: ignore[assignment]
    db_module.get_engine = lambda *a, **kw: mock_engine  # type: ignore[assignment]
    db_module.init_db = lambda *a, **kw: None  # type: ignore[assignment]
    db_module.get_session = lambda *a, **kw: mock_session_ctx  # type: ignore[assignment]
    tracker_module.BudgetTracker = MagicMock(return_value=mock_tracker)  # type: ignore[misc]
    gen_module.MaterialsGenerator = MagicMock()  # type: ignore[misc]
    apply_module.get_job_with_score = lambda session, jid: (job, score)  # type: ignore[assignment]
    apply_module.run_apply = lambda **kw: apply_result  # type: ignore[assignment]
    score_module.load_profile = lambda path: {"basics": {"name": "Test User"}} if path else None  # type: ignore[assignment]

    args = ["apply", job_id]
    if extra_args:
        args.extend(extra_args)

    try:
        result = runner.invoke(app, args)
    finally:
        settings_module.get_settings = orig_settings  # type: ignore[assignment]
        settings_module.get_materials_config = orig_materials  # type: ignore[assignment]
        settings_module.get_scoring_config = orig_scoring  # type: ignore[assignment]
        db_module.get_engine = orig_engine  # type: ignore[assignment]
        db_module.init_db = orig_init  # type: ignore[assignment]
        db_module.get_session = orig_session  # type: ignore[assignment]
        tracker_module.BudgetTracker = orig_budget_tracker  # type: ignore[misc]
        gen_module.MaterialsGenerator = orig_materials_generator  # type: ignore[misc]
        apply_module.get_job_with_score = orig_get_job  # type: ignore[assignment]
        apply_module.run_apply = orig_run_apply  # type: ignore[assignment]
        score_module.load_profile = orig_load_profile  # type: ignore[assignment]

    return result


# ---------------------------------------------------------------------------
# Test: apply command exists
# ---------------------------------------------------------------------------


class TestApplyCommandExists:
    def test_apply_command_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "apply" in result.output

    def test_apply_help_shows_job_id(self):
        result = runner.invoke(app, ["apply", "--help"])
        assert result.exit_code == 0
        assert "job" in result.output.lower() or "JOB_ID" in result.output

    def test_apply_help_shows_force_flag(self):
        result = runner.invoke(app, ["apply", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output


# ---------------------------------------------------------------------------
# Test: no API key error
# ---------------------------------------------------------------------------


class TestApplyNoApiKey:
    def test_apply_no_api_key_exits_1(self):
        """When no API key is set, apply should exit 1 with API key error."""
        import jobinator.configs.settings as settings_module

        mock_settings = make_mock_settings(anthropic_key="", openai_key="")
        mock_config = make_mock_materials_config()

        orig_settings = settings_module.get_settings
        orig_materials = settings_module.get_materials_config

        settings_module.get_settings = lambda: mock_settings  # type: ignore[assignment]
        settings_module.get_materials_config = lambda *a, **kw: mock_config  # type: ignore[assignment]

        try:
            result = runner.invoke(app, ["apply", "job-001"])
        finally:
            settings_module.get_settings = orig_settings  # type: ignore[assignment]
            settings_module.get_materials_config = orig_materials  # type: ignore[assignment]

        assert result.exit_code == 1
        combined = result.output + (result.stderr or "")
        assert (
            "api key" in combined.lower()
            or "ANTHROPIC_API_KEY" in combined
            or "OPENAI_API_KEY" in combined
        )


# ---------------------------------------------------------------------------
# Test: job not found
# ---------------------------------------------------------------------------


class TestApplyJobNotFound:
    def test_apply_job_not_found(self):
        """Non-existent job_id should exit 1 with 'Job not found'."""
        result = _run_apply_with_mocks(
            job_id="nonexistent-job-id",
            mock_settings=make_mock_settings(anthropic_key="sk-ant-test123"),
            fake_job_and_score=None,  # returns (None, None) -> job not found
        )
        assert result.exit_code == 1
        combined = result.output + (result.stderr or "")
        assert "not found" in combined.lower() or "job not found" in combined.lower()


# ---------------------------------------------------------------------------
# Test: no profile configured
# ---------------------------------------------------------------------------


class TestApplyNoProfile:
    def test_apply_no_profile_exits_1(self):
        """When profile_path is None (or missing file), apply should exit 1."""
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module
        import jobinator.pipelines.apply as apply_module
        import jobinator.pipelines.score as score_module

        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        mock_config = make_mock_materials_config(profile_path=None)
        from jobinator.configs.settings import ScoringConfig

        mock_scoring_config = ScoringConfig(profile_path=None)

        fake_job = make_fake_job()
        fake_score = make_fake_score(fake_job.id)

        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)

        orig_settings = settings_module.get_settings
        orig_materials = settings_module.get_materials_config
        orig_scoring = settings_module.get_scoring_config
        orig_engine = db_module.get_engine
        orig_init = db_module.init_db
        orig_session = db_module.get_session
        orig_get_job = apply_module.get_job_with_score
        orig_load_profile = score_module.load_profile

        settings_module.get_settings = lambda: mock_settings  # type: ignore[assignment]
        settings_module.get_materials_config = lambda *a, **kw: mock_config  # type: ignore[assignment]
        settings_module.get_scoring_config = lambda *a, **kw: mock_scoring_config  # type: ignore[assignment]
        db_module.get_engine = lambda *a, **kw: mock_engine  # type: ignore[assignment]
        db_module.init_db = lambda *a, **kw: None  # type: ignore[assignment]
        db_module.get_session = lambda *a, **kw: mock_session_ctx  # type: ignore[assignment]
        apply_module.get_job_with_score = lambda session, jid: (fake_job, fake_score)  # type: ignore[assignment]
        score_module.load_profile = lambda path: None  # type: ignore[assignment]  # no profile

        try:
            result = runner.invoke(app, ["apply", fake_job.id])
        finally:
            settings_module.get_settings = orig_settings  # type: ignore[assignment]
            settings_module.get_materials_config = orig_materials  # type: ignore[assignment]
            settings_module.get_scoring_config = orig_scoring  # type: ignore[assignment]
            db_module.get_engine = orig_engine  # type: ignore[assignment]
            db_module.init_db = orig_init  # type: ignore[assignment]
            db_module.get_session = orig_session  # type: ignore[assignment]
            apply_module.get_job_with_score = orig_get_job  # type: ignore[assignment]
            score_module.load_profile = orig_load_profile  # type: ignore[assignment]

        assert result.exit_code == 1
        assert "profile" in result.output.lower()


# ---------------------------------------------------------------------------
# Test: below threshold
# ---------------------------------------------------------------------------


class TestApplyBelowThreshold:
    def test_apply_below_threshold_exits_1(self):
        """Job score below threshold should exit 1 with threshold message."""
        fake_job = make_fake_job()
        fake_score = make_fake_score(fake_job.id, fit_score=0.3)
        apply_result = ApplyResult(
            success=False,
            errors=["Job fit_score 0.30 is below apply_threshold 0.60. Use --force to override."],
        )
        result = _run_apply_with_mocks(
            job_id=fake_job.id,
            mock_settings=make_mock_settings(anthropic_key="sk-ant-test123"),
            fake_job_and_score=(fake_job, fake_score),
            apply_result=apply_result,
        )
        assert result.exit_code == 1
        assert "threshold" in result.output.lower() or "apply_threshold" in result.output


# ---------------------------------------------------------------------------
# Test: --force overrides threshold
# ---------------------------------------------------------------------------


class TestApplyForceOverridesThreshold:
    def test_apply_force_overrides_threshold(self):
        """--force flag should bypass the threshold check."""
        import jobinator.budget.tracker as tracker_module
        import jobinator.configs.settings as settings_module
        import jobinator.db as db_module
        import jobinator.generation.generator as gen_module
        import jobinator.pipelines.apply as apply_module
        import jobinator.pipelines.score as score_module

        fake_job = make_fake_job()
        fake_score = make_fake_score(fake_job.id, fit_score=0.3)
        # config with threshold 0.6 — score is 0.3, normally below threshold
        mock_config = make_mock_materials_config(apply_threshold=0.6)

        captured_config = {}

        def capture_run_apply(**kwargs):
            captured_config["apply_threshold"] = kwargs["config"].apply_threshold
            return ApplyResult(
                success=True, confirmed=True, bundle_path="/tmp/test", total_cost_usd=0.01
            )

        mock_settings = make_mock_settings(anthropic_key="sk-ant-test123")
        from jobinator.configs.settings import ScoringConfig

        mock_scoring_config = ScoringConfig(profile_path=str(SAMPLE_RESUME_PATH))

        mock_engine = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)
        mock_tracker = MagicMock()
        mock_tracker.daily_spend.return_value = 0.0

        orig_settings = settings_module.get_settings
        orig_materials = settings_module.get_materials_config
        orig_scoring = settings_module.get_scoring_config
        orig_engine = db_module.get_engine
        orig_init = db_module.init_db
        orig_session = db_module.get_session
        orig_budget_tracker = tracker_module.BudgetTracker
        orig_gen = gen_module.MaterialsGenerator
        orig_get_job = apply_module.get_job_with_score
        orig_run_apply = apply_module.run_apply
        orig_load_profile = score_module.load_profile

        settings_module.get_settings = lambda: mock_settings  # type: ignore[assignment]
        settings_module.get_materials_config = lambda *a, **kw: mock_config  # type: ignore[assignment]
        settings_module.get_scoring_config = lambda *a, **kw: mock_scoring_config  # type: ignore[assignment]
        db_module.get_engine = lambda *a, **kw: mock_engine  # type: ignore[assignment]
        db_module.init_db = lambda *a, **kw: None  # type: ignore[assignment]
        db_module.get_session = lambda *a, **kw: mock_session_ctx  # type: ignore[assignment]
        tracker_module.BudgetTracker = MagicMock(return_value=mock_tracker)  # type: ignore[misc]
        gen_module.MaterialsGenerator = MagicMock()  # type: ignore[misc]
        apply_module.get_job_with_score = lambda session, jid: (fake_job, fake_score)  # type: ignore[assignment]
        apply_module.run_apply = capture_run_apply  # type: ignore[assignment]
        score_module.load_profile = lambda path: {"basics": {"name": "Test User"}}  # type: ignore[assignment]

        try:
            runner.invoke(app, ["apply", fake_job.id, "--force"])
        finally:
            settings_module.get_settings = orig_settings  # type: ignore[assignment]
            settings_module.get_materials_config = orig_materials  # type: ignore[assignment]
            settings_module.get_scoring_config = orig_scoring  # type: ignore[assignment]
            db_module.get_engine = orig_engine  # type: ignore[assignment]
            db_module.init_db = orig_init  # type: ignore[assignment]
            db_module.get_session = orig_session  # type: ignore[assignment]
            tracker_module.BudgetTracker = orig_budget_tracker  # type: ignore[misc]
            gen_module.MaterialsGenerator = orig_gen  # type: ignore[misc]
            apply_module.get_job_with_score = orig_get_job  # type: ignore[assignment]
            apply_module.run_apply = orig_run_apply  # type: ignore[assignment]
            score_module.load_profile = orig_load_profile  # type: ignore[assignment]

        # With --force, apply_threshold should be set to 0.0
        assert captured_config.get("apply_threshold") == 0.0

    def test_apply_success_prints_bundle_path(self):
        """Successful apply should print the bundle path."""
        fake_job = make_fake_job()
        fake_score = make_fake_score(fake_job.id)
        bundle_path = "/tmp/jobinator-output/acmecorp/senior-ml-engineer/20260101T120000Z"
        apply_result = ApplyResult(
            success=True,
            confirmed=True,
            bundle_path=bundle_path,
            total_cost_usd=0.03,
        )
        result = _run_apply_with_mocks(
            job_id=fake_job.id,
            mock_settings=make_mock_settings(anthropic_key="sk-ant-test123"),
            fake_job_and_score=(fake_job, fake_score),
            apply_result=apply_result,
        )
        assert result.exit_code == 0
        assert bundle_path in result.output

    def test_apply_user_cancel_exits_0(self):
        """User cancelling (result.confirmed=False) should exit with code 0."""
        fake_job = make_fake_job()
        fake_score = make_fake_score(fake_job.id)
        apply_result = ApplyResult(
            success=False,
            confirmed=False,
            bundle_path=None,
        )
        result = _run_apply_with_mocks(
            job_id=fake_job.id,
            mock_settings=make_mock_settings(anthropic_key="sk-ant-test123"),
            fake_job_and_score=(fake_job, fake_score),
            apply_result=apply_result,
        )
        assert result.exit_code == 0
        assert "cancel" in result.output.lower()
