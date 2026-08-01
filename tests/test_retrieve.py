from scripts.rag.retrieve import search, SEARCH_SQL


class StubCursor:
    """Records execute() params and hands back canned rows on fetchall()."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows


class StubConnection:
    def __init__(self, rows):
        self.cur = StubCursor(rows)

    def cursor(self):
        return self.cur


class StubEmbedder:
    """Fake embedder: records every call, returns one fixed vector per text."""

    def __init__(self, vector=(0.1, 0.2, 0.3)):
        self.calls = []
        self.vector = list(vector)

    def __call__(self, texts):
        self.calls.append(texts)
        return [self.vector for _ in texts]


# (chunk_id, paragraph_id, text, distance) -- as SEARCH_SQL's SELECT would return them,
# already in ascending-distance order (that's Postgres's ORDER BY, not this stub's job).
ROWS = [
    ("chunk-1", "1910.147(e)(3)", "Only the employee who applied the device may remove it.", 0.12),
    ("chunk-2", "1910.147(c)(1)", "Energy control program text.", 0.34),
]


def test_returns_results_ordered_by_ascending_distance():
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    results = search("who may remove a lockout device", conn=conn, embedder=embedder)

    assert [r["distance"] for r in results] == [0.12, 0.34]


def test_k_is_passed_through_to_the_query():
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    search("query", k=3, conn=conn, embedder=embedder)

    _, params = conn.cur.executed[0]
    assert params["k"] == 3


def test_embeds_the_query_text_exactly_once():
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    search("who may remove a lockout device", k=5, conn=conn, embedder=embedder)

    # one call, for the query alone -- not once per result row
    assert embedder.calls == [["who may remove a lockout device"]]


def test_result_dicts_carry_all_four_keys():
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    results = search("query", conn=conn, embedder=embedder)

    for r in results:
        assert set(r.keys()) == {"chunk_id", "paragraph_id", "text", "distance"}


def test_sql_contains_the_permission_predicate():
    # The filter must live in the query itself, never applied to the Python
    # result list afterwards -- otherwise "top k" silently stops meaning
    # "top k among what this caller may see."
    assert "required_role" in SEARCH_SQL
    assert "ANY(" in SEARCH_SQL.upper() or "ANY (" in SEARCH_SQL.upper()


def test_roles_list_is_passed_through_to_the_query_params():
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    search("query", conn=conn, embedder=embedder, roles=["safety_officer"])

    _, params = conn.cur.executed[0]
    assert params["roles"] == ["safety_officer"]


def test_roles_none_is_sent_as_an_empty_list_not_dropped():
    # roles=None must behave as "public content only" -- i.e. the query still
    # runs with a (empty) roles filter, not with the predicate skipped
    # entirely (which would return everything, gated or not).
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    search("query", conn=conn, embedder=embedder, roles=None)

    sql, params = conn.cur.executed[0]
    assert params["roles"] == []
    assert "required_role" in sql


def test_results_still_ordered_by_ascending_distance_with_roles():
    conn = StubConnection(ROWS)
    embedder = StubEmbedder()

    results = search("query", conn=conn, embedder=embedder, roles=["safety_officer"])

    assert [r["distance"] for r in results] == [0.12, 0.34]
