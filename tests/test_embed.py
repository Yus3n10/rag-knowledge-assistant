from scripts.rag.embed import embed_texts


class StubResponse:
    def __init__(self, embeddings, prompt_eval_count=0):
        self._embeddings = embeddings
        self._prompt_eval_count = prompt_eval_count

    def raise_for_status(self):
        return None

    def json(self):
        return {"embeddings": self._embeddings, "prompt_eval_count": self._prompt_eval_count}


class StubSession:
    """Returns one 3-dim vector per input text, batch by batch."""

    def __init__(self, dim=3, tokens_per_batch=5):
        self.calls = []
        self.dim = dim
        self.tokens_per_batch = tokens_per_batch

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        vectors = [[float(len(text))] * self.dim for text in json["input"]]
        return StubResponse(vectors, self.tokens_per_batch)


class OrderEncodingSession:
    """Encodes each input's position (via its own text, "0", "1", ...) into the
    returned vector so a reordering bug would produce an off-by-something vector."""

    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        vectors = [[float(text)] for text in json["input"]]
        return StubResponse(vectors, 1)


class MismatchedDimensionSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if len(self.calls) == 1:
            return StubResponse([[0.1, 0.2, 0.3]], 1)
        return StubResponse([[0.1, 0.2]], 1)


def test_embeds_each_text_and_returns_vectors_and_token_count():
    session = StubSession()

    vectors, tokens = embed_texts(
        ["lockout device removal"], model="nomic-embed-text",
        url="http://localhost:11434", session=session,
    )

    assert vectors == [[len("lockout device removal")] * 3]
    assert tokens == 5
    assert session.calls[0][1]["model"] == "nomic-embed-text"
    assert session.calls[0][0] == "http://localhost:11434/api/embed"


def test_rejects_an_empty_batch_rather_than_calling_the_api():
    session = StubSession()

    vectors, tokens = embed_texts(
        [], model="nomic-embed-text", url="http://localhost:11434", session=session,
    )

    assert vectors == []
    assert tokens == 0
    assert session.calls == []


def test_batches_requests_according_to_batch_size():
    session = StubSession()
    texts = [f"text-{i}" for i in range(7)]

    vectors, tokens = embed_texts(
        texts, model="nomic-embed-text", url="http://localhost:11434",
        session=session, batch_size=3,
    )

    assert len(vectors) == 7
    assert len(session.calls) == 3  # batches of 3, 3, 1
    assert tokens == 5 * 3  # summed across the 3 requests


def test_preserves_input_order_across_a_batch_boundary():
    session = OrderEncodingSession()
    texts = [str(i) for i in range(8)]

    vectors, _ = embed_texts(
        texts, model="nomic-embed-text", url="http://localhost:11434",
        session=session, batch_size=3,
    )

    assert vectors == [[float(i)] for i in range(8)]
    assert len(session.calls) == 3


def test_raises_on_dimension_mismatch_between_batches():
    session = MismatchedDimensionSession()
    texts = ["a", "b"]

    try:
        embed_texts(
            texts, model="nomic-embed-text", url="http://localhost:11434",
            session=session, batch_size=1,
        )
        assert False, "expected a ValueError for mismatched embedding dimensions"
    except ValueError:
        pass


# --- Cloudflare Workers AI provider ---------------------------------------
#
# Same contract as the Ollama path: (vectors, total_tokens), input order
# preserved, dimension mismatch still fatal. Cloudflare bills in "neurons"
# and returns no token count, so total_tokens is 0 there -- reporting a
# fabricated number would be worse than reporting none.

class CloudflareStubResponse:
    def __init__(self, vectors):
        self._vectors = vectors

    def raise_for_status(self):
        return None

    def json(self):
        return {"result": {"data": self._vectors, "shape": [len(self._vectors), 3]},
                "success": True, "errors": [], "messages": []}


class CloudflareStubSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        return CloudflareStubResponse([[float(len(t))] * 3 for t in json["text"]])


def test_cloudflare_returns_vectors_and_zero_tokens():
    session = CloudflareStubSession()
    vectors, tokens = embed_texts(
        ["ab", "cdef"], model="@cf/baai/bge-base-en-v1.5", provider="cloudflare",
        account_id="acct", api_token="tok", session=session,
    )
    assert vectors == [[2.0, 2.0, 2.0], [4.0, 4.0, 4.0]]
    assert tokens == 0


def test_cloudflare_posts_to_the_account_scoped_model_url_with_bearer_auth():
    session = CloudflareStubSession()
    embed_texts(["x"], model="@cf/baai/bge-base-en-v1.5", provider="cloudflare",
                account_id="acct123", api_token="secret", session=session)
    url, body, headers = session.calls[0]
    assert url == ("https://api.cloudflare.com/client/v4/accounts/acct123"
                   "/ai/run/@cf/baai/bge-base-en-v1.5")
    assert headers["Authorization"] == "Bearer secret"
    assert body == {"text": ["x"]}


def test_cloudflare_requires_credentials():
    for kwargs in ({"account_id": "a"}, {"api_token": "t"}, {}):
        try:
            embed_texts(["x"], model="m", provider="cloudflare",
                        session=CloudflareStubSession(), **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")


def test_rejects_an_unknown_provider():
    try:
        embed_texts(["x"], model="m", provider="nope", session=StubSession())
    except ValueError as err:
        assert "nope" in str(err)
        return
    raise AssertionError("expected ValueError")
