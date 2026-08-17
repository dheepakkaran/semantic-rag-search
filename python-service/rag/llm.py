"""Generation, behind one function so the provider can be swapped.

Retrieval does not care which model writes the answer, so the choice is a
single environment variable:

    LLM_PROVIDER=gemini   hosted, free tier, good answers  (default)
    LLM_PROVIDER=openai   hosted, paid per token
    LLM_PROVIDER=ollama   local, free, works with no network
    LLM_PROVIDER=mock     no model at all, for tests

Keeping the providers side by side is what makes it possible to compare a
small local model against a hosted one on the same retrieved passages.
"""

import os


class LLMError(RuntimeError):
    """A provider refused the request.

    Carries the provider's own status code so the API can pass it through
    rather than reporting every upstream problem as a 500. A quota error and a
    bug in this service are not the same thing, and the caller can only act on
    the difference if it survives.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def generate(prompt: str) -> str:
    """Send `prompt` to the configured model and return its text answer."""
    provider = os.getenv("LLM_PROVIDER", "gemini")

    if provider == "gemini":
        from google import genai
        from google.genai import errors

        client = genai.Client(api_key=_require_key("GEMINI_API_KEY"))
        try:
            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
                contents=prompt,
            )
        except errors.APIError as exc:
            # The free tier allows 20 generate_content calls a day, so 429 is
            # the error this hits in practice, not an exotic one.
            raise LLMError(exc.code or 502, _clean(str(exc))) from exc
        return response.text

    if provider == "openai":
        import openai

        client = openai.OpenAI(api_key=_require_key("OPENAI_API_KEY"))
        try:
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.APIStatusError as exc:
            raise LLMError(exc.status_code, _clean(str(exc))) from exc
        return response.choices[0].message.content

    if provider == "ollama":
        import ollama

        try:
            response = ollama.chat(
                model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # ollama raises ResponseError or ConnectionError
            raise LLMError(502, f"ollama call failed: {exc}") from exc
        return response["message"]["content"]

    if provider == "mock":
        # Returns the prompt's own question back. Lets the pipeline and the
        # API be exercised without a key, a network call or a GPU.
        return "[mock] no model was called"

    raise ValueError(
        f"unknown LLM_PROVIDER {provider!r}; "
        "expected one of: gemini, openai, ollama, mock"
    )


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
        raise RuntimeError(
            f"{name} is not set. Put it in a .env file (see .env.example) "
            f"or export it before starting the service."
        )
    return key
