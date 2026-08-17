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


def generate(prompt: str) -> str:
    """Send `prompt` to the configured model and return its text answer."""
    provider = os.getenv("LLM_PROVIDER", "gemini")

    if provider == "gemini":
        from google import genai

        client = genai.Client(api_key=_require_key("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            contents=prompt,
        )
        return response.text

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=_require_key("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    if provider == "ollama":
        import ollama

        response = ollama.chat(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]

    if provider == "mock":
        # Returns the prompt's own question back. Lets the pipeline and the
        # API be exercised without a key, a network call or a GPU.
        return "[mock] no model was called"

    raise ValueError(
        f"unknown LLM_PROVIDER {provider!r}; "
        "expected one of: gemini, openai, ollama, mock"
    )


def _require_key(name: str) -> str:
    key = os.getenv(name)
    if not key:
        raise RuntimeError(
            f"{name} is not set. Put it in a .env file (see .env.example) "
            f"or export it before starting the service."
        )
    return key
