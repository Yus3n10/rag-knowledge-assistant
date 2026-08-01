# Retrieval Findings — Phase 2

Measured against the 45-question hand-verified eval set over a 965-chunk index
(OSHA 29 CFR 1910 Subparts D, I, and §1910.147), embedded with
`nomic-embed-text` (768-dim) in Postgres + pgvector, cosine distance, exact scan.

## Headline numbers

| Metric | @5 | @10 |
|---|---|---|
| Per-paragraph recall (macro, 38 answerable) | 0.917 | **0.987** |
| Strict completeness (6 multi-paragraph) | 0.500 | **0.833** |
| Refusal accuracy (7 negatives) | hand-reviewed, not auto-scored | |

Recall is macro-averaged: each question contributes one equal vote regardless of
how many paragraphs it requires. Micro-averaging would give the 6 multi-paragraph
questions 23 of 55 pooled gold instances — 42% of the weight from 16% of the
questions — silently turning the headline into a multi-paragraph score. At current
retrieval quality the two agree closely (micro is 0.891 at k=5), so macro is chosen
for that structural reason, not because it rescues the number.

## k plateaus at 10

| k | recall | completeness | context chars | ~tokens |
|---|---|---|---|---|
| 3 | 0.860 | 0.000 | 1,436 | 359 |
| 5 | 0.917 | 0.500 | 2,264 | 566 |
| 8 | 0.955 | 0.667 | 3,391 | 848 |
| **10** | **0.987** | **0.833** | **4,263** | **1,066** |
| 15 | 0.987 | 0.833 | 6,189 | 1,547 |
| 25 | 0.987 | 0.833 | 10,226 | 2,557 |

Both metrics are flat from k=10 through k=25 while context cost grows 2.4x. **k=10
is the measured knee and the default for generation context.** Hybrid keyword+vector
search is the thing to reach for only if generated answers are still incomplete at
k=10 — not before, because most of the apparent k=5 weakness is recovered by a
config value at zero architectural cost.

## The residual gap is one paragraph

Ceilings are 37.5/38 recall and 5/6 completeness. Both are accounted for by a single
gold that is never retrieved at any depth (absent from the top 40):

> `1910.147(a)(2)(iii)` — *"This standard does not apply to the following."* (46 characters)

It is pure structural boilerplate with essentially no distinctive content to embed.
This is the opposite of the dilution failure mode below: not swamped by context,
but carrying almost no signal of its own.

## Hypotheses tested and rejected

Three explanations for weak multi-paragraph completeness were tested by measurement.
None required re-indexing.

**1. Section-level difficulty — REJECTED.** All completeness failures are in
`1910.147`, but mean intra-section cosine similarity ranks it third:

```
1910.137 0.892 | 1910.28 0.891 | 1910.147 0.885 | 1910.29 0.884
1910.25  0.860 | 1910.23 0.849 | 1910.140 0.845 | 1910.134 0.821 | 1910.132 0.768
```

The largest section (`1910.134`, 217 chunks) is second-least self-similar and its
questions pass. Decisively, `loto-008` passes *inside* `1910.147` while `loto-009`,
`loto-010`, and `loto-011` fail — no section-level property can explain that.

**2. Heading-trail dilution by ratio — REJECTED as stated.** The prediction was that
long shared parent prefixes swamp short child paragraphs. It correctly identified
`loto-010` (whose parent `(f)(1)` contributes 336 characters). But `train-001` is
structurally identical — 5 golds, parent plus children — and sweeps ranks 1-5 with a
71-character parent. Against that, `(a)(2)(ii)(A)` has a *worse* trail-to-body ratio
(233:78) than the failing `(e)(2)(i)` (195:99) and retrieves at rank 4. Raw ratio does
not separate passing from failing cases.

**3. Corpus-rarity of a paragraph's own vocabulary — CORRELATES, DOES NOT DETERMINE.**
Mean IDF-weighted distinctiveness of gold bodies: hits 4.045, misses 3.596, and all
four misses fall in the bottom third. It explains the `(a)(2)(ii)(A)` counterexample
well — its short body uses rare words (*guard*, *bypass*), so rarity beats ratio.

But it fails inside a single question. `loto-010`'s five golds share one query, one
parent, one trail:

| gold | distinctiveness | rank |
|---|---|---|
| `(f)(1)(iv)` | 4.950 | 3 |
| `(f)(1)(v)` | 3.883 | 9 |
| `(f)(1)(i)` | 3.344 | 7 |
| `(f)(1)(iii)` | 3.193 | 2 |
| `(f)(1)(ii)` | 2.994 | 5 |

Not monotonic. The lowest-rarity gold ranks 2; the second-highest ranks 9.

## Current best explanation

Query-term overlap, not corpus-rarity. `(f)(1)(iii)` — *"Remove the **lockout or
tagout devices** as specified in paragraph (e)(3)"* — ranks 2 against a query asking
about *"temporarily removing **lockout devices** to test or position equipment"*.
`(f)(1)(i)` — *"Clear the machine of tools and materials"* — shares nothing with the
query and ranks 7.

Short paragraphs whose content does not echo the query get swamped by their shared
heading trail. That is a known limitation of single-vector retrieval over short
chunks, and the standard remedy is hybrid keyword + vector search — an architectural
change, deferred until generated answers demonstrate it is needed at k=10.

## Reproducing

```bash
docker compose up -d
python -m scripts.build_index      # idempotent; ~965 chunks, ~75k tokens
python -m eval.run_eval
```
