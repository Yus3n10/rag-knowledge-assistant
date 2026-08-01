"""Generate a chat completion via Ollama's /api/chat endpoint."""

import time

import requests


def generate(messages, *, model, url, session=None, options=None):
    """Send messages to the model. Returns (answer_text, stats).

    stats contains prompt_tokens, completion_tokens, latency_s, load_duration_s.
    temperature defaults to 0 for reproducible eval runs; pass options to override.
    """
    session = session or requests.Session()
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
