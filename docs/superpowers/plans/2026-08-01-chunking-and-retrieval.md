# Phase 2: Chunking, Embeddings, and Retrieval Metrics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 937-paragraph OSHA corpus into a searchable vector index, and produce the first real retrieval scores against the 45-question eval set.

**Architecture:** Corpus paragraphs become chunks (paragraph text prefixed with its heading trail, tables appended). Chunks are embedded via Ollama and stored in Postgres + pgvector, both running in Docker. A retriever fetches top-k by cosine distance. An eval runner scores retrieval on three separate metrics and writes a timestamped result.

**Tech Stack:** Python 3.11, Ollama (`nomic-embed-text`), Postgres 16 + pgvector (Docker), `psycopg`, `requests`, `pytest`.

## Global Constraints

- Python 3.11+, Windows, no WSL. Use `python -m pytest`, never bare `pytest`.
- **Dependency budget changes this phase.** Phase 1 held to `requests`, `beautifulsoup4`, `pytest`. Phase 2 adds exactly one runtime dependency: `psycopg[binary]`. Embeddings go through Ollama's HTTP API using `requests` — **do not** add `sentence-transformers`, `torch`, `numpy`, `langchain`, or `llama-index`. Reusing the HTTP surface already needed for generation is the reason this stays at one new dependency.
- `data/raw/` and `data/corpus/` are committed and **final**. Do not re-scrape, do not regenerate, do not modify.
- `eval/questions.jsonl` is **final**. 45 hand-verified questions. Do not add, remove, or edit questions to improve a score. If a question looks wrong, stop and report it.
- Commit messages carry NO AI/Claude/Anthropic attribution and NO Co-Authored-By trailer.
- Everything must run offline once the model is pulled and the container is up. No hosted API calls in this phase.

## Metric definitions (settled — implement exactly)

The eval set has three structurally different question types. One averaged number would corrupt all three, so three metrics are reported.

| Metric | Scored over | Definition |
|---|---|---|
| **Per-paragraph recall@k** (headline) | the 38 answerable questions | For each question, `(required paragraphs retrieved) / (required paragraphs)`. **Macro-average**: average those 38 fractions with equal weight per question. |
| **Strict completeness@k** | the 6 multi-paragraph questions | Fraction of those 6 for which **every** required paragraph appears in top-k. |
| **Refusal accuracy** | the 7 negative questions | Did the system decline rather than confabulate. **Measured by hand**, see below. |

**Macro, not micro — this is load-bearing.** Pooling all 55 required-paragraph instances and computing one global fraction (micro-average) would give the 6 multi-paragraph questions 23 of 55 instances — 42% of the weight from 16% of the questions. The headline number would silently become a multi-paragraph score. Macro-averaging gives every question one equal vote, keeping per-paragraph recall genuinely general-purpose and leaving strict completeness as the metric deliberately allowed to weight multi-paragraph difficulty. Two metrics doing two distinct jobs.

**Refusal accuracy is hand-measured, and that is a deliberate choice, not a deferral.** Recall and completeness are mechanical set-membership checks against `expected_citation` — deterministic, no judgment. Classifying an answer as refusal-vs-confabulation is a text-understanding judgment with no citation to check against. Building an LLM-as-judge for exactly 7 questions would add a dependency plus its own reliability question. At N=7, hand-reviewing each run is cheaper and more trustworthy. The eval runner therefore **prints the 7 negative questions' retrieved chunks for human review and records a manually-entered score** — it does not silently skip them or auto-pass them.

Note: negatives still exercise retrieval (the corpus contains lexical distractors for all 7 — see their `notes`). Retrieval will return *something* for every negative. That is expected and is the point: the test is whether the downstream answer declines anyway.

---

## Task 0: Verify the environment before writing code

**Files:** none (verification only)

Do not assume Ollama or Docker are installed and working. Every later task depends on both.

- [ ] **Step 1: Check Docker**

Run: `docker --version` and `docker ps`
Expected: a version string, and a container table (possibly empty) without a daemon error.
If Docker Desktop is not installed or the daemon is not running, **STOP and report** — do not attempt to install it unattended.

- [ ] **Step 2: Check Ollama and pull the embedding model**

Run: `ollama --version`, then `ollama pull nomic-embed-text`
Expected: version string; pull completes (~274MB).
If Ollama is not installed, **STOP and report**.

- [ ] **Step 3: Determine the embeddings API shape — do not guess**

Ollama changed its embeddings endpoint across versions: older builds use `POST /api/embeddings` with `{"model": ..., "prompt": ...}` returning `{"embedding": [...]}`; newer builds use `POST /api/embed` with `{"model": ..., "input": ...}` returning `{"embeddings": [[...]]}`. Both may be present.

Probe the installed version directly:

```bash
curl -s http://localhost:11434/api/embed -d '{"model":"nomic-embed-text","input":"lockout device removal"}'
curl -s http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"lockout device removal"}'
```

Record which endpoint responds, the exact response key, and the **vector length**. Report all three — Task 3 and the database schema both depend on them. `nomic-embed-text` is expected to be 768 dimensions; confirm rather than assume.

- [ ] **Step 4: Report findings, do not commit**

Report: Docker version, Ollama version, working endpoint, response key, embedding dimension.

---

## Task 1: Chunker

**Files:**
- Create: `scripts/rag/chunk.py`
- Test: `tests/test_chunk.py`

**Interfaces:**
- Consumes: corpus JSON records `{paragraph_id, text, tables[], parent_headings[]}`
- Produces: `chunk_records(section, subpart, subpart_name) -> list[dict]` where each dict is
  `{chunk_id, paragraph_id, section_id, subpart, heading_trail, text}`.
  `chunk_id` is `paragraph_id` for unsplit paragraphs, `f"{paragraph_id}#{n}"` for splits.

**Design (settled):**
- One chunk per paragraph. Paragraph IDs are already real regulatory citations — keep them as the retrieval unit so citations stay exact.
- Chunk text = heading trail + content. The trail gives a 127-character median paragraph enough context to embed meaningfully; this is what `parent_headings` exists for.
- Every chunk carries `kind`: `"prose"` or `"table"`. Diagnostic, and needed by Task 7's `resp-001` check.

**Rule 1 — definition-aware splitting, both formats.** The corpus uses two definition styles and a single pattern covers neither alone:
- `Term means ...` — `1910.21(b)` (60 occurrences), `1910.134(b)` (35), `1910.140(b)` (28)
- `Term . Definition` — `1910.147(b)`. It contains 3 occurrences of "means", all ordinary usage ("a positive means such as a lock", "a means of attachment"), **zero** in `Term means` form. A means-based pattern fixes nothing here.

Split definitions-style paragraphs before each defined term under either format. Verified defects this fixes: `1910.21(b)` piece 4 opens mid-"Rope descent system"; `1910.147(b)` pieces 1 and 2 open mid-"Hot tap" and mid-"Tagout device".

**Rule 2 — tables are atomic, ONE CHUNK PER TABLE.** Never split inside a markdown table. `1910.137(c)(2)(xii)` currently severs a voltage-rating table so one chunk holds rows with no header — actively misleading, not merely unhelpful.

Emit **one chunk per table**, not one chunk holding all of a paragraph's tables. `1910.137(c)(2)(xii)` carries five separate tables; bundling them fixes the header severing but creates a precision problem underneath it, since a query about Class 2 glove proof-test voltage would retrieve the same undifferentiated chunk as rubber-sleeve retest scheduling. One chunk per retrievable unit.

- Oversized prose splits on sentence boundaries with the heading trail repeated on each part.

- [ ] **Step 1: Write the failing tests**

```python
from scripts.rag.chunk import chunk_records

SECTION = {
    "section_id": "1910.147",
    "section_heading": "The control of hazardous energy (lockout/tagout).",
    "records": [
        {"paragraph_id": "1910.147(e)(3)", "text": "Each device shall be removed by the employee who applied it.",
         "tables": [], "parent_headings": [{"paragraph_id": "1910.147(e)", "text": "Release from lockout or tagout."}]},
        {"paragraph_id": "1910.147(x)", "text": "Table paragraph.",
         "tables": ["| Type | APF |\n| --- | --- |\n| Full facepiece | 50 |"], "parent_headings": []},
    ],
}


def test_chunk_text_carries_the_heading_trail():
    chunks = chunk_records(SECTION, "Subpart J", "General Environmental Controls")

    first = chunks[0]
    assert first["chunk_id"] == "1910.147(e)(3)"
    assert "The control of hazardous energy" in first["text"]
    assert "Release from lockout or tagout." in first["text"]
    assert "removed by the employee who applied it" in first["text"]


def test_table_content_is_appended_to_its_paragraph_chunk():
    chunks = chunk_records(SECTION, "Subpart J", "General Environmental Controls")

    table_chunk = [c for c in chunks if c["paragraph_id"] == "1910.147(x)"][0]
    # the APF value lives only in the table; it must survive into the chunk text
    assert "50" in table_chunk["text"]
    assert "Full facepiece" in table_chunk["text"]


def test_oversized_paragraph_splits_with_the_trail_repeated():
    big = {
        "section_id": "1910.140",
        "section_heading": "Personal fall protection systems.",
        "records": [{"paragraph_id": "1910.140(b)", "tables": [], "parent_headings": [],
                     "text": " ".join(f"Term{i} means definition number {i}." for i in range(400))}],
    }

    chunks = chunk_records(big, "Subpart I", "Personal Protective Equipment")

    assert len(chunks) > 1
    assert [c["chunk_id"] for c in chunks] == [f"1910.140(b)#{i}" for i in range(len(chunks))]
    assert all("Personal fall protection systems." in c["text"] for c in chunks)
    assert all(c["paragraph_id"] == "1910.140(b)" for c in chunks)
    assert all(len(c["text"]) <= 2400 for c in chunks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_chunk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.rag.chunk'`

- [ ] **Step 3: Implement**

Create `scripts/rag/__init__.py` (empty) and `scripts/rag/chunk.py`:

```python
"""Turn corpus paragraphs into embeddable chunks."""

import re

MAX_CHARS = 2000
SENTENCE_END = re.compile(r"(?<=[.;:])\s+")


def heading_trail(section, record):
    """Readable ancestry: section heading then each parent paragraph's text."""
    parts = [f"{section['section_id']} {section['section_heading']}"]
    for parent in record.get("parent_headings", []):
        parts.append(parent["text"])
    return " > ".join(parts)


def split_text(text, budget):
    """Split on sentence boundaries into pieces no longer than budget."""
    if len(text) <= budget:
        return [text]
    pieces, current = [], ""
    for sentence in SENTENCE_END.split(text):
        if current and len(current) + 1 + len(sentence) > budget:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_records(section, subpart, subpart_name):
    chunks = []
    for record in section["records"]:
        trail = heading_trail(section, record)
        body = " ".join([record["text"]] + record.get("tables", []))
        budget = MAX_CHARS - len(trail) - 2
        pieces = split_text(body, budget)
        for n, piece in enumerate(pieces):
            chunk_id = record["paragraph_id"] if len(pieces) == 1 else f"{record['paragraph_id']}#{n}"
            chunks.append({
                "chunk_id": chunk_id,
                "paragraph_id": record["paragraph_id"],
                "section_id": section["section_id"],
                "subpart": subpart,
                "heading_trail": trail,
                "text": f"{trail}\n\n{piece}",
            })
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chunk.py -v`
Expected: 3 passed

- [ ] **Step 5: Sanity-check against the real corpus**

Run a throwaway script that chunks all three corpus files and prints: total chunks, how many paragraphs split, the largest chunk length, and the chunk containing `1910.134(d)(3)(i)(A)`. Confirm that last one contains the string `50`. Report the numbers.

- [ ] **Step 5b: Hand-check the definitions-blob splits — this has no automated tripwire**

`resp-001` exists so a bad table-append decision fails loudly in Task 7. **The definitions-blob split has no equivalent.** Zero of the 45 eval questions cite `1910.140(b)` or `1910.21(b)`, and the eval set is locked at 45 — a 46th question cannot be added to cover it. So this check is manual, by the same hand-verification discipline used throughout the project.

Check **every paragraph that splits into more than one chunk**, not a named list. An earlier version of this step named only `1910.140(b)` and `1910.21(b)` — following it literally missed `1910.147(b)` and `1910.137(c)(2)(xii)` entirely, because neither is a "definitions blob" under the name the step used. The generalization is the point: audit what the code actually splits, not what you remember being large.

Using the same throwaway script, print every piece of every multi-chunk paragraph and read the boundaries. Confirm no cut lands mid-definition — each piece should start at a defined term (`X means ...`), not partway through one. Report the piece count for each blob and quote the first 80 characters of each piece so the boundaries can be eyeballed.

If cuts land mid-definition, say so rather than proceeding — splitting on defined-term boundaries instead of sentence boundaries is the fix, and it is cheaper now than after the index is built. Delete the script afterwards.

- [ ] **Step 6: Commit**

```bash
git add scripts/rag/ tests/test_chunk.py
git commit -m "feat: chunk corpus paragraphs with heading trails and appended tables"
```

---

## Task 2: Postgres + pgvector in Docker

**Files:**
- Create: `docker-compose.yml`
- Create: `db/schema.sql`
- Create: `.env.example`

**Design (settled):** Docker Desktop locally, the same `pgvector/pgvector` image on the Oracle free-tier VM. Not a stand-in for production — the identical artifact runs in both places, which is what keeps dev and deploy honest. Compiling pgvector natively on Windows is real pain for no benefit.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: ragdev
      POSTGRES_DB: rag
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/schema.sql
volumes:
  pgdata:
```

Port 5433 on the host avoids colliding with any local Postgres on 5432.

- [ ] **Step 2: Write `db/schema.sql`**

Use the embedding dimension confirmed in Task 0 Step 3 in place of `768` if it differs.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    chunk_id      TEXT PRIMARY KEY,
    paragraph_id  TEXT NOT NULL,
    section_id    TEXT NOT NULL,
    subpart       TEXT NOT NULL,
    heading_trail TEXT NOT NULL,
    text          TEXT NOT NULL,
    embedding     vector(768)
);

CREATE INDEX chunks_paragraph_id_idx ON chunks (paragraph_id);
```

No vector index yet. At ~1000 chunks an exact scan is fast and always correct; an approximate index (HNSW/IVFFlat) trades recall for speed and would confound the first measurements. Add one only when measured latency justifies it — and re-run the eval after, because it can change the score.

- [ ] **Step 3: Write `.env.example`**

```
DATABASE_URL=postgresql://rag:ragdev@localhost:5433/rag
OLLAMA_URL=http://localhost:11434
EMBED_MODEL=nomic-embed-text
```

- [ ] **Step 4: Bring it up and verify**

Run: `docker compose up -d`, then
`docker compose exec db psql -U rag -d rag -c "\dx"` and
`docker compose exec db psql -U rag -d rag -c "\d chunks"`
Expected: `vector` extension listed; `chunks` table with an `embedding` column of type `vector(768)`.

- [ ] **Step 5: Add `.env` to `.gitignore` and commit**

Append `.env` to `.gitignore`. **Do not gitignore `data/`.**

```bash
git add docker-compose.yml db/schema.sql .env.example .gitignore
git commit -m "feat: add Postgres with pgvector via Docker Compose"
```

---

## Task 3: Ollama embedding client

**Files:**
- Create: `scripts/rag/embed.py`
- Test: `tests/test_embed.py`

**Interfaces:**
- Produces: `embed_texts(texts, *, model, url, session=None, batch_size=32) -> list[list[float]]`
- Produces: `embed_texts` also returns token accounting — signature is
  `embed_texts(...) -> tuple[list[list[float]], int]` where the int is summed `prompt_eval_count`.

**Task 0 findings — these are measured, not assumed:**

| Finding | Value |
|---|---|
| Ollama version | 0.32.5 |
| Working endpoint | `POST /api/embed` (newer shape). Legacy `/api/embeddings` also responds. |
| Request | `{"model": ..., "input": [...]}` — **accepts a list** |
| Response | `{"embeddings": [[...]], "prompt_eval_count": N}` |
| Embedding dimension | **768** — matches the schema's `vector(768)` |
| Model context length | 2048 tokens (≈8000 chars), so `MAX_CHARS = 2000` is comfortably within |

**Batch, don't loop.** `/api/embed` accepts a list of inputs and returns one vector per input. Embedding ~1000 chunks one request at a time is ~1000 round trips; batching at 32 is ~32. Use `batch_size=32` and preserve input order in the returned list — a reordering bug here would silently attach every chunk to the wrong vector, which no test downstream would obviously catch. Add a test that pins order across a batch boundary.

**Capture `prompt_eval_count`.** Ollama returns token counts per request for free. The Phase 3 cost/latency dashboard needs exactly this, and threading it through now costs one return value versus retrofitting it through every call site later.

Follow the Phase 1 fetch-layer pattern: accept an injectable `session` so tests run with zero network.

- [ ] **Step 1: Write the failing tests**

```python
from scripts.rag.embed import embed_texts


class StubSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))

        class R:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"embeddings": [[0.1, 0.2, 0.3]]}
        return R()


def test_embeds_each_text_and_returns_vectors():
    session = StubSession()

    vectors = embed_texts(["lockout device removal"], model="nomic-embed-text",
                          url="http://localhost:11434", session=session)

    assert vectors == [[0.1, 0.2, 0.3]]
    assert session.calls[0][1]["model"] == "nomic-embed-text"


def test_rejects_an_empty_batch_rather_than_calling_the_api():
    session = StubSession()

    vectors = embed_texts([], model="nomic-embed-text",
                          url="http://localhost:11434", session=session)

    assert vectors == []
    assert session.calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_embed.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `scripts/rag/embed.py`**

One text per request, returning a list of vectors. Raise on a dimension mismatch between vectors in the same run — a silent dimension change would corrupt the index in a way that surfaces much later as bad retrieval.

- [ ] **Step 4: Run tests, then smoke-test against real Ollama**

Run: `python -m pytest tests/test_embed.py -v` (expect 2 passed), then embed one real string and print the vector length. Confirm it matches the schema's dimension.

- [ ] **Step 5: Commit**

```bash
git add scripts/rag/embed.py tests/test_embed.py requirements.txt
git commit -m "feat: add Ollama embedding client"
```

---

## Task 4: Build the index

**Files:**
- Create: `scripts/build_index.py`
- Test: `tests/test_build_index.py`

Chunk all three corpus files, embed every chunk, upsert into `chunks`. Idempotent — re-running replaces rather than duplicating. Print progress; ~1000 embeddings takes a few minutes locally.

- [ ] **Step 1: Write a failing test** for the chunk-to-row mapping using a stub embedder and an in-memory list instead of a live database, so the test needs neither Docker nor Ollama.
- [ ] **Step 2: Run it, watch it fail.**
- [ ] **Step 3: Implement**, using `psycopg` with `ON CONFLICT (chunk_id) DO UPDATE`.
- [ ] **Step 4: Run tests, then run for real** against the live container.
- [ ] **Step 5: Verify in SQL:** `SELECT count(*) FROM chunks;` and `SELECT count(*) FROM chunks WHERE embedding IS NULL;` — the second must be 0. Report both numbers.
- [ ] **Step 6: Commit.**

---

## Task 5: Retriever

**Files:**
- Create: `scripts/rag/retrieve.py`
- Test: `tests/test_retrieve.py`

**Interfaces:**
- Produces: `search(query, *, k=5, conn, embedder) -> list[dict]` returning chunks ordered by ascending cosine distance, each with `chunk_id`, `paragraph_id`, `text`, `distance`.

Use `<=>` (cosine distance) — the standard pairing for `nomic-embed-text`.

The `WHERE` clause stays empty for now, but write the query so a permission filter can be added to it later rather than applied to the result list. Filtering after retrieval silently returns fewer, worse results with no signal that anything was withheld.

- [ ] **Step 1–4:** failing test with a stub connection, watch it fail, implement, pass.
- [ ] **Step 5: Manual sanity check.** Search `"who is allowed to remove a lockout device"` and confirm `1910.147(e)(3)` is in the top 3. Report the top 5 with distances. This is the first evidence that meaning-based search beats keyword search on this corpus — a Ctrl+F for that phrasing finds nothing.
- [ ] **Step 6: Commit.**

---

## Task 6: Metrics

**Files:**
- Create: `eval/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- `required_paragraphs(question) -> list[str]` — `[]` for negatives, else the one or many cited IDs
- `per_paragraph_recall(questions, retrieved_by_qid, k) -> float` — macro-averaged over answerable questions
- `strict_completeness(questions, retrieved_by_qid, k) -> float` — over multi-paragraph questions only

`retrieved_by_qid` maps question id to an ordered list of retrieved **paragraph** ids (map chunk ids back to paragraph ids first — a split paragraph's `#0`/`#1` chunks both count as their parent paragraph, and deduplicate before truncating to k).

- [ ] **Step 1: Write the failing tests — these must pin the macro/micro distinction explicitly**

```python
from eval.metrics import per_paragraph_recall, strict_completeness, required_paragraphs


def q(qid, category, **cite):
    return {"id": qid, "category": category, "expected_citation": cite or None}


def test_negative_questions_have_no_required_paragraphs():
    assert required_paragraphs({"id": "n1", "category": "negative",
                                "expected_citation": None}) == []


def test_recall_is_macro_averaged_not_micro_averaged():
    # one single-gold question, fully hit; one five-gold question, one of five hit.
    questions = [
        q("single", "numeric_lookup", paragraph_id="A"),
        q("multi", "procedural", paragraph_ids=["B", "C", "D", "E", "F"]),
    ]
    retrieved = {"single": ["A"], "multi": ["B"]}

    # macro: (1.0 + 0.2) / 2 = 0.6
    # micro would be 2 hits / 6 golds = 0.333 - this test fails under micro
    assert per_paragraph_recall(questions, retrieved, k=5) == 0.6


def test_negatives_are_excluded_from_recall_not_scored_as_zero():
    questions = [
        q("single", "numeric_lookup", paragraph_id="A"),
        {"id": "neg", "category": "negative", "expected_citation": None},
    ]
    retrieved = {"single": ["A"], "neg": ["Z"]}

    assert per_paragraph_recall(questions, retrieved, k=5) == 1.0


def test_strict_completeness_requires_every_gold_and_ignores_single_gold_questions():
    questions = [
        q("single", "numeric_lookup", paragraph_id="A"),
        q("m1", "procedural", paragraph_ids=["B", "C"]),
        q("m2", "conditional", paragraph_ids=["D", "E"]),
    ]
    retrieved = {"single": ["A"], "m1": ["B", "C"], "m2": ["D", "X"]}

    assert strict_completeness(questions, retrieved, k=5) == 0.5


def test_recall_only_counts_the_first_k_retrieved():
    questions = [q("single", "numeric_lookup", paragraph_id="A")]

    assert per_paragraph_recall(questions, {"single": ["X", "Y", "Z", "W", "V", "A"]}, k=5) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run tests to verify they pass** — expect 5 passed.
- [ ] **Step 5: Commit.**

---

## Task 7: Eval runner

**Files:**
- Create: `eval/run_eval.py`
- Create: `eval/results/` (committed, holds timestamped JSON results)

Runs all 45 questions through retrieval, computes the three metrics, prints a report, and appends a timestamped result to `eval/results/`.

- [ ] **Step 1: Implement.** Output shape:

```
Per-paragraph recall@5 (macro, 38 answerable) : 0.__
Strict completeness@5  (6 multi-paragraph)    : 0.__
Refusal accuracy       (7 negatives)          : PENDING HAND REVIEW

Weakest questions:
  <qid>  <category>  recall 0.00  missed: <paragraph ids>

Negative questions - retrieved chunks for hand review:
  <qid>  <question>
     1. <paragraph_id>  distance <d>
     ...
```

- [ ] **Step 2:** Save results as JSON with a timestamp, the k used, the embedding model, per-question recall, and a null `refusal_accuracy` field to be filled in after hand review. Never auto-fill it.
- [ ] **Step 3: Run it.** Report all three numbers and the weakest questions.
- [ ] **Step 4: Check `resp-001` specifically — assert on the retrieved TEXT, not the paragraph id.**

Its answer (APF 50) exists only in `1910.134(d)(3)(i)(A)`'s table. Under Rule 2 that paragraph produces **three** chunks — one table and two prose — and all three map back to the same paragraph id. Measured: `"50"` appears in the table chunk only, in neither prose chunk. So paragraph-level scoring reports a full hit when only a **prose** chunk ("Employers must use the assigned protection factors listed in Table 1…") was retrieved, even though the number 50 never was. The canary would pass green having caught nothing.

`resp-001` is the only one of the 45 questions whose cited paragraph splits into multiple chunks — verified against all 45 citations — so this is an isolated case warranting a targeted assertion, not a redesign of per-paragraph recall. Paragraph-level granularity remains correct for the other 44.

Assert that the concatenated text of `resp-001`'s retrieved chunks contains `50`, and report the `kind` of each retrieved chunk. If the table chunk is not retrieved, **report that rather than working around it** — it means table content is not reachable by a natural-language query about its subject, which is exactly the failure this question was planted to expose.
- [ ] **Step 5: Commit** the runner and the first result file.

---

## Expectations

The first score will probably be mediocre. That is the harness working — it is reporting the truth about an untuned pipeline, which is the entire reason it was built before the pipeline was.

Do not tune by editing questions, loosening a metric, or excluding hard cases. Tune the pipeline: chunk size, whether the heading trail helps or dilutes, k, the embedding model. Re-run after each change and keep the timestamped results — the trend line is the deliverable, not any single number.

**If `strict_completeness@k` comes back weak, check this first — it is a known concrete risk, not a guess.** `1910.147(f)(1)(iii)` (and its four siblings) carry a `parent_headings` trail containing `(f)(1)`'s full ~230-character sentence: *"Testing or positioning of machines... the following sequence of actions shall be followed:"*. All five LOTO release-sequence steps therefore embed with a near-identical several-hundred-character shared prefix, while each step's own distinctive content is a ten-word imperative (*"Clear the machine..."*, *"Remove employees..."*). Those five paragraphs are exactly the golds behind `loto-010`, the hardest multi-paragraph question in the set.

If that is the failure, the fix to test is truncating or omitting long parent sentences from the trail (keep the section heading and short parent headings, drop parents over ~100 characters) — and re-run, rather than assuming the trail is helping because it seemed reasonable.
