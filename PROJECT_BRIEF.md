# Grounded RAG Knowledge Assistant — Project Brief

Seed doc for a new chat session dedicated to building this project. Paste this whole file as the opening message, or point Claude at the file path.

## What this is

A document Q&A system for one real vertical, built like a product, not a tutorial. The differentiator is the layer most "RAG chatbot" portfolio projects skip: a retrieval eval harness, citation grounding, hallucination detection, and a live cost/latency dashboard. Ranked #1 (score 8.9/10) in a 12-month portfolio strategy — see career context below.

**Non-negotiable:** the eval harness is not a stretch goal. A plain RAG chatbot with no measured retrieval quality is explicitly the kind of project that gets a resume screened out, not in. If time runs short, cut scope elsewhere before cutting this.

## Career context (why this project, why this shape)

- Builder is a fresh Computer Engineering grad targeting **AI/ML Engineering as core specialty, Backend/Cloud as supporting skill** — chosen to build on existing work (Jarvis proactive AI butler, Pokémon image classifier, license-plate recognition thesis) rather than start cold.
- Existing portfolio already signals "AI person." The gap is *productionized* AI: evals, monitoring, cost control — not another notebook demo.
- 12-month plan, this is project 1 of 3 flagships (RAG Assistant → LGU SaaS → CV Safety System), months 1–4.
- Time budget: **20–40 hrs/week**. Cash budget: **$0 — free tier / self-hosted only.**
- Get this fully production-grade (tests, CI, monitoring) before moving to project 2. Start applying to jobs once this ships, don't wait for all three.

## Constraints that shape every technical decision

- **$0 budget, real API costs.** LLM inference is not free at scale. Resolve this by developing against local open-weight models (Ollama — Llama 3.1 8B or Qwen2.5, runs on a 16GB machine) and reserving a free hosted tier (Groq or Cloudflare Workers AI) only for the public-facing demo link, not for heavy iteration.
- Builder's machine: Windows, Lenovo LOQ 15IRX9, 16GB RAM, no WSL, Docker only via an Ubuntu container ("slight knowledge" — this project is a forcing function to get comfortable with it).
- Known languages/tools: Python, TypeScript, Laravel/PHP, MySQL, Oracle. Comfortable pace, don't over-explain fundamentals — do explain unfamiliar tooling and architecture trade-offs.
- Deploy target: **Oracle Cloud free tier** (Ampere ARM VM, free forever) — plays to existing Oracle DB familiarity.
- **Do not** build the demo's rate-limit/cost-handling on a free-tier-stacking proxy tool (e.g. OmniRoute). That was evaluated separately: legitimate as a personal dev-productivity tool, but baking it into this project's architecture undercuts the entire point of the eval/cost-dashboard differentiator — "a router hid the cost problem from me" is a weaker interview answer than "I measured and managed it myself."

## Vertical: decided — manufacturing specs / compliance docs

Chosen over legal contracts and hospital SOPs, for four reasons:

1. **Portfolio synergy** — Project 3 (CV Safety/QC System) is also manufacturing-vertical. Two flagships in the same domain tell one coherent "production AI for industrial reliability" story instead of three disconnected demos.
2. **Cleanest $0 data sourcing** — OSHA 29 CFR 1910 (US federal workplace safety regulations) is public domain, large, and already structured into numbered sections — ideal for citation grounding. Legal contracts are mostly confidential; hospital guidelines are public but invite PHI/Data-Privacy-Act questions in interviews even with no real patient data involved.
3. **Easiest domain for a rigorous eval harness** — specs have factual, checkable answers ("max torque for bolt X" → "150 Nm"), so retrieval precision/recall can be measured against ground truth. Legal/clinical answers are more interpretive and harder to grade automatically — and easier to fake having evaluated.
4. **Lowest regulatory noise** — no PHI-adjacency or data-privacy-law tangents to pre-empt.

**Corpus plan:** OSHA 29 CFR 1910 as the base corpus (public domain, citable by section number). Optionally layer a synthetic company-specific SOP set on top once the retrieval pipeline works, for a more realistic "internal knowledge base" demo.

### Corpus scope — decided: 3 subparts, not the full standard

Full 1910 (all ~100 subparts) and full+SOP-layer-on-day-one were both considered and rejected: both spend build time on corpus breadth instead of the eval harness, which is the actual differentiator. Every eval question needs to be hand-verified against source text — that only stays feasible at a bounded scope. The synthetic SOP layer (role-gating demo) stays a later addition, after retrieval + evals are proven on the public corpus alone; building both at once conflates two different problems (retrieval quality vs. access control) before either is solid.

**Chosen subparts** — picked for three different question shapes, to stress-test retrieval against real variety rather than one document style:

1. **Subpart D — Walking-Working Surfaces** (procedural)
2. **Subpart I — Personal Protective Equipment** (conditional/equipment requirements)
3. **Subpart J — General Environmental Controls**, specifically **1910.147 Lockout/Tagout** (one of the most-cited OSHA standards, tightly scoped, procedural with clear right-answer steps) — chosen over a full Subpart Z pull, since Z alone contains dozens of full substance-specific standards and is too large to hand-verify at this stage. If a numeric-lookup question shape is still wanted, bound Z to a short defined substance list (e.g. benzene, lead, asbestos, bloodborne pathogens + their PEL tables) rather than taking the subpart whole.

### Ingestion — decided: scrape osha.gov HTML

OSHA publishes 1910 as clean per-section HTML pages (`osha.gov/laws-regs/regulations/standardnumber/1910/1910.147`, etc.). Chosen over eCFR bulk XML (heavier schema, carries amendment/versioning metadata not needed for a 3-subpart demo — same underlying authoritative text as osha.gov, just harder to parse) and manual copy-paste (transcription-error risk directly into the eval ground truth, zero reusability if the corpus expands later).

Treat the scraper as a real deliverable, not throwaway glue — this is where the data-engineering skill this project already absorbs (rather than being project 4) actually shows up:

- Reusable module, e.g. `scripts/ingest_osha.py` — one function per subpart URL, re-runnable if more subparts are added later
- Output **two forms**: structured JSON (`section_id`, subpart, heading hierarchy, paragraph text) feeding pgvector/citation-grounding, and a parallel rendered Markdown file per subpart for hand-verifying eval questions against — JSON is painful to eyeball for that step
- Cache raw scraped HTML locally after first pull; don't re-hit osha.gov on every parsing iteration
- Read-only GETs against a public .gov site — standard scraping etiquette (reasonable rate, local caching), no special permission needed

### Eval question set — decided: hand-write ~45–50, LLM used only as a drafting aid

Not LLM-drafted-then-reviewed as a pipeline stage, and not a larger sampled-verification set — both would weaken the one claim this project is built to make ("every eval question hand-verified against real text"). Claude can help draft candidate questions in conversation, but the user reads the actual section and personally confirms/edits/rejects each one before it enters the set — the draft never enters the pipeline unverified, and the verification step is never sampled.

Deliberate mix, not just a flat count — roughly proportional across the 3 subparts:

| Type | Purpose | Share |
|---|---|---|
| Factual/numeric lookup | Precision baseline | ~35% |
| Procedural/step-order | Tests retrieval across multi-paragraph sequences | ~25% |
| Conditional/"when does X apply" | Tests handling of scoped/exception language | ~20% |
| Negative — no answer in corpus | Tests hallucination detection directly (model should say "not covered," not guess) | ~15% |
| Near-miss "trap" (similar wording, wrong section) | Tests retrieval precision, not just recall | ~5–10% |

### Phase 1 implementation spec — corpus & eval ingestion

Ready to build. Repo layout for this phase:

```
rag-knowledge-assistant/
  PROJECT_BRIEF.md
  requirements.txt        # requests + beautifulsoup4 only — no scraping framework needed for 3 static subparts
  scripts/ingest_osha.py
  data/raw/                # cached HTML per subpart — committed to git
  data/corpus/              # <subpart>.json + <subpart>.md — committed to git
  data/README.md            # scrape date, 3 source URLs, public-domain note — provenance for the Definition-of-Done doc requirement
  eval/questions.jsonl
```

- `scripts/ingest_osha.py`: one fetch function per subpart URL, raw HTML cached to `data/raw/` so re-parsing never re-hits osha.gov. Parses to `data/corpus/<subpart>.json`: array of `{section_id, heading, parent_headings[], paragraph_id, text}` — `parent_headings[]` carries hierarchy context so citations can render as "Subpart D → 1910.23 → (b)(1)", not a bare section ID. Also emits a parallel `data/corpus/<subpart>.md` per subpart for hand-verifying eval questions against.
- **`data/raw/` and `data/corpus/` are committed, not gitignored.** Public-domain text, tiny volume — committing makes the repo reproducible and demoable with zero network dependency on osha.gov staying unchanged, which matters more here than in a typical repo since this project needs to be a clickable, working demo for anyone who clones it.
- `eval/questions.jsonl`: ~45 hand-verified questions, schema `{id, question, category, expected_answer, expected_citation: {subpart, section_id, paragraph_id}, notes}`. `category` ∈ `numeric_lookup | procedural | conditional | negative | near_miss`. Negative questions carry a `notes` field stating what topic is absent and why, so "not covered" is a documented claim, not a guess.

### Known issues carried into Phase 2 (chunking/retrieval)

- **Definitions blobs need per-term splitting.** `1910.140(b)` is a single 11,720-character paragraph containing ~40 defined terms; `1910.21(b)` is similar. Median record is 127 characters. Generic chunking will either pull the whole blob (wasting context and diluting relevance for a query about one term) or cut it at an arbitrary window boundary mid-definition. These need special-case handling — split by defined term, each with its own identifier. Note the ingestion parser is already written and the corpus already built, so this is either a targeted re-ingest or a chunking-time split; decide which when Phase 2 starts.
- **Table content lives outside `record["text"]`.** Tables are stored separately in `record["tables"]`. A chunker embedding `text` alone makes all table-bearing records unretrievable — precisely the `numeric_lookup` targets.
- Full triaged list: `.superpowers/sdd/progress.md`.

## Target shape

| | |
|---|---|
| Target employer | AI startups, LLMOps/platform teams, "Applied AI Engineer" roles, industrial IoT / manufacturing tech |
| Target freelance client | Small factories / warehouses / compliance teams needing internal spec & safety-doc search |
| Difficulty / time | High · ~14–18 weeks at 20–40 hrs/wk |
| Auth | JWT + role-based doc access (some docs role-gated — proves real access control, not just a login page) |
| Possible revenue | $500–2,000 per freelance install, or fully open-source for pure portfolio signal |

## Tech stack

- **Backend:** FastAPI or Laravel (pick based on which better demonstrates range against the LGU SaaS project, which will already be Laravel — leaning FastAPI for stack diversity)
- **Vector store:** Postgres + pgvector (free, self-hosted, reuses SQL knowledge — no separate vector DB service needed)
- **LLM (dev):** Ollama, local open-weight models (Llama 3.1 8B / Qwen2.5)
- **LLM (public demo):** Groq free tier or Cloudflare Workers AI free tier
- **Frontend:** React/TypeScript
- **Infra:** Oracle Cloud free tier VM, Docker (forcing-function for the "slight knowledge" gap)
- **CI:** GitHub Actions
- **Monitoring:** Grafana Cloud free tier

## What "done" looks like

- [ ] Vertical chosen, corpus sourced and documented (where it came from, licensing)
- [ ] Retrieval eval harness: precision/recall on a held-out question set, tracked over time
- [ ] Citation grounding: every answer traces back to a specific source chunk, shown in the UI
- [ ] Hallucination detection: flagged when the model answers without sufficient retrieved support
- [ ] Live cost/latency dashboard (Grafana): tokens, $ per query, p95 latency
- [ ] Role-based access control on documents, not just user login
- [ ] Deployed and reachable at a live URL, not just runnable locally
- [ ] CI pipeline: tests run and pass on every push
- [ ] README: quantifies the business problem solved (time saved per lookup), documents the $0-budget trade-off explicitly, includes an ADR for the biggest architecture decision

## Explicit non-goals

- Novel retrieval research (chunking tricks, embedding model comparisons) — use a solid off-the-shelf approach, spend the saved time on the eval harness instead
- Multi-vertical support — one vertical, done well, beats three done shallowly
- A custom auth system — use a standard library/pattern, this project isn't about proving you can hand-roll auth
- Chasing more LLM providers than the two already chosen (Ollama for dev, one free tier for the demo)

## First message for the new session

> I'm starting the Grounded RAG Knowledge Assistant project — see PROJECT_BRIEF.md in this repo for full context. Vertical is decided: manufacturing specs/compliance, corpus is OSHA 29 CFR 1910. First thing I need from you: help me pull and structure the corpus, and design the held-out eval question set, before we touch the retrieval pipeline.
