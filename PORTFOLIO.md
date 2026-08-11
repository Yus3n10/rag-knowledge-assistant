# RAG Knowledge Assistant

**Grounded Q&A over OSHA safety regulations, with measured retrieval instead of assumed retrieval.**

- **Live:** https://rag-knowledge-assistant-z3hw.onrender.com/
- **Repo:** https://github.com/Yus3n10/rag-knowledge-assistant
- **Role:** Sole developer — corpus, retrieval, eval harness, API, frontend, deployment
- **Status:** Shipped and live

Demo sign-in: `viewer` / `viewer-pass` (general) or `officer` / `officer-pass` (safety officer). Ask both *"Who may remove a lockout device?"* to see the access gate in action. Free-tier hosting sleeps when idle, so a first request can take about a minute.

---

## One-line summary

A retrieval-augmented Q&A system over OSHA 29 CFR 1910 where every claim is traceable to the paragraph it came from, unsupported numbers are flagged, and questions outside the corpus are declined rather than guessed at.

## The problem

Most RAG portfolio projects are a chatbot with a vector database and a confident tone. There's no way to tell whether the retrieval is any good, whether the citations are real, or whether the model is inventing numbers — and in a compliance setting, a confident wrong answer is worse than no answer.

This project was built the other way round. The chatbot is the easy part. The deliverable is the **eval harness** that proves the chatbot works, and the interface that lets a reader verify a claim instead of trusting it.

## What it does

**Answers with verifiable sources.** Every bracketed paragraph id in an answer expands in place to show the exact regulation text behind that claim, with its heading trail. Paragraphs the model *cited* are shown distinctly from paragraphs that were retrieved into context but never referenced — that second list matters, because when a claim is misattributed the correct source is usually sitting in it.

**Flags what it can't support.** Numbers appearing in an answer but in none of the retrieved text are surfaced in a caution note rather than hidden.

**Declines out of scope.** The corpus is three slices of 29 CFR 1910, not all of OSHA. Questions it doesn't cover get a dedicated "outside the indexed corpus" state that explains the boundary and shows what the search did reach — a refusal presented as a correct outcome, not a failure.

**Enforces role-based access at the data layer.** A general viewer and a safety officer see different content. The gate lives in the retrieval SQL, so a viewer calling the API directly with a valid token still cannot reach gated paragraphs — the model never sees them.

**Makes retrieval visible.** A corpus map renders all 937 indexed paragraphs as cells in document order, grouped by subpart, and lights the ten a question retrieved. Ask about lockout/tagout and the lit cells cluster in the Subpart J band.

## Measured results

45 hand-verified questions (38 answerable, 7 negatives). Every citation machine-checked against the corpus; refusals read individually rather than auto-scored.

| Metric | Result |
|---|---|
| Citations resolved to a real paragraph | **60 / 60** |
| Fabricated citations | **0** |
| Gold citation rate | 37 / 38 |
| Ungrounded numbers (15 numeric lookups) | 0 |
| Out-of-scope questions declined | 7 / 7 |
| Per-paragraph recall @10 | 0.97 |
| Per-paragraph recall @5 | 0.88 |
| Mean generation latency | 0.41s |

Retrieval was measured on **two embedding backends** — local `nomic-embed-text` and hosted `bge-base-en-v1.5` — and both sets of numbers are published, including where the hosted stack is slightly worse. Small denominators are reported as fractions rather than percentages, because one question flipping out of six is noise, not a result.

## Tech stack

**Backend:** Python, FastAPI, Uvicorn, PyJWT, Passlib/bcrypt
**Data:** PostgreSQL 16 + pgvector (Neon in production, Docker locally), 965 chunks / 937 paragraphs
**Retrieval:** `bge-base-en-v1.5` via Cloudflare Workers AI (hosted), `nomic-embed-text` via Ollama (local) — both 768-dim
**Generation:** `llama-3.1-8b-instant` via Groq (hosted), `llama3.1:8b` via Ollama (local)
**Frontend:** React 19, TypeScript, Vite, vanilla CSS
**Infra:** Docker multi-stage build, Render, GitHub Actions CI, Grafana cost/latency dashboard
**Testing:** pytest (181 tests), Vitest + Testing Library (16 tests), custom eval harness

## What I'd point at in an interview

**The eval harness caught three real bugs that tests could not.** Migrating to a hosted embedding provider, a partially-wired provider left queries embedded with one model against an index built by another. Nothing errored — both return valid 768-dim vectors — but every metric scored 0.00 and distances flattened to near-orthogonal. Only measurement surfaced it. Two more followed: a provider-specific model name that broke every request in production, and an eval that scored itself 0.63 because its own role gate hid the most-cited section from it.

**Silent degradation is the real failure mode in RAG,** and it's exactly what a test suite is blind to. That's the argument for building the harness first.

**Migration is a measurement problem, not a porting problem.** Moving from a self-hosted VM to fully managed free tiers meant changing the embedding model, which invalidates every published number. The honest move was to re-measure and publish the delta rather than quietly keep the old figures.

## Known limitations

- Retrieval is weakest on `1910.147`, where 120 paragraphs share a section heading and compete with each other. Both embedding backends fail on the same questions, which locates the problem in chunking rather than in either model.
- Answer metrics are one model on one prompt version, not a cross-model comparison.
- The 45 questions are a hand-authored set, not a public benchmark.
- Free-tier hosting sleeps when idle; the first request after a quiet period is slow.
