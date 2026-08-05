# Phase 4d: Cost and Latency Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Every answered question records what it cost and how long it took, and a Grafana dashboard shows those numbers over time.

**Architecture:** `/ask` writes one row per request into a Postgres table. Grafana reads that table directly as a Postgres datasource. **No Prometheus** — Postgres is already running, Grafana speaks to it natively, and that is one container instead of two.

## Why not Prometheus

Prometheus is a time-series store built for scraping many hosts and aggregating on ingest. Here there is one service, request volume is tens per day, and the interesting questions are per-request ("what did *that* question cost?") rather than aggregate rates. A row per request in Postgres answers both the aggregate and the per-request question; a scrape endpoint answers only the aggregate, having thrown the individual rows away.

If request volume ever reaches the point where per-row storage hurts, that is the moment to add Prometheus — not before.

## Global Constraints

- **No new Python dependencies.** Writing one row uses the `psycopg` connection `/ask` already holds.
- Grafana runs as a container from the official image. The dashboard is **provisioned as code** — a JSON file in the repo, loaded at container start. A hand-clicked dashboard that lives only in Grafana's own volume is not reproducible and disappears with the volume.
- **Never invent a dollar figure.** Record tokens, which are measured. Derive cost from a rate table that is explicit, versioned, and obviously editable. A hardcoded price that silently goes stale is worse than no price.
- Recording a request must **never break answering one.** If the insert fails, log it and still return the answer.
- `data/` stays committed. Commit messages carry NO AI/Claude/Anthropic attribution and NO Co-Authored-By trailer.

## Measured inputs

| Fact | Value |
|---|---|
| Python tests | 161, hermetic |
| Frontend tests | 16 |
| Local warm `/ask` | ~8-12s with `llama3.1:8b` |
| Context at k=10 | ~1,066 prompt tokens |
| `stats` contract | `prompt_tokens`, `completion_tokens`, `latency_s`, `load_duration_s` — identical across the ollama and groq providers (asserted by test) |

That stats contract is what makes this phase cheap: both providers already return the same four keys, so recording is provider-agnostic and a provider switch shows up as a visible step in the same chart rather than breaking it.

---

## Task 1: Request log

**Files:** `db/003_request_log.sql`, `scripts/rag/requestlog.py`, tests

Table `request_log`:

| column | why |
|---|---|
| `id`, `asked_at` | ordering |
| `question` | which question was expensive |
| `username`, `roles` | who asked — ties cost to the RBAC work |
| `provider`, `model` | so a provider switch is legible in the chart |
| `prompt_tokens`, `completion_tokens`, `latency_s` | the measured facts |
| `citation_count`, `ungrounded_number_count`, `refused` | quality alongside cost |
| `k` | the retrieval setting in force |

Recording quality next to cost is the point. A dashboard showing only latency and tokens cannot answer the question that actually matters — *"is the cheaper provider also the worse one?"*

- [ ] `record_request(conn, **fields)` — one insert, no ORM.
- [ ] **Failure must not propagate.** Wrap the insert; on error log and continue. A dashboard outage must never become an API outage.
- [ ] TDD with a stub connection, including the failure path: assert a raising connection does not raise out of `record_request`.
- [ ] Apply the migration to the running container (do NOT `down -v` — that destroys the 965 embeddings).
- [ ] Commit.

## Task 2: Wire it into `/ask`

**Files:** `api/main.py`, `tests/test_api.py`

- [ ] After `answer_question` returns, record the row. Derive `refused` from an empty citation list plus the refusal phrasing already used in `prompt.py` — do not invent a second definition of refusal.
- [ ] TDD: a successful `/ask` records exactly one row; **a failing recorder still returns 200 with the answer.**
- [ ] Commit.

## Task 3: Cost model

**Files:** `scripts/rag/cost.py`, tests

- [ ] A module-level rate table: dollars per million prompt tokens and per million completion tokens, keyed by `(provider, model)`. Ollama is `0.0` — local inference has no marginal token cost.
- [ ] `cost_usd(provider, model, prompt_tokens, completion_tokens) -> float`.
- [ ] **An unknown model returns `None`, not `0.0`.** Silently pricing an unknown model at zero is how a dashboard lies. `None` renders as "unpriced" and is honest.
- [ ] A comment stating where the rates came from and when they were checked.
- [ ] TDD including the unknown-model case.
- [ ] Commit.

## Task 4: Grafana

**Files:** `docker-compose.yml`, `grafana/provisioning/datasources/postgres.yml`, `grafana/provisioning/dashboards/*.json`

- [ ] Grafana container, official image, Postgres datasource provisioned from a file. Credentials from the environment — no password in the repo.
- [ ] Dashboard JSON in the repo, auto-loaded at start. Panels:
  - requests over time
  - p50 / p95 latency
  - tokens per request
  - **cumulative cost**, with unpriced requests visibly excluded rather than counted as zero
  - **refusal rate and ungrounded-number rate** alongside cost
- [ ] Grafana binds to **localhost only.** An unauthenticated dashboard on a public port is a real exposure — the deployed API is public, the dashboard is not.
- [ ] Verify by generating real traffic: ask 5+ questions, then confirm every panel renders actual data. **Screenshot it.**
- [ ] Commit.

---

## Expectations

The dashboard's job is to make a cost/quality tradeoff visible, not to look impressive. The single most valuable thing it can show is the `llama3.1:8b` baseline and the Groq run side by side on the same axes — same 45 questions, different provider, with latency, cost, and refusal rate all in frame.

If cost renders as zero across the board because everything ran on free tiers, say so in the README rather than manufacturing a number. "Measured at $0 on free tiers, with the rate table ready for paid usage" is honest and still demonstrates the instrumentation.
