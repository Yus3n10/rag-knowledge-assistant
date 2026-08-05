"""Tests for scripts.rag.requestlog.record_request. Everything is stubbed --
no Postgres. See docs/superpowers/plans/2026-08-03-cost-and-latency-dashboard.md
(Task 1)."""

from scripts.rag.requestlog import record_request


class StubCursor:
    def __init__(self, raise_on_execute=None):
        self.executed = []
        self._raise_on_execute = raise_on_execute

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if self._raise_on_execute:
            raise self._raise_on_execute
        self.executed.append((sql, params))


class StubConnection:
    def __init__(self, raise_on_execute=None):
        self.cur = StubCursor(raise_on_execute=raise_on_execute)
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


FIELDS = dict(
    question="who may remove a lockout device?",
    username="officer",
    roles=["safety_officer"],
    provider="ollama",
    model="llama3.1:8b",
    prompt_tokens=100,
    completion_tokens=20,
    latency_s=4.5,
    citation_count=1,
    ungrounded_number_count=0,
    refused=False,
    k=10,
    cost_usd=0.0,
)


def test_record_request_inserts_the_right_values():
    conn = StubConnection()

    record_request(conn, **FIELDS)

    [(sql, params)] = conn.cur.executed
    assert "INSERT INTO request_log" in sql
    assert params["question"] == FIELDS["question"]
    assert params["username"] == FIELDS["username"]
    assert params["roles"] == FIELDS["roles"]
    assert params["provider"] == FIELDS["provider"]
    assert params["model"] == FIELDS["model"]
    assert params["prompt_tokens"] == FIELDS["prompt_tokens"]
    assert params["completion_tokens"] == FIELDS["completion_tokens"]
    assert params["latency_s"] == FIELDS["latency_s"]
    assert params["citation_count"] == FIELDS["citation_count"]
    assert params["ungrounded_number_count"] == FIELDS["ungrounded_number_count"]
    assert params["refused"] == FIELDS["refused"]
    assert params["k"] == FIELDS["k"]
    assert params["cost_usd"] == FIELDS["cost_usd"]
    assert conn.committed


def test_record_request_stores_none_cost_for_an_unpriced_model():
    conn = StubConnection()
    fields = dict(FIELDS, provider="groq", model="unknown-model", cost_usd=None)

    record_request(conn, **fields)

    [(_, params)] = conn.cur.executed
    assert params["cost_usd"] is None


def test_record_request_swallows_an_execute_error():
    conn = StubConnection(raise_on_execute=RuntimeError("db is down"))

    record_request(conn, **FIELDS)  # must not raise
