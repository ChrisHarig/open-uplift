"""Tests for the multi-provider LLM client."""

import pytest

from open_uplift.llm_client import LLMClient, LLMResponse, MODEL_PRICING


def test_provider_selection_anthropic():
    client = LLMClient("anthropic", "claude-sonnet-4-6", "fake-key")
    assert client.provider == "anthropic"
    assert client.model == "claude-sonnet-4-6"


def test_provider_selection_openai():
    client = LLMClient("openai", "gpt-4o", "fake-key")
    assert client.provider == "openai"
    assert client.model == "gpt-4o"


def test_unsupported_provider():
    """Non-anthropic providers route through OpenAI-compatible API, which fails with auth/connection error."""
    client = LLMClient("unsupported", "model", "fake-key")
    with pytest.raises(Exception):
        client.complete("system", "user")


def test_estimate_cost_known_model():
    client = LLMClient("anthropic", "claude-sonnet-4-6", "fake-key")
    cost = client._estimate_cost(1_000_000, 1_000_000)
    # sonnet: (1M * 3.0 + 1M * 15.0) / 1M = 18.0
    assert cost == pytest.approx(18.0, abs=0.01)


def test_estimate_cost_unknown_model():
    client = LLMClient("anthropic", "unknown-model", "fake-key")
    cost = client._estimate_cost(1000, 1000)
    assert cost == 0.0


def test_estimate_cost_prefix_match():
    client = LLMClient("anthropic", "claude-sonnet-4-6-20260101", "fake-key")
    cost = client._estimate_cost(1_000_000, 0)
    # Should match claude-sonnet-4-6 via prefix
    assert cost > 0


def test_model_pricing_has_entries():
    assert len(MODEL_PRICING) >= 5
    assert "claude-sonnet-4-6" in MODEL_PRICING
    assert "gpt-4o" in MODEL_PRICING


def test_llm_response_dataclass():
    r = LLMResponse(
        content="Hello",
        input_tokens=100,
        output_tokens=50,
        model="claude-sonnet-4-6",
        cost_usd=0.001,
    )
    assert r.content == "Hello"
    assert r.input_tokens == 100


def test_mock_complete(mock_llm):
    """LLMClient.complete should use the mock."""
    client = LLMClient("anthropic", "claude-sonnet-4-6", "fake")
    response = client.complete("system", "user")
    assert response.content
    assert response.input_tokens == 1000
