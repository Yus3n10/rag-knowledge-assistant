# RAG Knowledge Assistant (OSHA 29 CFR 1910)

Retrieval-augmented Q&A over OSHA general industry regulations, with
citation validation, hallucination checks, and role-based access control,
exposed over HTTP.

## Stack

- Postgres 16 + pgvector (Docker), 965 chunks embedded with `nomic-embed-text`
- Generation via `llama3.1:8b` (Ollama)
- FastAPI + Uvicorn, JWT auth (PyJWT), password hashing (Passlib/bcrypt)

## Running the API

Prerequisites: `docker compose up -d` (Postgres) and Ollama running locally
with `nomic-embed-text` and `llama3.1:8b` pulled.

```bash
pip install -r requirements.txt
python -m api.seed_users        # creates the two demo users, see below
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET  /health` -- liveness plus chunk count
- `POST /auth/login` -- `{"username", "password"}` -> `{"access_token", "token_type"}`
- `POST /ask` -- requires `Authorization: Bearer <token>`; `{"question"}` ->
  answer, citations, citation report, ungrounded numbers, generation stats,
  and `retrieved`: for each paragraph its id, distance, heading trail, and
  **source text**

Each `retrieved` entry's `text` joins *every* chunk of that paragraph, not
just the highest-ranked one. That matters: a paragraph can split into prose
and table chunks, and the answer sometimes lives only in the table. Showing
the first chunk alone would silently omit it.

An authenticated `/ask` takes roughly 8-12s warm (mostly `llama3.1:8b`
generation time); this is a known, accepted characteristic of the
synchronous design for this phase -- see the plan's "Measured inputs".

## Running the web interface

With the API already running on port 8000:

```bash
cd web
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
npm test -- --run    # component tests
```

Log in with either demo user, ask a question, and click any citation to
expand the exact regulation text that produced the claim. Paragraphs the
model cited are shown distinctly from paragraphs that were retrieved into
context but never cited -- the latter matters, because when the model
mis-attributes a claim, the correct source is often sitting in that list.

If the system detects numbers in an answer that do not appear in the
retrieved text, it says so in a warning banner rather than hiding it.

## Demo users

Seeded by `python -m api.seed_users`:

| username | password       | roles              |
|----------|----------------|--------------------|
| viewer   | `viewer-pass`  | (none)             |
| officer  | `officer-pass` | `safety_officer`   |

`JWT_SECRET` is read from the environment; if unset it falls back to an
obviously-a-dev value (`dev-secret-change-me-before-deploying-anywhere-real`)
defined in `api/auth.py`. Set a real `JWT_SECRET` before deploying anywhere
that matters.

## Role gating is synthetic

All OSHA 29 CFR text in this corpus is public domain -- none of it is
actually confidential. `db/002_access_control.sql` gates chunks under
`1910.147` (Lockout/Tagout) behind a `safety_officer` role purely to
**demonstrate that access control is enforced end to end**: the permission
check lives inside the retrieval SQL (`WHERE required_role IS NULL OR
required_role = ANY(roles)`), not filtered out of results after the fact,
and a caller's roles come only from their signed JWT -- the `/ask` request
body cannot claim roles for itself. This is not a real content-sensitivity
classification.

## Live verification (Phase 4a, Task 5)

Both demo users were logged in and asked the identical question whose
answer lives only in gated `1910.147` content:

> Who is allowed to remove a lockout device from an energy isolating device?

**viewer** (no roles) -- retrieved only `1910.137` (PPE) paragraphs, cited
nothing, and declined gracefully:

> "The provided text does not contain information about who is allowed to
> remove a lockout device from an energy isolating device."

No `1910.147` paragraph appeared anywhere in the viewer's `retrieved` list
or `citations` -- zero leakage of gated content.

**officer** (`safety_officer`) -- retrieved ten `1910.147` paragraphs and
answered correctly, with a valid citation:

> "According to [1910.147(e)(3)], each lockout or tagout device shall be
> removed from each energy isolating device by the employee who applied the
> device. However, if the authorized employee who applied the lockout or
> tagout device is not available, it may be removed under the direction of
> the employer, provided that specific procedures and training for such
> removal have been developed, documented and incorporated into the
> employer's energy control program."

Both requests returned `200` -- the ungated user got a graceful refusal, not
an error. Authenticated `/ask` latency: officer's request (warm model) took
11.4s wall / 8.2s generation; viewer's request included a 9.7s Ollama model
load, giving 21.0s wall / 13.7s generation. Full request/response bodies are
recorded in `.superpowers/sdd/p4a-task-345-report.md`.

## Testing

```bash
python -m pytest
```

All tests are hermetic -- `tests/test_auth.py` and `tests/test_api.py` stub
the DB connection, embedder, and generator, so the suite never touches
Postgres or Ollama.

## Live verification (Phase 4b, Task 4)

Same question, both demo users, against the running stack:

**`officer`** (role `safety_officer`) -- 10.0s

> According to [1910.147(e)(3)], each lockout or tagout device shall be
> removed from each energy isolating device by the employee who applied the
> device. However, if the authorized employee who applied it is unavailable...

Citations: `["1910.147(e)(3)"]`. All 10 retrieved paragraphs from `1910.147`.

**`viewer`** (no roles) -- 6.4s

> The provided text does not contain information about who is allowed to
> remove a lockout device from an energy isolating device.

Citations: `[]`. Zero retrieved paragraphs from `1910.147` -- retrieval drew
a full 10 results from `1910.137` instead.

The viewer receiving a *full* result set from permitted content, rather than
a truncated one, is the point: the permission predicate lives inside the
retrieval SQL (`WHERE required_role IS NULL OR required_role = ANY(...)`),
above `ORDER BY` and `LIMIT`. Filtering after the query would have returned
fewer results with no signal that anything was withheld.
