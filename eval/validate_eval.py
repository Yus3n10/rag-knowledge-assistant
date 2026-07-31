"""Validate the hand-authored eval question set against the corpus."""

import json
import sys
from collections import Counter
from pathlib import Path

CATEGORIES = {"numeric_lookup", "procedural", "conditional", "negative", "near_miss"}

TARGET_COMPOSITION = {
    "numeric_lookup": 0.35,
    "procedural": 0.25,
    "conditional": 0.20,
    "negative": 0.15,
    "near_miss": 0.05,
}
COMPOSITION_TOLERANCE = 0.05


def load_corpus_paragraph_ids(corpus_dir):
    ids = set()
    for path in Path(corpus_dir).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for section in payload["sections"]:
            for record in section["records"]:
                ids.add(record["paragraph_id"])
    return ids


def load_questions(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def validate(questions, known_paragraph_ids, *, check_composition=False):
    errors = []

    seen = set()
    for q in questions:
        qid = q.get("id")
        if qid in seen:
            errors.append(f"duplicate id: {qid}")
        seen.add(qid)

        category = q.get("category")
        if category not in CATEGORIES:
            errors.append(f"{qid}: unknown category {category!r}")
            continue

        citation = q.get("expected_citation")
        if category == "negative":
            if citation is not None:
                errors.append(f"{qid}: negative questions must have expected_citation null")
            if not (q.get("notes") or "").strip():
                errors.append(f"{qid}: negative questions require notes naming the absent topic")
        else:
            if not citation:
                errors.append(f"{qid}: missing expected_citation")
            elif citation["paragraph_id"] not in known_paragraph_ids:
                errors.append(
                    f"{qid}: citation {citation['paragraph_id']} not found in corpus")

    if check_composition and questions:
        counts = Counter(q.get("category") for q in questions)
        total = len(questions)
        for category, target in TARGET_COMPOSITION.items():
            actual = counts[category] / total
            if abs(actual - target) > COMPOSITION_TOLERANCE:
                errors.append(
                    f"composition: {category} is {actual:.0%}, target {target:.0%} "
                    f"(+/-{COMPOSITION_TOLERANCE:.0%})")

    return errors


def main():
    root = Path(__file__).resolve().parent.parent
    questions = load_questions(root / "eval" / "questions.jsonl")
    known = load_corpus_paragraph_ids(root / "data" / "corpus")

    errors = validate(questions, known, check_composition=len(questions) >= 40)
    for error in errors:
        print(error)

    print(f"\n{len(questions)} questions, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
