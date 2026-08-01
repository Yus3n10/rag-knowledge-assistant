"""Run all 45 eval questions through the full answer pipeline, score answer
quality, print a report (including every negative question's full answer for
hand review), and save a timestamped JSON result to eval/results/.

Usage: python -m eval.run_answers
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests

from eval.metrics import required_paragraphs
from eval.run_eval import make_embedder
from eval.validate_eval import load_corpus_index, load_questions
from scripts.rag.answer import answer_question
from scripts.rag.generate import generate
from scripts.rag.prompt import PROMPT_VERSION

DEFAULTS = {
    "DATABASE_URL": "postgresql://rag:ragdev@localhost:5433/rag",
    "OLLAMA_URL": "http://localhost:11434",
    "EMBED_MODEL": "nomic-embed-text",
    "GEN_MODEL": "llama3.1:8b",
}

K = 10  # measured knee, see docs/RETRIEVAL_FINDINGS.md -- do not raise to chase a score
RESP001_QID = "resp-001"
RESP001_EXPECTED_PARAGRAPH = "1910.134(d)(3)(i)(A)"
NUMBER_50 = re.compile(r"(?<!\d)50(?!\d)")
RESULTS_DIR = Path(__file__).resolve().parent / "results"
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.jsonl"
CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"


def make_generator(model, url):
    session = requests.Session()

    def generator(messages):
        return generate(messages, model=model, url=url, session=session)

    return generator


# --- aggregation (pure, no I/O -- covered by tests/test_run_answers.py) ----

def citation_validity_rate(records):
    """Fraction of citations emitted by answerable questions that were
    actually retrieved (pooled across questions, not averaged per-question)."""
    answerable = [r for r in records if r["category"] != "negative"]
    valid = sum(len(r["citation_report"]["valid"]) for r in answerable)
    not_retrieved = sum(len(r["citation_report"]["not_retrieved"]) for r in answerable)
    not_in_corpus = sum(len(r["citation_report"]["not_in_corpus"]) for r in answerable)
    total = valid + not_retrieved + not_in_corpus
    return valid / total if total else 0.0


def gold_citation_rate(records):
    """Fraction of answerable questions whose answer cites at least one
    required (gold) paragraph."""
    answerable = [r for r in records if r["category"] != "negative"]
    if not answerable:
        return 0.0
    hits = sum(1 for r in answerable if set(r["citations"]) & set(r["required"]))
    return hits / len(answerable)


def ungrounded_number_rate(records):
    """Fraction of numeric_lookup questions with at least one number absent
    from the retrieved text."""
    numeric = [r for r in records if r["category"] == "numeric_lookup"]
    if not numeric:
        return 0.0
    flagged = sum(1 for r in numeric if r["ungrounded_numbers"])
    return flagged / len(numeric)


def fabricated_citation_count(records):
    """Count of citations landing in not_in_corpus, across ALL questions."""
    return sum(len(r["citation_report"]["not_in_corpus"]) for r in records)


def resp001_detail(records):
    """Planted regression check: the answer to resp-001 (APF 50) exists only
    in a table chunk. Reports whether the answer states 50, whether it cited
    the expected paragraph, and whether the retrieved context contained 50
    at all -- independent of the answer, so a bad generation is
    distinguishable from a bad retrieval."""
    resp001 = next((r for r in records if r["id"] == RESP001_QID), None)
    if resp001 is None:
        return None
    return {
        "answer_contains_50": bool(NUMBER_50.search(resp001["answer"])),
        "cited_expected_paragraph": RESP001_EXPECTED_PARAGRAPH in resp001["citations"],
        "context_contains_50": bool(NUMBER_50.search(resp001["retrieved_text"])),
    }


def build_report(records, *, k, embed_model, gen_model):
    negatives = [r for r in records if r["category"] == "negative"]
    numeric = [r for r in records if r["category"] == "numeric_lookup"]
    answerable = [r for r in records if r["category"] != "negative"]

    total_prompt_tokens = sum(r["stats"]["prompt_tokens"] for r in records)
    total_completion_tokens = sum(r["stats"]["completion_tokens"] for r in records)
    mean_latency_s = sum(r["stats"]["latency_s"] for r in records) / len(records) if records else 0.0

    per_question = [
        {
            "id": r["id"],
            "category": r["category"],
            "question": r["question"],
            "answer": r["answer"],
            "citations": r["citations"],
            "citation_report": r["citation_report"],
            "ungrounded_numbers": r["ungrounded_numbers"],
            "required": r["required"],
            "retrieved": r["retrieved"],
            "stats": r["stats"],
        }
        for r in records
    ]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "k": k,
        "prompt_version": PROMPT_VERSION,
        "generation_model": gen_model,
        "embedding_model": embed_model,
        "answerable_count": len(answerable),
        "numeric_lookup_count": len(numeric),
        "negative_count": len(negatives),
        "metrics": {
            "citation_validity_rate": citation_validity_rate(records),
            "gold_citation_rate": gold_citation_rate(records),
            "ungrounded_number_rate": ungrounded_number_rate(records),
            "fabricated_citation_count": fabricated_citation_count(records),
            "refusal_accuracy": None,  # hand-reviewed only, never auto-scored
        },
        "resp001_detail": resp001_detail(records),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "mean_latency_s": mean_latency_s,
        "per_question": per_question,
    }


def print_report(report, records):
    m = report["metrics"]
    print()
    print(f"Citation validity rate  ({report['answerable_count']} answerable)     : "
          f"{m['citation_validity_rate']:.2f}")
    print(f"Gold citation rate      ({report['answerable_count']} answerable)     : "
          f"{m['gold_citation_rate']:.2f}")
    print(f"Ungrounded-number rate  ({report['numeric_lookup_count']} numeric_lookup) : "
          f"{m['ungrounded_number_rate']:.2f}")
    print(f"Fabricated citations    (all {len(records)})               : "
          f"{m['fabricated_citation_count']}")
    print(f"Refusal accuracy        ({report['negative_count']} negatives)         : "
          "PENDING HAND REVIEW (see answers below)")

    print(f"\nTotal prompt tokens: {report['total_prompt_tokens']}   "
          f"Total completion tokens: {report['total_completion_tokens']}   "
          f"Mean latency: {report['mean_latency_s']:.2f}s")

    detail = report["resp001_detail"]
    if detail is not None:
        print("\nresp-001 (planted regression, APF 50 lives only in a table chunk):")
        print(f"  answer contains '50'          : {detail['answer_contains_50']}")
        print(f"  cited expected paragraph      : {detail['cited_expected_paragraph']}")
        print(f"  retrieved context contains 50 : {detail['context_contains_50']}")

    print("\n--- Negative questions: full answers for hand review of refusal ---")
    for r in records:
        if r["category"] != "negative":
            continue
        print(f"\n[{r['id']}] {r['question']}")
        print(f"  ANSWER: {r['answer']}")
        print(f"  citations emitted: {r['citations']}")

    print("\n--- Worst offenders (invalid citations / ungrounded numbers / no gold citation) ---")
    for r in records:
        problems = []
        if r["citation_report"]["not_retrieved"] or r["citation_report"]["not_in_corpus"]:
            problems.append("invalid citation")
        if r["ungrounded_numbers"]:
            problems.append("ungrounded number")
        if r["category"] != "negative" and r["required"] and not (set(r["citations"]) & set(r["required"])):
            problems.append("no gold citation")
        if problems:
            print(f"  {r['id']} ({r['category']}): {', '.join(problems)}")
            if r["citation_report"]["not_retrieved"]:
                print(f"      not_retrieved: {r['citation_report']['not_retrieved']}")
            if r["citation_report"]["not_in_corpus"]:
                print(f"      not_in_corpus: {r['citation_report']['not_in_corpus']}")
            if r["ungrounded_numbers"]:
                print(f"      ungrounded_numbers: {r['ungrounded_numbers']}")


def main():
    database_url = os.environ.get("DATABASE_URL", DEFAULTS["DATABASE_URL"])
    ollama_url = os.environ.get("OLLAMA_URL", DEFAULTS["OLLAMA_URL"])
    embed_model = os.environ.get("EMBED_MODEL", DEFAULTS["EMBED_MODEL"])
    gen_model = os.environ.get("GEN_MODEL", DEFAULTS["GEN_MODEL"])

    questions = load_questions(QUESTIONS_PATH)
    corpus_paragraph_ids = set(load_corpus_index(CORPUS_DIR).keys())

    embedder = make_embedder(embed_model, ollama_url)
    generator = make_generator(gen_model, ollama_url)

    records = []
    with psycopg.connect(database_url) as conn:
        for i, q in enumerate(questions, start=1):
            start = time.monotonic()
            result = answer_question(
                q["question"], k=K, conn=conn, embedder=embedder, generator=generator,
                corpus_paragraph_ids=corpus_paragraph_ids,
            )
            elapsed = time.monotonic() - start
            print(f"[{i}/{len(questions)}] {q['id']} ({q['category']}) - {elapsed:.1f}s")
            records.append({
                "id": q["id"], "category": q["category"], "question": q["question"],
                "required": required_paragraphs(q),
                **result,
            })

    report = build_report(records, k=K, embed_model=embed_model, gen_model=gen_model)
    print_report(report, records)

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"answers-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    main()
