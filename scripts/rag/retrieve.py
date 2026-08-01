"""Retrieve the k chunks nearest a query by cosine distance over embeddings."""

# Permission filtering (when it lands) MUST be added as a predicate inside this
# WHERE clause, not applied to the Python result list after fetchall(). Filtering
# after the fact silently returns fewer, worse results with no signal that
# anything was withheld -- role-based access depends on "top k" meaning "top k
# among what this user may see," which only holds if the filter runs before LIMIT.
SEARCH_SQL = """
SELECT chunk_id, paragraph_id, text, embedding <=> %(embedding)s::vector AS distance
FROM chunks
WHERE TRUE
ORDER BY distance
LIMIT %(k)s
"""


def _vector_literal(vector):
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def search(query, *, k=5, conn, embedder):
    """Return the k chunks nearest to query, ascending by cosine distance.

    embedder(texts: list[str]) -> list[vector]; called once with [query].
    conn is a psycopg-style connection exposing cursor() as a context manager.
    """
    [vector] = embedder([query])

    with conn.cursor() as cur:
        cur.execute(SEARCH_SQL, {"embedding": _vector_literal(vector), "k": k})
        rows = cur.fetchall()

    return [
        {"chunk_id": chunk_id, "paragraph_id": paragraph_id, "text": text, "distance": distance}
        for chunk_id, paragraph_id, text, distance in rows
    ]
