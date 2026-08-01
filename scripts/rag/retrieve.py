"""Retrieve the k chunks nearest a query by cosine distance over embeddings."""

# Permission filtering (when it lands) MUST be added as a predicate inside this
# WHERE clause, not applied to the Python result list after fetchall(). Filtering
# after the fact silently returns fewer, worse results with no signal that
# anything was withheld -- role-based access depends on "top k" meaning "top k
# among what this user may see," which only holds if the filter runs before LIMIT.
SEARCH_SQL = """
SELECT chunk_id, paragraph_id, text, embedding <=> %(embedding)s::vector AS distance
FROM chunks
WHERE required_role IS NULL OR required_role = ANY(%(roles)s)
ORDER BY distance
LIMIT %(k)s
"""


def _vector_literal(vector):
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def search(query, *, k=5, conn, embedder, roles=None):
    """Return the k chunks nearest to query, ascending by cosine distance,
    restricted to chunks this caller may see.

    embedder(texts: list[str]) -> list[vector]; called once with [query].
    conn is a psycopg-style connection exposing cursor() as a context manager.

    roles=None behaves as "public content only" (equivalent to []), not as
    "everything" -- it is sent to the query as an empty list so the
    permission predicate below still runs.
    """
    [vector] = embedder([query])
    role_list = list(roles) if roles else []

    with conn.cursor() as cur:
        cur.execute(SEARCH_SQL, {"embedding": _vector_literal(vector), "k": k, "roles": role_list})
        rows = cur.fetchall()

    return [
        {"chunk_id": chunk_id, "paragraph_id": paragraph_id, "text": text, "distance": distance}
        for chunk_id, paragraph_id, text, distance in rows
    ]
