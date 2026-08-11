"""Turn text into embedding vectors via a pluggable provider.

Ollama (`nomic-embed-text`) is the local-development default. Cloudflare
Workers AI (`@cf/baai/bge-base-en-v1.5`) is the hosted path used in
deployments where no VM is available to run a model -- see
docs/superpowers/plans/2026-08-12-deploy-without-oracle.md.

Both are 768-dim, so the `vector(768)` column needs no migration to switch.
They are NOT interchangeable against an existing index: the vectors come from
different models, so an index built with one and queried with the other
degrades retrieval *silently*. Rebuild the index and re-run eval/run_eval.py
when changing provider. The dimension check below catches a wrong-size model;
nothing but the eval catches a wrong same-size one.
"""

import requests

CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"


def embed_texts(texts, *, model, url=None, session=None, batch_size=32,
                provider="ollama", account_id=None, api_token=None):
    """Embed texts in order, batched. Returns (vectors, total_prompt_eval_count).

    total_prompt_eval_count is 0 for Cloudflare, which bills in neurons and
    reports no token count -- see tests/test_embed.py.
    """
    if not texts:
        return [], 0

    if provider == "ollama":
        post_batch = _ollama_batch(model=model, url=url)
    elif provider == "cloudflare":
        if not account_id or not api_token:
            raise ValueError("provider='cloudflare' requires account_id and api_token")
        post_batch = _cloudflare_batch(model=model, account_id=account_id,
                                       api_token=api_token)
    else:
        raise ValueError(f"unknown provider: {provider!r}")

    session = session or requests.Session()
    vectors = []
    total_tokens = 0
    dim = None

    for i in range(0, len(texts), batch_size):
        batch_vectors, batch_tokens = post_batch(session, texts[i:i + batch_size])

        for vector in batch_vectors:
            if dim is None:
                dim = len(vector)
            elif len(vector) != dim:
                raise ValueError(
                    f"embedding dimension mismatch: expected {dim}, got {len(vector)}"
                )

        vectors.extend(batch_vectors)
        total_tokens += batch_tokens

    return vectors, total_tokens


def _ollama_batch(*, model, url):
    def post(session, batch):
        response = session.post(
            f"{url}/api/embed",
            json={"model": model, "input": batch},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"], data.get("prompt_eval_count", 0)

    return post


def _cloudflare_batch(*, model, account_id, api_token):
    def post(session, batch):
        response = session.post(
            CLOUDFLARE_URL.format(account_id=account_id, model=model),
            json={"text": batch},
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        # Cloudflare returns HTTP 200 with success=false and an errors array
        # rather than an error status, so raise_for_status alone would let a
        # failed call through as an empty result set.
        if not data.get("success", False):
            raise ValueError(f"Cloudflare Workers AI error: {data.get('errors')}")
        return data["result"]["data"], 0

    return post
