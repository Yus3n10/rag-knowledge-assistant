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
  answer, citations, citation report, ungrounded numbers, retrieved
  paragraph ids with distances, and generation stats

An authenticated `/ask` takes roughly 8-12s warm (mostly `llama3.1:8b`
generation time); this is a known, accepted characteristic of the
synchronous design for this phase -- see the plan's "Measured inputs".

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
