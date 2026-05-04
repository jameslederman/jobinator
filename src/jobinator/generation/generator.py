"""MaterialsGenerator: LLM-based generation of resume, cover letter, and prep brief.

Uses Instructor + LiteLLM for structured output, identical to the scoring pipeline.
Each generation method individually budget-gates before the LLM call and records
a SpendRecord immediately after.

Architecture follows scoring/scorer.py patterns:
  1. assert_within_limits() — budget gate BEFORE LLM call
  2. build_*_prompt() — format profile + job context
  3. _client.create_with_completion() — structured LLM call
  4. Extract cost from raw._hidden_params["response_cost"]
  5. Build and record SpendRecord
  6. Return (content, spend)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import instructor
import litellm

from jobinator.generation.models import CoverLetterContent, PrepBriefContent, ResumeContent
from jobinator.generation.prompts import (
    build_cover_letter_prompt,
    build_prep_brief_prompt,
    build_resume_prompt,
)
from jobinator.models.budget import SpendRecord
from jobinator.models.job import NormalizedJob
from jobinator.models.score import JobScore

if TYPE_CHECKING:
    from jobinator.budget.tracker import BudgetTracker
    from jobinator.configs.settings import MaterialsConfig

logger = logging.getLogger(__name__)

# Module-level Instructor-wrapped LiteLLM client (same pattern as scoring/client.py).
# Cost extracted from raw._hidden_params["response_cost"] — see instructor#1330.
_client = instructor.from_litellm(litellm.completion)


def _provider_from_model(model: str) -> str:
    """Infer provider name from model string.

    Examples:
        'claude-3-5-sonnet-latest' -> 'anthropic'
        'gpt-4o' -> 'openai'
    """
    if "claude" in model or "anthropic" in model:
        return "anthropic"
    if "gpt" in model or "openai" in model:
        return "openai"
    return "unknown"


def _ensure_provider_prefix(model: str) -> str:
    """Ensure model string has the LiteLLM provider prefix.

    LiteLLM requires 'anthropic/claude-...' or 'openai/gpt-...' format.
    If the user config omits the prefix, add it based on model name.
    """
    if "/" in model:
        return model
    provider = _provider_from_model(model)
    if provider != "unknown":
        return f"{provider}/{model}"
    return model


class MaterialsGenerator:
    """Orchestrates generation of resume, cover letter, and interview prep brief.

    Each generation method follows the same lifecycle:
      1. Budget gate BEFORE LLM call (raises BudgetExceeded if over limit)
      2. Build structured prompt from profile + job context
      3. Call LLM via Instructor for structured output
      4. Extract cost from raw response
      5. Create and record SpendRecord
      6. Return (content, spend)
    """

    def __init__(self, budget_tracker: "BudgetTracker", config: "MaterialsConfig") -> None:
        self.budget_tracker = budget_tracker
        self.config = config

    def generate_resume(
        self,
        job: NormalizedJob,
        profile_data: dict,
        score: JobScore | None = None,
    ) -> tuple[ResumeContent, SpendRecord]:
        """Generate a tailored resume for a job posting.

        Args:
            job: NormalizedJob to tailor the resume for.
            profile_data: JSON Resume dict (the complete candidate profile).
            score: Optional JobScore to emphasize strengths and address gaps.

        Returns:
            Tuple of (ResumeContent, SpendRecord).

        Raises:
            BudgetExceeded: If daily or per-job budget is exhausted.
        """
        # 1. Budget gate BEFORE LLM call
        self.budget_tracker.assert_within_limits(job_id=job.id)

        # 2. Build prompt
        messages = build_resume_prompt(profile_data, job, score)

        # 3. Call LLM via Instructor
        content, raw = _client.create_with_completion(
            model=_ensure_provider_prefix(self.config.strong_model),
            messages=messages,
            response_model=ResumeContent,
            max_tokens=2048,
            max_retries=self.config.max_retries,
        )

        # 4. Extract cost
        cost = float(raw._hidden_params.get("response_cost", 0.0))
        if cost == 0.0:
            logger.warning(
                "response_cost is 0.0 for model=%s — pricing table may not have this model.",
                self.config.strong_model,
            )

        # 5. Build SpendRecord
        spend = SpendRecord(
            job_id=job.id,
            model_name=self.config.strong_model,
            provider=_provider_from_model(self.config.strong_model),
            operation="generate_resume",
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
            cost_usd=cost,
        )

        # 6. Record spend
        self.budget_tracker.record(spend)

        return (content, spend)

    def generate_cover_letter(
        self,
        job: NormalizedJob,
        profile_data: dict,
        score: JobScore | None = None,
    ) -> tuple[CoverLetterContent, SpendRecord]:
        """Generate a tailored cover letter for a job posting.

        Args:
            job: NormalizedJob to tailor the cover letter for.
            profile_data: JSON Resume dict (the complete candidate profile).
            score: Optional JobScore to highlight strengths and address gaps.

        Returns:
            Tuple of (CoverLetterContent, SpendRecord).

        Raises:
            BudgetExceeded: If daily or per-job budget is exhausted.
        """
        # 1. Budget gate BEFORE LLM call
        self.budget_tracker.assert_within_limits(job_id=job.id)

        # 2. Build prompt
        messages = build_cover_letter_prompt(profile_data, job, score)

        # 3. Call LLM via Instructor
        content, raw = _client.create_with_completion(
            model=_ensure_provider_prefix(self.config.strong_model),
            messages=messages,
            response_model=CoverLetterContent,
            max_tokens=1024,
            max_retries=self.config.max_retries,
        )

        # 4. Extract cost
        cost = float(raw._hidden_params.get("response_cost", 0.0))
        if cost == 0.0:
            logger.warning(
                "response_cost is 0.0 for model=%s — pricing table may not have this model.",
                self.config.strong_model,
            )

        # 5. Build SpendRecord
        spend = SpendRecord(
            job_id=job.id,
            model_name=self.config.strong_model,
            provider=_provider_from_model(self.config.strong_model),
            operation="generate_cover_letter",
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
            cost_usd=cost,
        )

        # 6. Record spend
        self.budget_tracker.record(spend)

        return (content, spend)

    def generate_prep_brief(
        self,
        job: NormalizedJob,
        profile_data: dict,
        score: JobScore | None = None,
    ) -> tuple[PrepBriefContent, SpendRecord]:
        """Generate an interview prep brief for a job posting.

        Args:
            job: NormalizedJob to prepare for.
            profile_data: JSON Resume dict (the complete candidate profile).
            score: Optional JobScore for gap-based prep focus.

        Returns:
            Tuple of (PrepBriefContent, SpendRecord).

        Raises:
            BudgetExceeded: If daily or per-job budget is exhausted.
        """
        # 1. Budget gate BEFORE LLM call
        self.budget_tracker.assert_within_limits(job_id=job.id)

        # 2. Build prompt
        messages = build_prep_brief_prompt(profile_data, job, score)

        # 3. Call LLM via Instructor
        content, raw = _client.create_with_completion(
            model=_ensure_provider_prefix(self.config.strong_model),
            messages=messages,
            response_model=PrepBriefContent,
            max_tokens=1536,
            max_retries=self.config.max_retries,
        )

        # 4. Extract cost
        cost = float(raw._hidden_params.get("response_cost", 0.0))
        if cost == 0.0:
            logger.warning(
                "response_cost is 0.0 for model=%s — pricing table may not have this model.",
                self.config.strong_model,
            )

        # 5. Build SpendRecord
        spend = SpendRecord(
            job_id=job.id,
            model_name=self.config.strong_model,
            provider=_provider_from_model(self.config.strong_model),
            operation="generate_prep_brief",
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
            cost_usd=cost,
        )

        # 6. Record spend
        self.budget_tracker.record(spend)

        return (content, spend)
