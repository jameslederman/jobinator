"""LLM client wrapper using Instructor + LiteLLM for structured scoring output."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import instructor
import litellm

from jobinator.models.score import JobScoreOutput

logger = logging.getLogger(__name__)

# Module-level Instructor-wrapped LiteLLM client.
# Using instructor.from_litellm() so we get create_with_completion() support
# to extract both the parsed Pydantic model and the raw ModelResponse for
# cost/token extraction. See instructor#1330: completion_cost() returns 0.0
# through the Instructor wrapper; use _hidden_params["response_cost"] instead.
_client = instructor.from_litellm(litellm.completion)


@dataclass
class LLMResult:
    """Result from an LLM scoring call."""

    score: JobScoreOutput
    cost_usd: float
    input_tokens: int
    output_tokens: int


class LLMClient:
    """Wraps Instructor + LiteLLM to produce structured JobScoreOutput.

    Usage:
        client = LLMClient(model="claude-3-haiku-20240307")
        result = client.score(messages)
        # result.score: JobScoreOutput
        # result.cost_usd: float
        # result.input_tokens: int
        # result.output_tokens: int
    """

    def __init__(self, model: str = "claude-3-haiku-20240307") -> None:
        self.model = model

    def score(self, messages: list[dict]) -> LLMResult:
        """Call LLM with structured output and extract cost.

        Uses create_with_completion() to get both the Pydantic model
        and the raw completion for cost extraction.

        IMPORTANT: Cost is extracted from raw._hidden_params["response_cost"],
        NOT from litellm.completion_cost() which returns 0.0 via Instructor
        wrapper (known bug, instructor#1330).

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            LLMResult with structured score output, cost, and token counts.
        """
        model = self.model
        if "/" not in model:
            if "claude" in model or "anthropic" in model:
                model = f"anthropic/{model}"
            elif "gpt" in model or "openai" in model:
                model = f"openai/{model}"
        score_output, raw = _client.create_with_completion(
            model=model,
            messages=messages,
            response_model=JobScoreOutput,
            max_tokens=512,
            max_retries=2,
        )

        cost = float(raw._hidden_params.get("response_cost", 0.0))
        input_tokens = raw.usage.prompt_tokens
        output_tokens = raw.usage.completion_tokens

        if cost == 0.0:
            logger.warning(
                "response_cost is 0.0 for model=%s — LiteLLM pricing table "
                "may not have this model. Cost will be recorded as $0.00.",
                self.model,
            )

        return LLMResult(
            score=score_output,
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
