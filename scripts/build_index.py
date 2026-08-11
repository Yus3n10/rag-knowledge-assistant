"""Chunk the OSHA corpus, embed every chunk, and upsert into Postgres+pgvector."""

import json
import os
import time
from pathlib import Path

import psycopg

from scripts.rag.chunk import chunk_records
from scripts.rag.embed import embed_texts

DEFAULTS = {
    "DATABASE_URL": "postgresql://rag:ragdev@localhost:5433/rag",
    "OLLAMA_URL": "http://localhost:11434",
    "EMBED_MODEL": "nomic-embed-text",
    "CF_EMBED_MODEL": "@cf/baai/bge-base-en-v1.5",
}

COLUMNS = ("chunk_id", "paragraph_id", "section_id", "subpart",
           "heading_trail", "text", "embedding")

UPSERT_SQL = f"""
INSERT INTO chunks ({", ".join(COLUMNS)})
VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (chunk_id) DO UPDATE SET
    paragraph_id = EXCLUDED.paragraph_id,
    section_id = EXCLUDED.section_id,
    subpart = EXCLUDED.subpart,
    heading_trail = EXCLUDED.heading_trail,
    text = EXCLUDED.text,
    embedding = EXCLUDED.embedding
"""


def chunks_to_rows(sections, subpart, subpart_name, *, embed):
    """Chunk every section and embed the chunk texts in one batch call. Returns
    (rows, tokens) where each row is a COLUMNS-ordered tuple ready for the DB, with
    the embedding still a plain list of floats (not yet formatted for SQL)."""
    chunks = []
    for section in sections:
        chunks.extend(chunk_records(section, subpart, subpart_name))

    vectors, tokens = embed([c["text"] for c in chunks])

    rows = [
        (c["chunk_id"], c["paragraph_id"], c["section_id"], c["subpart"],
         c["heading_trail"], c["text"], vector)
        for c, vector in zip(chunks, vectors)
    ]
    return rows, tokens


def _vector_literal(vector):
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def main():
    database_url = os.environ.get("DATABASE_URL", DEFAULTS["DATABASE_URL"])
    ollama_url = os.environ.get("OLLAMA_URL", DEFAULTS["OLLAMA_URL"])
    provider = os.environ.get("EMBED_PROVIDER", "ollama")
    default_model = (DEFAULTS["CF_EMBED_MODEL"] if provider == "cloudflare"
                     else DEFAULTS["EMBED_MODEL"])
    embed_model = os.environ.get("EMBED_MODEL", default_model)
    account_id = os.environ.get("CF_ACCOUNT_ID")
    api_token = os.environ.get("CF_API_TOKEN")
    # The index and the query path must agree on the model; print it so a
    # mismatched rebuild is visible in the log rather than only in eval scores.
    print(f"embedding with provider={provider} model={embed_model}")

    corpus_dir = Path(__file__).resolve().parent.parent / "data" / "corpus"
    corpus_files = sorted(corpus_dir.glob("*.json"))
    if not corpus_files:
        raise SystemExit(f"no corpus files found in {corpus_dir}")

    def embed(texts):
        return embed_texts(texts, model=embed_model, url=ollama_url,
                            provider=provider, account_id=account_id,
                            api_token=api_token)

    start = time.time()
    all_rows = []
    total_tokens = 0
    for path in corpus_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(f"chunking+embedding {path.name} ({len(payload['sections'])} sections)...")
        rows, tokens = chunks_to_rows(
            payload["sections"], payload["subpart"], payload["subpart_name"], embed=embed)
        all_rows.extend(rows)
        total_tokens += tokens
        print(f"  {len(rows)} chunks, {tokens} tokens "
              f"(running total: {len(all_rows)} chunks, {total_tokens} tokens)")

    print(f"upserting {len(all_rows)} rows into chunks...")
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            for i, row in enumerate(all_rows, 1):
                cur.execute(UPSERT_SQL, row[:6] + (_vector_literal(row[6]),))
                if i % 100 == 0 or i == len(all_rows):
                    print(f"  upserted {i}/{len(all_rows)}")

    elapsed = time.time() - start
    print(f"done in {elapsed:.1f}s. total chunks: {len(all_rows)}. total tokens: {total_tokens}")


if __name__ == "__main__":
    main()
