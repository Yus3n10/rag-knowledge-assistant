"""FastAPI endpoint tests. Everything is stubbed -- no Ollama, no Postgres.
See docs/superpowers/plans/2026-08-02-api-and-access-control.md (Task 4).
"""

from fastapi.testclient import TestClient

from api.auth import create_token, hash_password
from api.main import app, get_conn, get_embedder, get_generator


class StubCursor:
    """Mirrors tests/test_retrieve.py's stub, plus fetchone() for /health and
    /auth/login's single-row lookups."""

    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class StubConnection:
    def __init__(self, rows=None, one=None):
        self.cur = StubCursor(rows=rows, one=one)

    def cursor(self):
        return self.cur

    def commit(self):
        pass


class StubEmbedder:
    def __init__(self, vector=(0.1, 0.2, 0.3)):
        self.calls = []
        self.vector = list(vector)

    def __call__(self, texts):
        self.calls.append(texts)
        return [self.vector for _ in texts]


class StubGenerator:
    def __init__(self, answer="the answer [1910.147(e)(3)]", stats=None):
        self.calls = []
        self.answer = answer
        self.stats = stats or {
            "prompt_tokens": 100, "completion_tokens": 20,
            "latency_s": 4.5, "load_duration_s": 0.0,
        }

    def __call__(self, messages):
        self.calls.append(messages)
        return self.answer, self.stats


# (chunk_id, paragraph_id, text, distance)
ASK_ROWS = [
    ("c1", "1910.147(e)(3)", "Only the employee who applied the device may remove it.", 0.12),
]


def make_client(rows=None, one=None):
    """Build a TestClient with conn/embedder/generator dependencies stubbed
    out. Returns (client, stub_conn, stub_embedder, stub_generator) so tests
    can inspect what each stub received."""
    stub_conn = StubConnection(rows=rows or ASK_ROWS, one=one)
    stub_embedder = StubEmbedder()
    stub_generator = StubGenerator()

    app.dependency_overrides[get_conn] = lambda: stub_conn
    app.dependency_overrides[get_embedder] = lambda: stub_embedder
    app.dependency_overrides[get_generator] = lambda: stub_generator

    client = TestClient(app)
    return client, stub_conn, stub_embedder, stub_generator


def teardown_function(_):
    app.dependency_overrides.clear()


def auth_header(username="viewer", roles=None):
    token = create_token(username, roles or [])
    return {"Authorization": f"Bearer {token}"}


# --- /health -----------------------------------------------------------------

def test_health_reports_chunk_count():
    client, _, _, _ = make_client(one=(965,))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["chunk_count"] == 965


# --- /auth/login ---------------------------------------------------------------

def test_login_with_valid_credentials_returns_a_token():
    password_hash = hash_password("officer-pass")
    client, _, _, _ = make_client(one=(password_hash, ["safety_officer"]))

    response = client.post("/auth/login", json={"username": "officer", "password": "officer-pass"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_wrong_password_is_401():
    password_hash = hash_password("officer-pass")
    client, _, _, _ = make_client(one=(password_hash, ["safety_officer"]))

    response = client.post("/auth/login", json={"username": "officer", "password": "nope"})

    assert response.status_code == 401


def test_login_with_unknown_username_is_401():
    client, _, _, _ = make_client(one=None)

    response = client.post("/auth/login", json={"username": "ghost", "password": "whatever"})

    assert response.status_code == 401


# --- /ask ----------------------------------------------------------------------

def test_ask_without_a_token_is_401():
    client, _, _, _ = make_client()

    response = client.post("/ask", json={"question": "who may remove a lockout device?"})

    assert response.status_code == 401


def test_ask_with_an_invalid_token_is_401():
    client, _, _, _ = make_client()

    response = client.post(
        "/ask", json={"question": "q"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


def test_ask_with_a_valid_token_returns_a_well_formed_body():
    client, _, _, _ = make_client()

    response = client.post("/ask", json={"question": "q"}, headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {
        "answer", "citations", "citation_report", "ungrounded_numbers",
        "retrieved", "stats",
    }
    assert body["retrieved"][0]["paragraph_id"] == "1910.147(e)(3)"
    assert body["retrieved"][0]["distance"] == 0.12


def test_ask_retrieved_entries_include_heading_trail_and_text():
    rows = [("c1", "1910.147(e)(3)", "TRAIL HERE\n\nOnly the employee who applied the device may remove it.", 0.12)]
    client, _, _, _ = make_client(rows=rows)

    response = client.post("/ask", json={"question": "q"}, headers=auth_header())

    [entry] = response.json()["retrieved"]
    assert entry["heading_trail"] == "TRAIL HERE"
    assert entry["text"] == "Only the employee who applied the device may remove it."


def test_ask_threads_the_tokens_roles_into_retrieval():
    client, stub_conn, _, _ = make_client()

    client.post(
        "/ask", json={"question": "q"},
        headers=auth_header(username="officer", roles=["safety_officer"]),
    )

    _, params = stub_conn.cur.executed[0]
    assert params["roles"] == ["safety_officer"]


def test_ask_with_no_roles_in_token_searches_public_only():
    client, stub_conn, _, _ = make_client()

    client.post("/ask", json={"question": "q"}, headers=auth_header(username="viewer", roles=[]))

    _, params = stub_conn.cur.executed[0]
    assert params["roles"] == []


# --- request_log recording ------------------------------------------------

def test_ask_records_one_request_log_row():
    client, stub_conn, _, _ = make_client()

    client.post(
        "/ask", json={"question": "who may remove a lockout device?"},
        headers=auth_header(username="officer", roles=["safety_officer"]),
    )

    insert_calls = [
        (sql, params) for sql, params in stub_conn.cur.executed
        if "INSERT INTO request_log" in sql
    ]
    assert len(insert_calls) == 1
    _, params = insert_calls[0]
    assert params["question"] == "who may remove a lockout device?"
    assert params["username"] == "officer"
    assert params["roles"] == ["safety_officer"]
    assert params["provider"] == "ollama"
    assert params["prompt_tokens"] == 100
    assert params["completion_tokens"] == 20
    assert params["latency_s"] == 4.5
    assert params["citation_count"] == 1
    assert params["ungrounded_number_count"] == 0
    assert params["refused"] is False
    assert params["k"] == 10


def _refused_flag_for(answer_text):
    """Run one /ask whose model returns answer_text, return the recorded refused flag."""
    client, stub_conn, _, _ = make_client()
    from api.main import app, get_generator

    app.dependency_overrides[get_generator] = lambda: (
        lambda messages: (answer_text, {
            "prompt_tokens": 50, "completion_tokens": 10,
            "latency_s": 1.0, "load_duration_s": 0.0,
        })
    )
    client.post("/ask", json={"question": "q"}, headers=auth_header())
    _, params = [
        (sql, p) for sql, p in stub_conn.cur.executed if "INSERT INTO request_log" in sql
    ][0]
    return params["refused"]


def test_ask_records_refused_when_the_model_declines_with_no_citations():
    from api.main import _REFUSAL_EXAMPLE

    assert _refused_flag_for(_REFUSAL_EXAMPLE) is True


def test_ask_records_refused_when_the_model_paraphrases_the_refusal():
    # Real llama3.1:8b output. The model keeps the head of the prompt's example
    # sentence and paraphrases the tail, so matching the full example sentence
    # scored genuine refusals as answers and undercounted the refusal rate.
    paraphrased = (
        "The provided text does not contain information about Personal "
        "Protective Equipment (PPE) requirements for hazard communication."
    )
    assert _refused_flag_for(paraphrased) is True


def test_ask_does_not_record_refused_for_a_real_answer():
    answered = "According to [1910.147(e)(3)], the employee who applied it removes it."
    assert _refused_flag_for(answered) is False


def test_ask_still_returns_200_when_the_recorder_raises(monkeypatch):
    import api.main as main

    def boom(conn, **fields):
        raise RuntimeError("db is down")

    monkeypatch.setattr(main, "record_request", boom)
    client, _, _, _ = make_client()

    response = client.post("/ask", json={"question": "q"}, headers=auth_header())

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["citations"]


def test_ask_ignores_roles_claimed_in_the_request_body():
    # The point of this whole phase: a caller cannot grant themselves access
    # by putting roles in the JSON body. Only the token's roles may reach
    # retrieval.
    client, stub_conn, _, _ = make_client()

    client.post(
        "/ask",
        json={"question": "q", "roles": ["safety_officer"]},
        headers=auth_header(username="viewer", roles=[]),
    )

    _, params = stub_conn.cur.executed[0]
    assert params["roles"] == []
