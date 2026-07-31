"""Validate the hand-authored eval question set against the corpus."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

# Categories track QUESTION SHAPE, not subject matter or unit type.
#
#   numeric_lookup  One specific extractable value living in a single passage.
#                   Dimension, force, count, or duration - the unit does not
#                   matter. Tests whether the pipeline returns the exact value
#                   without drifting to a nearby wrong one.
#   procedural      Genuinely multi-step or sequential, where order or
#                   completeness across several clauses is what is being tested.
#   conditional     Turns on scoped or exception language ("when does X apply").
#   negative        Not answerable from this corpus. Tests refusal, not recall.
#   near_miss       Deliberately similar phrasing to another passage, written to
#                   bait the wrong answer. The exclusion is for DISJOINT SCOPE,
#                   not for a shared template with swapped nouns:
#                     - 1910.23(b)(2)(i) names "elevator shafts" - a genuinely
#                       separable setting, so the question disambiguates itself.
#                       Not a near_miss.
#                     - 1910.29(b)(3) vs (b)(5) are different components of the
#                       SAME assembly in a near-verbatim template differing by
#                       one noun and one number. Naming "midrails" does not
#                       resolve a source-text-level collision. Near_miss.
CATEGORIES = {"numeric_lookup", "procedural", "conditional", "negative", "near_miss"}

# Questions whose real answer spans several child paragraphs (a step sequence,
# not a single fact) may cite expected_citation.paragraph_ids instead of a lone
# paragraph_id - retrieval must surface all of them. Restricted to categories
# where a multi-paragraph answer is the point - numeric_lookup is a single-
# passage value by definition.
#
# There is no "any one of these" mode. One was built and later removed: every
# real multi-citation question that looked like an "any" candidate turned out,
# on inspection, to need all of its sources for a complete answer - "what are
# the acceptable alternatives" has to state every alternative, not confirm
# retrieval found one. It was also untested against real data before removal.
# If a genuine "any" case ever shows up, rebuild it against that case, not in
# the abstract.
#
# When to include a parent paragraph in paragraph_ids: the test is SEMANTIC
# self-containment, not grammatical completeness. Ask whether the paragraph
# states what its own condition is FOR - subject, condition, and consequence.
#
#   1910.147(a)(2)(ii)(A) "An employee is required to remove or bypass a
#     guard...; or" is a grammatically complete sentence but NOT self-
#     contained: required for what consequence lives only in the parent's
#     "is covered by this standard only if:". Parent required.
#   1910.134(c)(2)(i) "An employer may provide respirators... if the employer
#     determines that such use will not in itself create a hazard" carries its
#     own subject, condition, and consequence. Its trailing "; and" is just
#     OSHA's connector to the next sibling. No parent needed.
#
# Grammatical completeness alone is not sufficient - it happens to agree with
# self-containment often, but not always.
#
# Separately: cite the paragraph that answers the question ASKED. A "when does
# this apply" question is answered by the condition, not by the steps that
# follow it, even when those steps are the same paragraph's children.
MULTI_CITATION_CATEGORIES = {"procedural", "conditional"}

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
        paragraph_ids = citation.get("paragraph_ids")

        if paragraph_id and paragraph_ids:
            errors.append(f"{qid}: expected_citation must not set both paragraph_id and paragraph_ids")
            continue

        if paragraph_ids is not None:
            if category not in MULTI_CITATION_CATEGORIES:
                errors.append(
                    f"{qid}: paragraph_ids is only allowed for "
                    f"{sorted(MULTI_CITATION_CATEGORIES)}, not {category!r}")
                continue
            if not isinstance(paragraph_ids, list) or not paragraph_ids:
                errors.append(f"{qid}: paragraph_ids must be a non-empty list")
                continue
            if "citation_match" in citation:
                errors.append(
                    f"{qid}: citation_match was removed - paragraph_ids always means "
                    f"'all required', drop the field")
                continue
            for pid in paragraph_ids:
                record = corpus_index.get(pid)
                if record is None:
                    errors.append(f"{qid}: citation {pid} not found in corpus")
                    continue
                if citation.get("section_id") and citation["section_id"] != record["section_id"]:
                    errors.append(
                        f"{qid}: citation says section {citation['section_id']} "
                        f"but {pid} is in {record['section_id']}")
                if citation.get("subpart") and citation["subpart"] != record["subpart"]:
                    errors.append(
                        f"{qid}: citation says {citation['subpart']} "
                        f"but {pid} is in {record['subpart']}")
            continue

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
