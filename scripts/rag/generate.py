"""Generate a chat completion via a pluggable LLM provider (Ollama or Groq)."""

import time

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def generate(messages, *, provider="ollama", model, url=None, api_key=None,
             session=None, options=None):
    """Send messages to the model. Returns (answer_text, stats).

    stats always contains prompt_tokens, completion_tokens, latency_s,
    load_duration_s -- same keys regardless of provider, so callers (and the
    cost/latency dashboard) never need to branch on which provider answered.
    temperature defaults to 0 for reproducible eval runs; pass options to
    override (ollama only -- groq takes no extra options today).
    """
    session = session or requests.Session()

    if provider == "ollama":
        return _generate_ollama(messages, model=model, url=url, session=session,
                                 options=options)
    if provider == "groq":
        if not api_key:
            raise ValueError("provider='groq' requires an api_key")
        return _generate_groq(messages, model=model, api_key=api_key, session=session)

    raise ValueError(f"unknown provider: {provider!r}")


def _generate_ollama(messages, *, model, url, session, options):
    request_options = {"temperature": 0}
    if options:
        request_options.update(options)

    start = time.monotonic()
    response = session.post(
        f"{url}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": request_options,
        },
        timeout=120,
    )
    latency_s = time.monotonic() - start
    response.raise_for_status()
    data = response.json()

    answer = data.get("message", {}).get("content")
    if not answer:
        raise ValueError("Ollama response had no message.content")

    stats = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
        "latency_s": latency_s,
        "load_duration_s": data.get("load_duration", 0) / 1e9,
    }

    return answer, stats


def _generate_groq(messages, *, model, api_key, session):
    start = time.monotonic()
    response = session.post(
        GROQ_URL,
        json={"model": model, "messages": messages, "temperature": 0},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    latency_s = time.monotonic() - start
    response.raise_for_status()
    data = response.json()

    answer = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not answer:
        raise ValueError("Groq response had no choices[0].message.content")

    usage = data.get("usage", {})
    stats = {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_s": latency_s,
        "load_duration_s": 0.0,
    }

    return answer, stats
