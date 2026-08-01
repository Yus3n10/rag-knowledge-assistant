"""Run all 45 eval questions through retrieval, score them, print a report,
and save a timestamped JSON result to eval/results/.

Usage: python -m eval.run_eval
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from eval.metrics import per_paragraph_recall, required_paragraphs, strict_completeness
from eval.validate_eval import load_questions
from scripts.rag.embed import embed_texts
from scripts.rag.retrieve import search

DEFAULTS = {
    "DATABASE_URL": "postgresql://rag:ragdev@localhost:5433/rag",
    "OLLAMA_URL": "http://localhost:11434",
    "EMBED_MODEL": "nomic-embed-text",
}

K_VALUES = (5, 10)
OVERFETCH_FACTOR = 4  # retrieve k*4 chunks before dedup, per eval/metrics.py's contract
RESP001_QID = "resp-001"
RESP001_TARGET = "50"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def dedupe_paragraphs(chunks, k):
    """Map retrieved chunks to paragraph_id, drop duplicates keeping first-seen
    (nearest-first) order, then keep only the first k distinct paragraphs.

    Must run on a generous overfetch and BEFORE any k-based scoring - see
    eval/metrics.py's module docstring. A split paragraph contributes several
    chunks at different ranks; deduping first stops it from occupying more
    than one of the k slots that should each hold a different paragraph.
    """
    seen = []
    for chunk in chunks:
        pid = chunk["paragraph_id"]
        if pid not in seen:
            seen.append(pid)
        if len(seen) == k:
            break
    return seen


def is_table_chunk(text):
    return "| --- |" in text


def find_first_chunk_with_number(chunks, number):
    """1-indexed rank of the first chunk whose text contains `number` as a
    standalone number (not part of a longer digit run like '150'). None if
    no retrieved chunk contains it."""
    pattern = re.compile(r"(?<!\d)" + re.escape(number) + r"(?!\d)")
    for i, chunk in enumerate(chunks, start=1):
        if pattern.search(chunk["text"]):
            return i
    return None


def make_embedder(model, url):
    def embedder(texts):
        vectors, _ = embed_texts(texts, model=model, url=url)
        return vectors
    return embedder


def retrieve_all(questions, *, conn, embedder, k_values=K_VALUES, overfetch_factor=OVERFETCH_FACTOR):
    """Run retrieval once per question at a generous overfetch, then dedupe
    to paragraph ids truncated to max(k_values). Because dedup-then-truncate
    preserves order, that single list's first-k prefix equals what deduping
    straight to k would give, so it serves every k in k_values."""
    max_k = max(k_values)
    raw_chunks_by_qid = {}
    retrieved_by_qid = {}
    for q in questions:
        chunks = search(q["question"], k=max_k * overfetch_factor, conn=conn, embedder=embedder)
        raw_chunks_by_qid[q["id"]] = chunks
        retrieved_by_qid[q["id"]] = dedupe_paragraphs(chunks, max_k)
    return raw_chunks_by_qid, retrieved_by_qid


def per_question_recall(questions, retrieved_by_qid, k):
    """Per-question recall fraction (not macro-averaged) plus missed paragraph
    ids, for reporting the weakest questions. Mirrors the hit-counting in
    eval/metrics.py's per_paragraph_recall, which only returns the average."""
    out = {}
    for q in questions:
        required = required_paragraphs(q)
        if not required:
            continue
        retrieved_k = set(retrieved_by_qid.get(q["id"], [])[:k])
        missed = [pid for pid in required if pid not in retrieved_k]
        out[q["id"]] = {
            "category": q["category"],
            "recall": (len(required) - len(missed)) / len(required),
            "missed": missed,
        }
    return out


def build_report(questions, raw_chunks_by_qid, retrieved_by_qid, *, embed_model):
    metrics = {}
    per_question = {}
    for k in K_VALUES:
        metrics[f"k{k}"] = {
            "per_paragraph_recall": per_paragraph_recall(questions, retrieved_by_qid, k),
            "strict_completeness": strict_completeness(questions, retrieved_by_qid, k),
        }
        per_question[f"k{k}"] = per_question_recall(questions, retrieved_by_qid, k)

    resp001_chunks = raw_chunks_by_qid.get(RESP001_QID, [])
    rank = find_first_chunk_with_number(resp001_chunks, RESP001_TARGET)
    resp001_canary = {
        "question_id": RESP001_QID,
        "target_number": RESP001_TARGET,
        "rank_of_first_chunk_with_target": rank,
        "retrieved_chunks": [
            {
                "rank": i,
                "paragraph_id": c["paragraph_id"],
                "is_table": is_table_chunk(c["text"]),
                "contains_target": bool(re.search(
                    r"(?<!\d)" + re.escape(RESP001_TARGET) + r"(?!\d)", c["text"])),
                "distance": c["distance"],
            }
            for i, c in enumerate(resp001_chunks[:10], start=1)
        ],
    }

    negatives = {}
    for q in questions:
        if q["category"] != "negative":
            continue
        chunks = raw_chunks_by_qid.get(q["id"], [])[:5]
        negatives[q["id"]] = {
            "question": q["question"],
            "top_chunks": [
                {"paragraph_id": c["paragraph_id"], "distance": c["distance"]} for c in chunks
            ],
        }

    answerable_count = sum(1 for q in questions if required_paragraphs(q))
    multi_count = sum(1 for q in questions if len(required_paragraphs(q)) > 1)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "k": K_VALUES[0],
        "embedding_model": embed_model,
        "overfetch_factor": OVERFETCH_FACTOR,
        "answerable_count": answerable_count,
        "multi_paragraph_count": multi_count,
        "negative_count": len(negatives),
        "metrics": metrics,
        "refusal_accuracy": None,
        "per_question_recall": per_question,
        "resp001_canary": resp001_canary,
        "negatives": negatives,
    }


def print_report(report):
    m5 = report["metrics"]["k5"]
    m10 = report["metrics"]["k10"]
    n_ans = report["answerable_count"]
    n_multi = report["multi_paragraph_count"]
    n_neg = report["negative_count"]

    print(f"Per-paragraph recall@5  (macro, {n_ans} answerable)    : "
          f"{m5['per_paragraph_recall']:.2f}")
    print(f"Per-paragraph recall@10 (macro, {n_ans} answerable)    : "
          f"{m10['per_paragraph_recall']:.2f}")
    print(f"Strict completeness@5   ({n_multi} multi-paragraph)       : "
          f"{m5['strict_completeness']:.2f}")
    print(f"Strict completeness@10  ({n_multi} multi-paragraph)       : "
          f"{m10['strict_completeness']:.2f}")
    print(f"Refusal accuracy        ({n_neg} negatives)              : PENDING HAND REVIEW")

    print("\nWeakest questions (recall@5):")
    weakest = sorted(report["per_question_recall"]["k5"].items(),
                      key=lambda item: (item[1]["recall"], item[0]))[:5]
    for qid, info in weakest:
        missed = ", ".join(info["missed"]) if info["missed"] else "none"
        print(f"  {qid}  {info['category']}  recall {info['recall']:.2f}  missed: {missed}")

    canary = report["resp001_canary"]
    rank = canary["rank_of_first_chunk_with_target"]
    rank_str = str(rank) if rank is not None else "NOT RETRIEVED"
    print(f"\nresp-001 canary: rank of first chunk containing "
          f"'{canary['target_number']}' = {rank_str}")
    for c in canary["retrieved_chunks"]:
        print(f"  {c['rank']}. {c['paragraph_id']}  table={c['is_table']}  "
              f"contains_50={c['contains_target']}  distance={c['distance']:.4f}")

    print("\nNegative questions - retrieved chunks for hand review:")
    for qid, info in report["negatives"].items():
        print(f"  {qid}  {info['question']}")
        for i, c in enumerate(info["top_chunks"], start=1):
            print(f"     {i}. {c['paragraph_id']}  distance {c['distance']:.4f}")


def main():
    database_url = os.environ.get("DATABASE_URL", DEFAULTS["DATABASE_URL"])
    ollama_url = os.environ.get("OLLAMA_URL", DEFAULTS["OLLAMA_URL"])
    embed_model = os.environ.get("EMBED_MODEL", DEFAULTS["EMBED_MODEL"])

    questions = load_questions(Path(__file__).resolve().parent / "questions.jsonl")
    embedder = make_embedder(embed_model, ollama_url)

    with psycopg.connect(database_url) as conn:
        raw_chunks_by_qid, retrieved_by_qid = retrieve_all(questions, conn=conn, embedder=embedder)

    report = build_report(questions, raw_chunks_by_qid, retrieved_by_qid, embed_model=embed_model)
    print_report(report)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    main()
