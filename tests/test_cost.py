"""Tests for scripts.rag.cost. See
docs/superpowers/plans/2026-08-03-cost-and-latency-dashboard.md (Task 3)."""

from scripts.rag.cost import cost_usd


def test_known_ollama_model_is_free():
    assert cost_usd("ollama", "llama3.1:8b", prompt_tokens=1_000_000, completion_tokens=1_000_000) == 0.0


def test_known_groq_model_computes_from_the_rate_table():
    # 1,066 prompt / 200 completion tokens at $0.05 / $0.08 per million.
    got = cost_usd("groq", "llama-3.1-8b-instant", prompt_tokens=1_066, completion_tokens=200)
    expected = (1_066 / 1_000_000) * 0.05 + (200 / 1_000_000) * 0.08
    assert got == expected


def test_unknown_model_returns_none_not_zero():
    assert cost_usd("groq", "some-model-not-in-the-table", prompt_tokens=100, completion_tokens=100) is None


def test_unknown_provider_returns_none():
    assert cost_usd("openai", "gpt-4", prompt_tokens=100, completion_tokens=100) is None
