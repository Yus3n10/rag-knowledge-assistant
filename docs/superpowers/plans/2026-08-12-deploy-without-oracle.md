# Deploy without Oracle — Implementation Plan

**Goal:** A public URL a recruiter can open, at $0, without waiting on Oracle
free-tier ARM capacity.

**Status of the thing being replaced:** Oracle Ampere A1 capacity has not
freed up despite the retry script (`provision-instance.sh`) and the console
auto-click loop. This is a known-normal Oracle condition, not a
misconfiguration, and it is not worth more waiting.

---

## The only real constraint

The deployed system has three external dependencies. Two are already solved:

| Dependency | State |
|---|---|
| Generation | **Solved.** `scripts/rag/generate.py` already supports Groq; `LLM_PROVIDER=groq` selects it. |
| Postgres + pgvector | **Easy.** 965 chunks x 768 dims ~= 3 MB of vectors, ~15 MB total. Fits any free tier. |
| **Query-time embeddings** | **The constraint.** Every `/ask` embeds the question. Today that is an HTTP call to a local Ollama running `nomic-embed-text`. |

Everything hard about leaving Oracle is that third row, and it is confined to
**one function**: `get_embedder()` in `api/main.py:79`. It builds a closure
over `EMBED_MODEL` + `OLLAMA_URL` and calls `embed_texts()`. Swapping the
embedding backend is a change to that seam plus a sibling of
`scripts/rag/embed.py` — not a rewrite.

**The fork that decides everything else:**

- Keep `nomic-embed-text` -> the committed index stays valid, the measured
  0.92 / 0.99 headline numbers stand unchanged, but something must run a
  ~300 MB model in RAM.
- Change embedding model -> no model to host, fits a 512 MB free container,
  but the index **must be rebuilt and both evals re-run**. The old numbers do
  not transfer. `docker-compose.prod.yml` already warns about this: a
  mismatched embedder breaks retrieval *silently*.

Do not skip the re-eval to save time. Silent retrieval degradation is exactly
the failure this project exists to be able to detect.

---

## Track 1 (recommended): fully managed, no VM, no credit card

| Layer | Service | Notes |
|---|---|---|
| Postgres + pgvector | **Neon** free | 0.5 GB storage, 100 compute-hours/mo, pgvector supported. Our ~15 MB is nothing. Autosuspends when idle. |
| Embeddings | **Cloudflare Workers AI** `@cf/baai/bge-base-en-v1.5` | **768-dim — same as the current `vector(768)` schema, so no migration.** Free daily allocation. |
| Generation | **Groq** free | Already implemented and already measured. |
| API + frontend | **Render** or **Koyeb** free | 512 MB is ample once no embedding model runs in-process. FastAPI already serves `web/dist` at `/`, so no second service. |

**Why this one:** no VM to patch, no capacity lottery, no cross-compile
(Render is amd64 — the `linux/arm64` buildx step in `DEPLOY.md` goes away),
and every tier here is reachable without a credit card. Cold starts on the
free tiers are the price; see "Known limitations".

**Cost:** one re-index and one re-run of both eval suites.

### Tasks

- [ ] Create Neon project; enable `pgvector`; apply `db/schema.sql`.
- [ ] Add a `cloudflare` provider to `scripts/rag/embed.py` as a sibling of
      the Ollama path, mirroring how `generate.py` added `groq`. Same
      signature, same return shape `(vectors, total_tokens)` — the dimension
      check in the existing loop must stay, it is what catches a wrong model.
- [ ] Wire `get_embedder()` (`api/main.py:79`) to select provider from env,
      defaulting to Ollama so local dev is unchanged.
- [ ] TDD both paths with a stub session, showing the RED step. Assert the
      768-dim contract explicitly.
- [ ] **Re-index against Neon** with the new embedder. Verify
      `SELECT count(*) FROM chunks` = 965.
- [ ] **Re-run `python -m eval.run_eval`** — record recall@5/@10 and
      completeness@5/@10 next to the `nomic-embed-text` baseline
      (0.92 / 0.99 / 0.50 / 0.83). **Report the delta, do not tune to match.**
- [ ] **Re-run the answer eval** — citation validity, gold citation rate,
      ungrounded numbers, refusal accuracy.
- [ ] Deploy API to Render/Koyeb from the Dockerfile. Drop the arm64
      constraint. Set `DATABASE_URL`, `JWT_SECRET`, `GROQ_API_KEY`,
      embedding provider vars.
- [ ] `GET /health` over the public URL -> `chunk_count: 965`.
- [ ] Log in as **both** demo users over the public internet and confirm the
      `viewer` / `safety_officer` gated-content difference still holds. This
      is the same check as Phase 4a/4b and it is the thing being demonstrated.
- [ ] Update README with the live URL, deployed latency, and **both**
      embedding backends' scores.

---

## Track 2 (if the measured numbers must not move): one small VM

Keeps `nomic-embed-text` exactly, so the committed index and every published
number stay valid. Only worth it if re-measuring is unacceptable.

- **Google Cloud e2-micro (Always Free)** — us-west1 / us-central1 /
  us-east1, 1 vCPU / 1 GB. Real always-free, no capacity lottery. Put
  Postgres on Neon so the VM only runs Ollama + FastAPI; 1 GB is tight but
  workable that way. x86, so no ARM cross-build. Requires a card on file.
- **The Pi 5 (`savesai`) + Cloudflare Tunnel** — $0 forever, already on 24/7
  for Jarvis, and ARM64 so the image built for Ampere runs unmodified. The
  catch is fate-sharing: a home power or ISP outage takes down the demo *and*
  Jarvis together, and the public URL dies with it. Scope the tunnel
  hostname to the RAG container only so it does not also expose Jarvis.

---

## Track 3 (worst case): static replay demo

If hosting stalls entirely, ship the demo with **no backend at all**.

`eval/results/answers-20260801T155647Z.json` already contains, for all 45
questions: the full answer text, citations, the citation report, ungrounded
numbers, every retrieved paragraph with distances, and per-question token and
latency stats. That is the entire payload the frontend renders.

- [ ] Swap the question textbox for a picker over the 45 recorded questions.
- [ ] Read from the committed JSON instead of `POST /ask`.
- [ ] Label it plainly — "recorded run, 2026-08-01, llama3.1:8b" — visible on
      the page, not buried in a README.
- [ ] Deploy the static build to Cloudflare Pages or GitHub Pages.

**What survives:** the citation interface, the expandable source text, the
retrieved-but-not-cited list, the refusals, and every eval number. That is
the differentiator intact.
**What is lost:** free-text questions. A visitor cannot ask their own.

Honest and always-up beats live and frequently-down. This is a legitimate
destination, not just a consolation prize — but it is strictly worse than
Track 1 and should not be chosen while Track 1 is still viable.

---

## Known limitations to state, not hide

- **Free tiers sleep.** Render free spins down when idle (~1 min cold start);
  Neon autosuspends; Koyeb scales to zero. First visit after a quiet period
  is slow. Put a one-line note on the page so a recruiter does not read a
  cold start as a broken app.
- **Free-tier terms move.** They changed twice while this plan was being
  written — Hugging Face Docker Spaces went PRO-only in 2026, and Railway's
  credit is no longer enough for 24/7. Verify current limits at signup rather
  than trusting this table.
- **Do not weaken security to ship.** No committed `JWT_SECRET`, no giving
  `viewer` the `safety_officer` role to make the demo look better. The
  two-user difference is the demonstration; defeating it removes the reason
  to deploy.

## Expectations

As with the Oracle attempt, the likely failures here are environmental —
tier limits, cold starts, env vars — not application bugs. The one genuine
engineering risk is the embedding swap silently degrading retrieval, and the
eval suite is precisely the instrument that catches it. Run it.
