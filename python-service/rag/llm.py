"""Generation, behind one function so the provider can be swapped.

Retrieval does not care which model writes the answer, which is what makes two
things possible:

  * choosing a provider per request, and
  * falling back automatically when one refuses.

The fallback matters here because the Gemini free tier allows 20 generations a
day. When it runs out the retrieved passages are still perfectly good, so the
same prompt goes to the next provider in the chain rather than the request
failing. Nothing is re-retrieved and nothing is re-embedded — the context the
model sees is identical.

    LLM_PROVIDER_CHAIN=gemini,openai,ollama   order to try (default)
    LLM_PROVIDER=gemini                       single provider, no fallback

A provider is skipped without being called if its key is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Statuses worth trying the next provider for: quota, overload, transient
# server faults. A 401 or a 400 is not in here — a bad key or a malformed
# request will fail the same way everywhere, so moving on just wastes time.
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}

DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2:3b",
    "mock": "mock",
}

KEY_FOR = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


class LLMError(RuntimeError):
    """A provider refused the request.

    Carries the provider's own status code so the API can pass it through
    rather than reporting every upstream problem as a 500. A quota error and a
    bug in this service are not the same thing.
    """

    def __init__(self, status: int, message: str, provider: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.provider = provider

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE


@dataclass
class Attempt:
    """A provider that was tried and refused."""

    provider: str
    model: str
    status: int
    message: str


@dataclass
class Generation:
    """An answer, and the record of what it took to get one."""

    text: str
    provider: str
    model: str
    fallbacks: list[Attempt] = field(default_factory=list)


def model_for(provider: str) -> str:
    return os.getenv(f"{provider.upper()}_MODEL", DEFAULT_MODELS.get(provider, provider))


def is_available(provider: str) -> bool:
    """Whether this provider could be called at all.

    Only key presence is checked. Ollama needs a local daemon and Gemini needs
    quota left, and neither can be known without making a request.
    """
    key = KEY_FOR.get(provider)
    return True if key is None else bool(os.getenv(key))


def chain() -> list[str]:
    """The providers to try, in order.

    LLM_PROVIDER on its own means "this one, no fallback" — the behaviour
    before fallback existed, kept so nothing that sets it changes meaning.
    """
    raw = os.getenv("LLM_PROVIDER_CHAIN")
    if raw:
        names = [name.strip() for name in raw.split(",") if name.strip()]
    else:
        names = [os.getenv("LLM_PROVIDER", "gemini")]

    unknown = [name for name in names if name not in DEFAULT_MODELS]
    if unknown:
        raise ValueError(
            f"unknown provider(s) {unknown}; expected any of {sorted(DEFAULT_MODELS)}"
        )
    return names


def generate(prompt: str, provider: str | None = None) -> Generation:
    """Answer `prompt`, walking the chain until a provider succeeds.

    `provider` pins a single one and disables fallback, which is what the UI's
    model picker sends when the reader has chosen deliberately.
    """
    order = [provider] if provider else chain()

    attempts: list[Attempt] = []
    for name in order:
        model = model_for(name)

        if not is_available(name):
            attempts.append(
                Attempt(name, model, 503, f"{KEY_FOR[name]} is not set")
            )
            continue

        try:
            return Generation(_call(prompt, name), name, model, attempts)
        except LLMError as error:
            attempts.append(Attempt(name, model, error.status, str(error)))
            # A non-retryable refusal will repeat everywhere, so stop.
            if not error.retryable:
                break

    raise _exhausted(attempts)


def _exhausted(attempts: list[Attempt]) -> LLMError:
    if not attempts:
        raise ValueError("no providers configured")

    last = attempts[-1]
    tried = ", ".join(f"{a.provider} ({a.status})" for a in attempts)
    if len(attempts) == 1:
        return LLMError(last.status, last.message, last.provider)
    return LLMError(
        last.status, f"every provider refused — tried {tried}. Last: {last.message}", last.provider
    )


def _call(prompt: str, provider: str) -> str:
    """One provider, one attempt. Raises LLMError on refusal."""
    if provider == "gemini":
        from google import genai
        from google.genai import errors

        client = genai.Client(api_key=_require_key("GEMINI_API_KEY"))
        try:
            response = client.models.generate_content(
                model=model_for("gemini"), contents=prompt
            )
        except errors.APIError as exc:
            raise LLMError(exc.code or 502, _clean(str(exc)), provider) from exc
        return response.text or ""

    if provider == "openai":
        import openai

        client = openai.OpenAI(api_key=_require_key("OPENAI_API_KEY"))
        try:
            response = client.chat.completions.create(
                model=model_for("openai"),
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.APIStatusError as exc:
            raise LLMError(exc.status_code, _clean(str(exc)), provider) from exc
        except openai.APIConnectionError as exc:
            raise LLMError(502, _clean(str(exc)), provider) from exc
        return response.choices[0].message.content or ""

    if provider == "ollama":
        import ollama

        try:
            response = ollama.chat(
                model=model_for("ollama"),
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # ResponseError, ConnectionError, ...
            raise LLMError(502, f"ollama call failed: {_clean(str(exc))}", provider) from exc
        return response["message"]["content"]

    if provider == "mock":
        return "[mock] no model was called"

    raise ValueError(f"unknown provider {provider!r}")


def _clean(message: str) -> str:
    """Trim a provider's error to its first line.

    Both SDKs stringify the whole JSON error body, which is several hundred
    characters of nested detail. The first line carries the part a caller can
    act on.
    """
    return message.strip().splitlines()[0][:300]


def _require_key(name: str) -> str:
    key = os.getenv(name)
    if not key:
        raise LLMError(503, f"{name} is not set", name.split("_")[0].lower())
    return key
