"""JobScorer: orchestrates budget gating, LLM call, and spend recording."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from jobinator.models.budget import SpendRecord
from jobinator.models.job import NormalizedJob
from jobinator.models.score import JobScore
from jobinator.scoring.prompt import build_scoring_prompt

if TYPE_CHECKING:
    from jobinator.budget.tracker import BudgetTracker
    from jobinator.configs.settings import ScoringConfig
    from jobinator.scoring.client import LLMClient

logger = logging.getLogger(__name__)


def _provider_from_model(model: str) -> str:
    """Infer provider name from model string.

    Examples:
        'claude-3-haiku-20240307' -> 'anthropic'
        'gpt-4o-mini' -> 'openai'
        'gemini-pro' -> 'gemini'
    """
    if "claude" in model:
        return "anthropic"
    if "gpt" in model:
        return "openai"
    # Fallback: first token before '-'
    return model.split("-")[0]


class JobScorer:
    """Orchestrates a single job scoring call.

    Lifecycle per job:
      1. assert_within_limits() — budget gate BEFORE LLM call
      2. build_scoring_prompt() — format job + profile
      3. llm_client.score() — structured LLM call
      4. _compute_priority() — local recency/urgency weighting
      5. Build JobScore (not persisted here — caller commits)
      6. record() SpendRecord
      7. log_decision() for audit trail
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        budget_tracker: "BudgetTracker",
        config: "ScoringConfig",
    ) -> None:
        self.llm_client = llm_client
        self.budget_tracker = budget_tracker
        self.config = config

    def score_job(self, job: NormalizedJob, profile_data: dict) -> JobScore:
        """Score a single job against the candidate profile.

        Budget gate is checked BEFORE the LLM call. SpendRecord is persisted
        immediately after. Caller is responsible for session.commit() to
        persist the returned JobScore.

        Args:
            job: NormalizedJob to score.
            profile_data: JSON Resume dict for the candidate.

        Returns:
            JobScore instance (not yet committed to DB).

        Raises:
            BudgetExceeded: If daily or per-job budget is exhausted.
        """
        # 1. Budget gate BEFORE LLM call
        self.budget_tracker.assert_within_limits(job_id=job.id)

        # 2. Build prompt
        messages = build_scoring_prompt(job, profile_data)

        # 3. Call LLM
        result = self.llm_client.score(messages)

        # 4. Compute priority locally (overrides LLM-provided value)
        priority = self._compute_priority(result.score.fit_score, job)

        # 5. Build JobScore
        job_score = JobScore(
            job_id=job.id,
            fit_score=result.score.fit_score,
            priority_score=priority,
            strengths_json=json.dumps(result.score.strengths_match),
            gaps_json=json.dumps(result.score.gaps),
            compensation_estimate=result.score.compensation_estimate,
            reasoning=result.score.reasoning,
            model_used=self.config.cheap_model,
        )

        # 6. Record spend
        spend = SpendRecord(
            job_id=job.id,
            model_name=self.config.cheap_model,
            provider=_provider_from_model(self.config.cheap_model),
            operation="score",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        )
        self.budget_tracker.record(spend)

        # 7. Log decision for audit trail
        self.budget_tracker.log_decision(
            decision_type="score",
            decision="scored",
            reason=(
                f"fit_score={result.score.fit_score:.2f}, "
                f"priority={priority:.2f}, "
                f"cost=${result.cost_usd:.5f}"
            ),
            job_id=job.id,
            context={"model": self.config.cheap_model, "tokens": result.input_tokens + result.output_tokens},
        )

        return job_score

    def _compute_priority(self, fit_score: float, job: NormalizedJob) -> float:
        """Compute priority score from fit, recency, and urgency.

        Args:
            fit_score: LLM-assigned fit score (0.0-1.0).
            job: NormalizedJob for date-based recency/urgency computation.

        Returns:
            Weighted priority score in range [0.0, 1.0].
        """
        weights = self.config.priority_weights
        recency = self._recency_score(job)
        urgency = self._urgency_score(job)
        raw = (
            weights.get("fit", 0.6) * fit_score
            + weights.get("recency", 0.2) * recency
            + weights.get("urgency", 0.2) * urgency
        )
        return max(0.0, min(1.0, raw))

    def _recency_score(self, job: NormalizedJob) -> float:
        """Recency score: 1.0 for jobs posted today, decays to 0.0 over 30 days.

        Returns 0.5 for jobs with unknown posting date.
        """
        if not job.posted_at:
            return 0.5  # unknown = neutral
        days_old = (datetime.utcnow() - job.posted_at).days
        return max(0.0, 1.0 - (days_old / 30.0))

    def _urgency_score(self, job: NormalizedJob) -> float:
        """Urgency score: higher for jobs seen recently for the first time.

        Based on first_seen_at: 1.0 if seen today, decays to 0.0 over 14 days.
        """
        days_since_first_seen = (datetime.utcnow() - job.first_seen_at).days
        return max(0.0, 1.0 - (days_since_first_seen / 14.0))
