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
