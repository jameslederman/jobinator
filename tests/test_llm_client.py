"""Tests for LLMClient wrapper using Instructor + LiteLLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jobinator.models.score import JobScoreOutput
from jobinator.scoring import LLMClient, LLMResult


def make_mock_raw(
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    response_cost: float = 0.0015,
) -> MagicMock:
    """Create a mock raw LiteLLM ModelResponse with usage and hidden params."""
    mock_raw = MagicMock()
    mock_raw.usage.prompt_tokens = prompt_tokens
    mock_raw.usage.completion_tokens = completion_tokens
    mock_raw._hidden_params = {"response_cost": response_cost}
    return mock_raw


def make_sample_score_output() -> JobScoreOutput:
    """Return a sample JobScoreOutput for use in mocked calls."""
    return JobScoreOutput(
        fit_score=0.85,
        strengths_match=["Strong Python skills", "ML experience"],
        gaps=["No fintech background"],
        compensation_estimate="$180k-$220k",
        priority_score=0.75,
        reasoning="The candidate has strong ML skills highly relevant to this role.",
    )


class TestLLMClientScore:
    """Tests for LLMClient.score() return values and extraction logic."""

    def test_score_returns_llm_result_tuple(self):
        """LLMClient.score() returns an LLMResult with score, cost, and token counts."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw(prompt_tokens=100, completion_tokens=50, response_cost=0.0015)

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            result = client.score([{"role": "user", "content": "score this job"}])

        assert isinstance(result, LLMResult)
        assert isinstance(result.score, JobScoreOutput)
        assert result.score.fit_score == 0.85

    def test_score_extracts_cost_from_hidden_params(self):
        """cost_usd is extracted from raw._hidden_params['response_cost']."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw(response_cost=0.0015)

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            result = client.score([{"role": "user", "content": "score this"}])

        assert result.cost_usd == 0.0015

    def test_score_extracts_input_tokens(self):
        """input_tokens is extracted from raw.usage.prompt_tokens."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw(prompt_tokens=120, completion_tokens=60)

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            result = client.score([{"role": "user", "content": "score this"}])

        assert result.input_tokens == 120

    def test_score_extracts_output_tokens(self):
        """output_tokens is extracted from raw.usage.completion_tokens."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw(prompt_tokens=120, completion_tokens=60)

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            result = client.score([{"role": "user", "content": "score this"}])

        assert result.output_tokens == 60

    def test_score_uses_model_from_config(self):
        """LLMClient passes the model string it was initialized with to create_with_completion."""
        client = LLMClient(model="gpt-4o-mini")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw()

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            client.score([{"role": "user", "content": "score this"}])

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs.get("model") == "gpt-4o-mini"

    def test_score_passes_response_model_job_score_output(self):
        """LLMClient passes response_model=JobScoreOutput to create_with_completion."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw()

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            client.score([{"role": "user", "content": "score this"}])

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs.get("response_model") is JobScoreOutput

    def test_score_passes_max_retries_2(self):
        """LLMClient passes max_retries=2 to create_with_completion."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()
        mock_raw = make_mock_raw()

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            client.score([{"role": "user", "content": "score this"}])

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs.get("max_retries") == 2

    def test_score_defaults_cost_to_zero_when_missing(self):
        """When _hidden_params['response_cost'] is absent, cost_usd defaults to 0.0."""
        client = LLMClient(model="claude-3-haiku-20240307")
        sample_score = make_sample_score_output()

        mock_raw = MagicMock()
        mock_raw.usage.prompt_tokens = 100
        mock_raw.usage.completion_tokens = 50
        mock_raw._hidden_params = {}  # No response_cost key

        with patch("jobinator.scoring.client._client.create_with_completion") as mock_create:
            mock_create.return_value = (sample_score, mock_raw)
            result = client.score([{"role": "user", "content": "score this"}])

        assert result.cost_usd == 0.0

    def test_llm_client_default_model(self):
        """LLMClient defaults to claude-3-haiku-20240307 when no model specified."""
        client = LLMClient()
        assert client.model == "claude-3-haiku-20240307"


class TestLLMClientImports:
    """Smoke tests for module structure."""

    def test_llm_result_dataclass_fields(self):
        """LLMResult has score, cost_usd, input_tokens, output_tokens fields."""
        sample_score = make_sample_score_output()
        result = LLMResult(
            score=sample_score,
            cost_usd=0.001,
            input_tokens=100,
            output_tokens=50,
        )
        assert result.score is sample_score
        assert result.cost_usd == 0.001
        assert result.input_tokens == 100
        assert result.output_tokens == 50
