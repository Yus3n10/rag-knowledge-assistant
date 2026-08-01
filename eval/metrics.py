"""Retrieval metrics for the eval question set. Pure functions, no I/O.

Caller contract: `retrieved_by_qid` must map each question id to an ordered
list of PARAGRAPH ids, not chunk ids. A split paragraph produces chunks like
"1910.21(b)#0" and "1910.21(b)#3" that both belong to paragraph "1910.21(b)".
The caller is responsible for mapping retrieved chunk ids back to their
paragraph ids and then deduplicating while preserving order BEFORE calling
these functions. Getting this wrong lets one paragraph occupy several of the
k slots and silently inflates every score below.
"""


def required_paragraphs(question):
    """Paragraph ids that must be retrieved to answer `question`.

    [] for negatives (nothing to retrieve), a one-element list for a single
    citation, the full list for a multi-paragraph citation.
    """
    citation = question.get("expected_citation")
    if not citation:
        return []
    if "paragraph_ids" in citation:
        return list(citation["paragraph_ids"])
    return [citation["paragraph_id"]]


def per_paragraph_recall(questions, retrieved_by_qid, k):
    """Macro-averaged recall over answerable (non-negative) questions.

    Each question's own hit fraction (required retrieved / required) is
    computed first; those per-question fractions are then averaged with
    equal weight. This is NOT pooling hits and requirements globally - a
    question with five required paragraphs does not get five times the
    weight of a single-citation question.
    """
    scores = []
    for question in questions:
        required = required_paragraphs(question)
        if not required:
            continue
        retrieved_k = set(retrieved_by_qid.get(question["id"], [])[:k])
        hits = sum(1 for pid in required if pid in retrieved_k)
        scores.append(hits / len(required))
    return sum(scores) / len(scores) if scores else 0.0


def strict_completeness(questions, retrieved_by_qid, k):
    """Fraction of multi-paragraph questions whose full required set is met.

    Only questions with more than one required paragraph are scored; a
    single-citation question can't be "complete" or "incomplete", so it's
    excluded rather than trivially counted as a pass.
    """
    scores = []
    for question in questions:
        required = required_paragraphs(question)
        if len(required) <= 1:
            continue
        retrieved_k = set(retrieved_by_qid.get(question["id"], [])[:k])
        scores.append(1.0 if all(pid in retrieved_k for pid in required) else 0.0)
    return sum(scores) / len(scores) if scores else 0.0
