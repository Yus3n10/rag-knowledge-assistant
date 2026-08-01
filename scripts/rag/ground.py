"""Hallucination detection: citation validation and numeric grounding.

Checks a generated answer against what was actually retrieved, per
docs/superpowers/plans/2026-08-01-generation-and-grounding.md (Tasks 3-4).
"""

import re

from eval.validate_eval import numbers_in

# IDs contain parens inside the brackets (e.g. [1910.134(d)(3)(i)(A)]), so the
# character class excludes only the brackets themselves, not parens/digits/letters.
CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")

# OSHA citation ID shape: 4 digits, dot, digits, then zero or more parenthesised groups.
# Filters out literal brackets like [RESERVED] or [59 FR 16362, April 6, 1994].
CITATION_ID = re.compile(r"^\d{4}\.\d+(?:\([^)]+\))*$")


def extract_citations(answer):
    """Bracketed paragraph ids in answer, deduplicated, first-appearance order.

    Only returns brackets containing text that matches the OSHA paragraph ID shape,
    ignoring literal brackets in the corpus (e.g. [RESERVED], [59 FR ...]).
    """
    seen = []
    for citation in CITATION_PATTERN.findall(answer):
        if CITATION_ID.match(citation) and citation not in seen:
            seen.append(citation)
    return seen


def validate_citations(citations, retrieved_paragraph_ids, corpus_paragraph_ids=None):
    """Split citations into valid / not_retrieved / not_in_corpus.

    valid: the id was among what was actually retrieved for this answer.
    not_retrieved: the id is real (or corpus_paragraph_ids wasn't supplied to
        check) but wasn't in the retrieved set - the model likely pulled it
        from parametric memory rather than the given context.
    not_in_corpus: corpus_paragraph_ids was supplied and the id isn't in it
        at all - outright fabrication.
    """
    retrieved = set(retrieved_paragraph_ids)
    valid, not_retrieved, not_in_corpus = [], [], []

    for citation in citations:
        if citation in retrieved:
            valid.append(citation)
        elif corpus_paragraph_ids is not None and citation not in corpus_paragraph_ids:
            not_in_corpus.append(citation)
        else:
            not_retrieved.append(citation)

    return {"valid": valid, "not_retrieved": not_retrieved, "not_in_corpus": not_in_corpus}


def ungrounded_numbers(answer, retrieved_text):
    """Numbers stated in answer (outside citation brackets) absent from retrieved_text."""
    answer_without_citations = CITATION_PATTERN.sub("", answer)
    missing = numbers_in(answer_without_citations) - numbers_in(retrieved_text)
    return sorted(missing)
