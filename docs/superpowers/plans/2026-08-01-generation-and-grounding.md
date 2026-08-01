# Phase 3: Generation, Citations, and Hallucination Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn retrieved chunks into answers that cite their sources, and refuse when the corpus does not support an answer.

**Architecture:** Retrieve k=10 paragraphs, build a prompt that forbids outside knowledge and demands paragraph-ID citations, generate with a local Llama 3.1 8B, then validate the output: every citation must resolve to a retrieved paragraph, and every number must appear in the retrieved text. Unsupported answers are flagged; unsupportable questions are refused.

**Tech Stack:** Python 3.11, Ollama (`llama3.1:8b` for generation, `nomic-embed-text` for retrieval), Postgres + pgvector, `requests`, `psycopg`, `pytest`.

**Not in this phase:** FastAPI, React, JWT/roles, Docker deployment, Grafana. Those are Phase 4. This phase ends with a command-line pipeline whose answer quality is measured.

## Global Constraints

- Python 3.11+, Windows, no WSL. `python -m pytest`, never bare `pytest`.
- **No new dependencies.** `requests`, `beautifulsoup4`, `psycopg[binary]`, `pytest` is the entire budget. Do NOT add `langchain`, `llama-index`, `instructor`, `pydantic-ai`, or any orchestration framework. The retrieval and prompt logic here is a few hundred lines; a framework would add a dependency and hide the cost/latency accounting this project exists to demonstrate.
- `eval/questions.jsonl` (45 questions) and `data/` are **FINAL**. Never edit either to improve a score.
- Commit messages carry NO AI/Claude/Anthropic attribution and NO Co-Authored-By trailer.
- Everything runs offline against local Ollama. No hosted API calls in this phase.

## Measured inputs from Phase 2 — use these, do not re-derive

| Fact | Value | Source |
|---|---|---|
| **Generation context k** | **10** | Measured knee: recall and completeness are flat from k=10 to k=25 while context cost grows 2.4x. See `docs/RETRIEVAL_FINDINGS.md`. |
| Retrieval ceiling at k=10 | recall 0.987, completeness 0.833 | The entire residual gap is one unreachable 46-char paragraph, `1910.147(a)(2)(iii)`. |
| Context size at k=10 | ~4,263 chars / ~1,066 tokens | Budget the prompt around this. |
| Generation model | `llama3.1:8b`, already pulled | 4.9GB, runs on the 16GB dev machine. |
| Embedding model | `nomic-embed-text`, 768-dim | Already indexed, 965 chunks. |

**Do not raise k above 10 to chase a better score.** It is measured to gain nothing and cost tokens linearly.

## Refusal design — settled by measurement

A distance threshold **cannot** drive refusal. Measured top-1 cosine distance:

```
ANSWERABLE (38 questions): min 0.089  median 0.202  max 0.305
NEGATIVE    (7 questions): min 0.257  median 0.331  max 0.366
```

The medians separate but the tails overlap. A threshold low enough to catch all 7 negatives (<0.257) falsely refuses **8 of 38 answerable questions**; one permissive enough to keep all answerable (>0.305) admits 5 of 7 negatives. No single value does both.

Therefore: **refusal is a model judgment made over the retrieved context**, driven by an explicit prompt instruction, and validated against the 7 negative questions. Distance may be recorded as a supporting signal but must not be the gate. Any implementation that adds a global distance cutoff is wrong and contradicts this measurement.

---

## Task 0: Verify generation works and measure its cost

**Files:** none (verification only)

- [ ] **Step 1: Confirm the model responds.** `POST http://localhost:11434/api/chat` with `llama3.1:8b` and a trivial message. Record the exact response shape and which keys carry token counts (expect `prompt_eval_count` and `eval_count`).
- [ ] **Step 2: Measure latency and throughput** on a realistic prompt — roughly 1,100 tokens of context plus a question. Record wall-clock seconds, prompt tokens, and generated tokens. This is the baseline the Phase 4 dashboard reports against.
- [ ] **Step 3: Report.** Endpoint, response keys, latency, token counts. Do not commit.

---

## Task 1: Generation client

**Files:** Create `scripts/rag/generate.py`, `tests/test_generate.py`

**Interfaces:** `generate(messages, *, model, url, session=None, options=None) -> tuple[str, dict]`
returning the answer text and a stats dict with at least `prompt_tokens`, `completion_tokens`, `latency_s`.

Mirror `scripts/rag/embed.py`: injectable `session` so tests need no Ollama, explicit token accounting returned rather than logged. Read `embed.py` first and match its style.

Set `temperature=0` by default. A grounded-QA system should be reproducible; sampling variation would make eval runs non-comparable, which defeats tracking a trend line.

- [ ] TDD: failing test with a stub session, watch it fail, implement, pass.
- [ ] Smoke-test against live Ollama; report latency and token counts.
- [ ] Commit.

---

## Task 2: Prompt construction

**Files:** Create `scripts/rag/prompt.py`, `tests/test_prompt.py`

**Interfaces:** `build_messages(question, chunks) -> list[dict]`

The prompt must:
1. Present each retrieved chunk labelled with its `paragraph_id`.
2. Instruct: answer **only** from the provided text; cite the `paragraph_id` for every claim; if the provided text does not contain the answer, say so explicitly and cite nothing.
3. Specify a parseable citation format — square-bracketed IDs, e.g. `[1910.147(e)(3)]`.

Keep the prompt in one module so it is diffable and versionable. Record a `PROMPT_VERSION` constant and include it in eval results — a prompt change that moves the score must be attributable.

- [ ] TDD: assert every chunk's `paragraph_id` appears in the built prompt; assert the refusal instruction is present; assert chunk order is preserved.
- [ ] Commit.

---

## Task 3: Answer parsing and citation validation

**Files:** Create `scripts/rag/ground.py`, `tests/test_ground.py`

**Interfaces:**
- `extract_citations(answer) -> list[str]`
- `validate_citations(citations, retrieved_paragraph_ids) -> dict` with `valid`, `not_retrieved`, `not_in_corpus`

A citation naming a paragraph that was never retrieved means the model produced it from parametric memory, not from the context — that is a hallucination even when the paragraph exists in the corpus. Distinguish the two cases; they have different causes and different fixes.

- [ ] TDD covering: well-formed citations; a citation not among the retrieved set; a fabricated ID absent from the corpus; an answer with no citations at all.
- [ ] Commit.

---

## Task 4: Numeric grounding check

**Files:** extend `scripts/rag/ground.py` and its tests

**Interfaces:** `ungrounded_numbers(answer, retrieved_text) -> list[str]`

Every number in the answer must appear in the retrieved text. Reuse the comma-normalising `numbers_in` logic already proven in `eval/validate_eval.py` — do not write a second, subtly different number parser.

This is the highest-value automated hallucination check for this corpus, because 15 of the 45 questions are `numeric_lookup` and a wrong number in a safety regulation is the most consequential possible error.

- [ ] TDD: an answer whose number is absent from context is flagged; an answer whose numbers all appear is clean; comma forms (`1,000` vs `1000`) are treated as equal.
- [ ] Commit.

---

## Task 5: The answer pipeline

**Files:** Create `scripts/rag/answer.py`, `tests/test_answer.py`

**Interfaces:** `answer_question(question, *, k=10, conn, embedder, generator) -> dict`
returning `answer`, `citations`, `citation_report`, `ungrounded_numbers`, `retrieved` (ids and distances), `stats`.

Wire together retrieve (k=10) → prompt → generate → validate. Everything injectable so tests need neither Postgres nor Ollama.

**Do not add a distance gate.** See the refusal-design section — it is measured not to work, and adding one would silently refuse 8 answerable questions.

- [ ] TDD with stub connection and stub generator.
- [ ] Run against 3 real questions — one numeric, one procedural, one negative — and paste the full answers with citations.
- [ ] Commit.

---

## Task 6: Answer-quality evaluation

**Files:** Create `eval/run_answers.py`, extend `eval/results/` schema

Run all 45 questions through the full pipeline and report:

| Metric | Over | Definition |
|---|---|---|
| Citation validity rate | 38 answerable | Fraction of emitted citations that were actually retrieved |
| Gold citation rate | 38 answerable | Fraction of questions where the answer cites at least one required paragraph |
| Ungrounded-number rate | 15 `numeric_lookup` | Fraction with at least one number absent from context |
| **Refusal accuracy** | 7 negatives | **Hand-reviewed. Never auto-scored.** |

Print each negative's generated answer in full for human review, and write `refusal_accuracy: null` to the results JSON. Classifying refusal-versus-confabulation is a text-understanding judgment; at N=7 a human is cheaper and more trustworthy than a judge model that would itself need validating.

Record `PROMPT_VERSION`, the generation model, k, and total tokens in every result file.

- [ ] TDD the aggregation logic with stubs.
- [ ] Run for real. Report every metric and the 7 negative answers verbatim.
- [ ] **Report the numbers whatever they are.** A model that hallucinates is a finding, not a failure to hide. Do not tune the prompt to improve a score inside the same run that measured it — change one thing, re-run, keep both results.
- [ ] Commit the runner and the first result file.

---

## Expectations

An 8B model will be worse at instruction-following than a frontier model. Expect some citation drift and some over-answering of negatives. That is the point of measuring it: the deliverable is the measurement plus the trend line, not a perfect first score.

If refusal accuracy is poor, the first lever is the prompt (Task 2), not the retrieval — retrieval is already measured at 0.987 recall@10, so a wrong answer at that point is a generation problem, not a retrieval one. Knowing which layer to blame is exactly what Phase 2's numbers bought.
