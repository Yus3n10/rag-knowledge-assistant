"""Turn text into embedding vectors via Ollama's /api/embed endpoint."""

import requests


def embed_texts(texts, *, model, url, session=None, batch_size=32):
    """Embed texts in order, batched. Returns (vectors, total_prompt_eval_count)."""
    if not texts:
        return [], 0

    session = session or requests.Session()
    vectors = []
    total_tokens = 0
    dim = None

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = session.post(
            f"{url}/api/embed",
            json={"model": model, "input": batch},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        batch_vectors = data["embeddings"]

        for vector in batch_vectors:
            if dim is None:
                dim = len(vector)
            elif len(vector) != dim:
                raise ValueError(
                    f"embedding dimension mismatch: expected {dim}, got {len(vector)}"
                )

        vectors.extend(batch_vectors)
        total_tokens += data.get("prompt_eval_count", 0)

    return vectors, total_tokens
