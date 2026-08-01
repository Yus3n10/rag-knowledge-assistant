# Phase 4a: API and Role-Based Access Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expose the working RAG pipeline over HTTP with authentication and genuine document-level access control, so it is a service rather than a script.

**Architecture:** FastAPI wraps the existing `answer_question` pipeline. JWT carries the caller's roles. Document visibility is enforced **inside the retrieval SQL**, not filtered afterwards — so top-k always means "top-k among what this caller may see."

**Tech Stack:** FastAPI, Uvicorn, PyJWT, Passlib (bcrypt), plus the existing Postgres + pgvector and Ollama stack.

**Not in this phase:** React frontend (4b), Oracle Cloud deploy and CI (4c), Grafana (4d), reranking (deferred — see `docs/RETRIEVAL_FINDINGS.md`).

## Global Constraints

- Python 3.11+, Windows, no WSL. `python -m pytest`, never bare `pytest`.
- **New dependencies permitted, and only these:** `fastapi`, `uvicorn[standard]`, `pyjwt`, `passlib[bcrypt]`, `httpx` (test client). Nothing else — no `langchain`, no ORM, no `sqlmodel`. The project already talks to Postgres with raw `psycopg` and that stays.
- **Do not hand-roll auth primitives.** Use PyJWT for tokens and Passlib for password hashing. The plan's own non-goals say this project is not about proving you can write crypto, and hand-rolled auth is where security bugs live.
- `eval/questions.jsonl`, `data/`, and every existing `scripts/rag/*` module are unchanged unless a task says otherwise.
- Commit messages carry NO AI/Claude/Anthropic attribution and NO Co-Authored-By trailer.
- Never commit real secrets. `JWT_SECRET` comes from the environment with a development default that is obviously a dev value.

## Measured inputs — do not re-derive

| Fact | Value |
|---|---|
| Generation context k | **10** (measured knee, `docs/RETRIEVAL_FINDINGS.md`) |
| Warm latency | ~5s per question at ~1,100 prompt tokens |
| Pipeline entry point | `scripts/rag/answer.py::answer_question(question, *, k, conn, embedder, generator, corpus_paragraph_ids)` |
| Index | 965 chunks, `chunks` table, host port 5433 |

An answer takes ~5 seconds. That is slow for a synchronous HTTP request but acceptable for this phase; do **not** add a task queue, websockets, or streaming. Note it in the README as a known characteristic and revisit only if the frontend demands it.

---

## Task 1: Access-control schema

**Files:** `db/002_access_control.sql`, `tests/test_access_control_schema.py`

Add to the database:
- `users(id, username UNIQUE, password_hash, roles TEXT[])`
- `chunks.required_role TEXT` — nullable; `NULL` means public

Backfill every existing chunk to `NULL` (all OSHA text is public). Then mark a **small, clearly labelled** subset as role-gated so access control is demonstrably real rather than theoretical — e.g. gate `1910.147` chunks behind role `safety_officer`.

**This gating is synthetic and must be labelled as such** in the README and in the migration's own comment. OSHA text is public domain; pretending otherwise would misrepresent the corpus. The purpose is to demonstrate enforcement, not to model a real classification.

- [ ] Write the migration; apply it to the running container.
- [ ] Verify with SQL: total chunks unchanged at 965; count of gated chunks matches expectation; `users` table exists.
- [ ] Commit.

## Task 2: Permission-aware retrieval

**Files:** modify `scripts/rag/retrieve.py`, `tests/test_retrieve.py`

`search(query, *, k, conn, embedder, roles=None)` — add the `WHERE` clause the existing comment already anticipates:

```sql
WHERE required_role IS NULL OR required_role = ANY(%s)
```

**The filter goes in the query, never in Python afterwards.** Post-filtering returns fewer than k results with no signal that anything was withheld, silently degrading answers for gated users. This is the single most important correctness property in this phase.

- [ ] TDD: a caller without the role gets zero gated chunks; a caller with it gets them; `roles=None` behaves as "public only"; the returned count is still k when enough permitted chunks exist.
- [ ] **Regression check:** re-run `python -m eval.run_eval` with full roles. Recall@10 must still be 0.987 — if it moved, the filter changed behaviour for public content, which is a bug.
- [ ] Commit.

## Task 3: Auth

**Files:** `api/auth.py`, `tests/test_auth.py`

- `hash_password` / `verify_password` via Passlib bcrypt
- `create_token(username, roles)` / `decode_token(token)` via PyJWT, HS256, with an expiry claim
- A seed script creating two demo users: one plain (`viewer`, no roles) and one with `safety_officer`

- [ ] TDD: a valid token round-trips; an expired token is rejected; a token signed with the wrong secret is rejected; a tampered payload is rejected.
- [ ] Commit.

## Task 4: The API

**Files:** `api/main.py`, `tests/test_api.py`

Endpoints:
- `POST /auth/login` — username + password, returns a token
- `POST /ask` — authenticated; body `{question}`; returns answer, citations, citation report, ungrounded numbers, retrieved paragraph ids with distances, and stats
- `GET /health` — liveness plus chunk count

`/ask` calls `answer_question` with the caller's roles threaded through to retrieval.

- [ ] TDD with FastAPI's `TestClient` and stubbed embedder/generator — no Ollama, no Postgres, in tests.
- [ ] Assert: `/ask` without a token is 401; with a valid token is 200; a `viewer` asking a question whose only answer is gated gets an answer that does not cite gated paragraphs.
- [ ] **That last test is the point of the whole phase** — it proves access control reaches the answer, not just the endpoint.
- [ ] Commit.

## Task 5: Live verification

**Files:** none (verification), plus README updates

- [ ] Run the API for real against live Postgres and Ollama.
- [ ] Log in as `viewer` and as `safety_officer`, ask **the same question** whose answer lives in gated `1910.147` content, and paste both full responses. The difference between them is the deliverable.
- [ ] Confirm the gated user's answer cites gated paragraphs and the ungated user's does not — and that the ungated user gets a graceful answer or refusal rather than an error.
- [ ] Record latency for an authenticated `/ask`.
- [ ] Update the README: how to run, the two demo users, and an explicit note that the role gating is synthetic because OSHA text is public domain.
- [ ] Commit.

---

## Expectations

The interesting failure here is not a 500. It is a `viewer` receiving an answer built from paragraphs they should not see, or receiving a silently worse answer with no indication anything was withheld. Task 4's final test and Task 5's side-by-side exist specifically to catch both.

Do not weaken the eval to accommodate access control. The regression check in Task 2 runs with full roles precisely so that public retrieval quality stays comparable to Phase 2's numbers.
