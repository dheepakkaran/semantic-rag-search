"""Fallback between providers, with every provider call faked.

The behaviour worth pinning down is which refusals are worth moving on from.
A quota error means try the next model; a bad key means the request is wrong
and will be wrong everywhere, so trying three providers just triples the wait
before the same failure.
"""

import pytest

from rag.llm import LLMError, chain, generate, is_available, model_for


@pytest.fixture
def calls(monkeypatch):
    """Record which providers get called, and script what each one does."""
    seen: list[str] = []
    behaviour: dict[str, object] = {}

    def fake_call(prompt: str, provider: str) -> str:
        seen.append(provider)
        outcome = behaviour.get(provider, f"answer from {provider}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("rag.llm._call", fake_call)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    return seen, behaviour


def test_the_first_provider_answers_and_the_rest_are_never_called(calls, monkeypatch):
    seen, _ = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")

    result = generate("prompt")

    assert result.provider == "gemini"
    assert result.fallbacks == []
    assert seen == ["gemini"]


def test_a_quota_error_falls_through_to_the_next_provider(calls, monkeypatch):
    seen, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(429, "quota exceeded, retry in 34s", "gemini")

    result = generate("prompt")

    assert result.provider == "openai"
    assert result.text == "answer from openai"
    assert seen == ["gemini", "openai"]

    # The refusal is reported rather than hidden — the UI says which model
    # stood in and why.
    assert len(result.fallbacks) == 1
    assert result.fallbacks[0].provider == "gemini"
    assert result.fallbacks[0].status == 429
    assert "quota exceeded" in result.fallbacks[0].message


def test_the_same_prompt_reaches_the_fallback(calls, monkeypatch):
    """The point of falling back: the retrieved passages do not change."""
    prompts: list[str] = []
    _, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(429, "quota", "gemini")

    def recording_call(prompt: str, provider: str) -> str:
        prompts.append(prompt)
        if isinstance(behaviour.get(provider), Exception):
            raise behaviour[provider]
        return "ok"

    monkeypatch.setattr("rag.llm._call", recording_call)
    generate("Notes:\n[1] a passage\n\nQuestion: why?")

    assert len(prompts) == 2
    assert prompts[0] == prompts[1]


def test_a_bad_key_stops_the_chain(calls, monkeypatch):
    """401 is not retryable — it will be 401 at every provider too."""
    seen, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(401, "invalid api key", "gemini")

    with pytest.raises(LLMError) as raised:
        generate("prompt")

    assert raised.value.status == 401
    assert seen == ["gemini"]


def test_a_provider_with_no_key_is_skipped_without_being_called(calls, monkeypatch):
    seen, _ = calls
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")

    result = generate("prompt")

    assert result.provider == "openai"
    assert seen == ["openai"]
    assert result.fallbacks[0].status == 503


def test_every_provider_refusing_reports_all_of_them(calls, monkeypatch):
    _, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(429, "quota", "gemini")
    behaviour["openai"] = LLMError(503, "overloaded", "openai")

    with pytest.raises(LLMError) as raised:
        generate("prompt")

    assert "gemini (429)" in str(raised.value)
    assert "openai (503)" in str(raised.value)


def test_pinning_a_provider_disables_fallback(calls, monkeypatch):
    """An explicit choice from the model picker is not overridden."""
    seen, behaviour = calls
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,openai")
    behaviour["gemini"] = LLMError(429, "quota", "gemini")

    with pytest.raises(LLMError):
        generate("prompt", provider="gemini")

    assert seen == ["gemini"]


def test_llm_provider_alone_means_no_fallback(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_CHAIN", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert chain() == ["openai"]


def test_an_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "gemini,gpt5000")
    with pytest.raises(ValueError, match="gpt5000"):
        chain()


def test_availability_follows_the_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not is_available("openai")

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert is_available("openai")

    # Ollama is local, so there is no key to check.
    assert is_available("ollama")


def test_models_can_be_overridden_by_environment(monkeypatch):
    assert model_for("openai") == "gpt-4o-mini"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    assert model_for("openai") == "gpt-4.1-mini"
