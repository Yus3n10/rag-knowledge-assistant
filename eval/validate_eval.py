"""Validate the hand-authored eval question set against the corpus."""

import json
import re
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

NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text):
    """Numeric tokens in text, comma separators removed so 1,000 reads as 1000."""
    return set(NUMBER_PATTERN.findall(text.replace(",", "")))


def load_corpus_index(corpus_dir):
    """Map every corpus paragraph_id to its subpart, section, and full text."""
    index = {}
    for path in sorted(Path(corpus_dir).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for section in payload["sections"]:
            for record in section["records"]:
                index[record["paragraph_id"]] = {
                    "subpart": payload["subpart"],
                    "section_id": section["section_id"],
                    "text": " ".join([record["text"]] + record["tables"]),
                }
    return index


def load_questions(path):
    questions = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            questions.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON - {exc}") from exc
    return questions


def validate(questions, corpus_index, *, check_composition=False):
    errors = []

    seen = set()
    for q in questions:
        qid = q.get("id")
        if not qid:
            errors.append("question is missing an id")
        elif qid in seen:
            errors.append(f"duplicate id: {qid}")
        seen.add(qid)

        if not (q.get("question") or "").strip():
            errors.append(f"{qid}: question text must not be empty")

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
            continue

        answer = (q.get("expected_answer") or "").strip()
        if not answer:
            errors.append(f"{qid}: expected_answer must not be empty")

        if not citation:
            errors.append(f"{qid}: missing expected_citation")
            continue
        paragraph_id = citation.get("paragraph_id")
        if not paragraph_id:
            errors.append(f"{qid}: expected_citation is missing paragraph_id")
            continue

        record = corpus_index.get(paragraph_id)
        if record is None:
            errors.append(f"{qid}: citation {paragraph_id} not found in corpus")
            continue

        if citation.get("section_id") and citation["section_id"] != record["section_id"]:
            errors.append(
                f"{qid}: citation says section {citation['section_id']} "
                f"but {paragraph_id} is in {record['section_id']}")
        if citation.get("subpart") and citation["subpart"] != record["subpart"]:
            errors.append(
                f"{qid}: citation says {citation['subpart']} "
                f"but {paragraph_id} is in {record['subpart']}")

        if category == "numeric_lookup" and answer:
            missing = sorted(numbers_in(answer) - numbers_in(record["text"]))
            if missing:
                errors.append(
                    f"{qid}: numbers {missing} in expected_answer "
                    f"do not appear in {paragraph_id}")

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
    corpus_index = load_corpus_index(root / "data" / "corpus")

    errors = validate(questions, corpus_index, check_composition=len(questions) >= 40)
    for error in errors:
        print(error)

    if questions:
        counts = Counter(q.get("category") for q in questions)
        print("\ncomposition (target in parentheses):")
        for category, target in TARGET_COMPOSITION.items():
            actual = counts[category] / len(questions)
            print(f"  {category:<14} {counts[category]:>3}  {actual:>4.0%}  ({target:.0%})")

    print(f"\n{len(questions)} questions, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
