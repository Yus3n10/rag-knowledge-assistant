from eval.run_answers import (
    citation_validity_rate,
    gold_citation_rate,
    ungrounded_number_rate,
    fabricated_citation_count,
    resp001_detail,
)


def record(id, category, *, required=None, citations=None, valid=None,
           not_retrieved=None, not_in_corpus=None, ungrounded=None,
           answer="", retrieved_text=""):
    return {
        "id": id,
        "category": category,
        "answer": answer,
        "required": required or [],
        "citations": citations or [],
        "citation_report": {
            "valid": valid or [], "not_retrieved": not_retrieved or [],
            "not_in_corpus": not_in_corpus or [],
        },
        "ungrounded_numbers": ungrounded or [],
        "retrieved_text": retrieved_text,
    }


# --- citation_validity_rate (over answerable questions only) --------------

def test_citation_validity_rate_pools_valid_over_all_emitted_citations():
    records = [
        record("q1", "numeric_lookup", citations=["A", "B"], valid=["A", "B"]),
        record("q2", "procedural", citations=["C", "D"], valid=["C"], not_retrieved=["D"]),
        # negative question with a citation must be excluded from this rate
        record("neg1", "negative", citations=["X"], not_in_corpus=["X"]),
    ]

    assert citation_validity_rate(records) == 3 / 4


def test_citation_validity_rate_zero_when_no_citations_emitted():
    records = [record("q1", "numeric_lookup")]
    assert citation_validity_rate(records) == 0.0


# --- gold_citation_rate (over answerable questions only) -------------------

def test_gold_citation_rate_counts_questions_citing_any_required_paragraph():
    records = [
        record("q1", "numeric_lookup", required=["A"], citations=["A", "B"]),
        record("q2", "procedural", required=["C"], citations=["D"]),
        record("neg1", "negative", required=[], citations=[]),
    ]

    assert gold_citation_rate(records) == 1 / 2


def test_gold_citation_rate_zero_when_no_answerable_questions():
    assert gold_citation_rate([record("neg1", "negative")]) == 0.0


# --- ungrounded_number_rate (over numeric_lookup only) ---------------------

def test_ungrounded_number_rate_over_numeric_lookup_only():
    records = [
        record("q1", "numeric_lookup", ungrounded=["42"]),
        record("q2", "numeric_lookup", ungrounded=[]),
        record("q3", "numeric_lookup", ungrounded=[]),
        record("q4", "procedural", ungrounded=["99"]),  # excluded: not numeric_lookup
    ]

    assert ungrounded_number_rate(records) == 1 / 3


def test_ungrounded_number_rate_zero_when_no_numeric_questions():
    assert ungrounded_number_rate([record("q1", "procedural")]) == 0.0


# --- fabricated_citation_count (over ALL questions) -------------------------

def test_fabricated_citation_count_sums_not_in_corpus_across_all_questions():
    records = [
        record("q1", "numeric_lookup", not_in_corpus=["A"]),
        record("neg1", "negative", not_in_corpus=["B", "C"]),
        record("q2", "procedural"),
    ]

    assert fabricated_citation_count(records) == 3


# --- resp001_detail ----------------------------------------------------------

def test_resp001_detail_reports_the_three_planted_regression_facts():
    records = [
        record(
            "resp-001", "numeric_lookup",
            answer="The assigned protection factor is 50 [1910.134(d)(3)(i)(A)].",
            citations=["1910.134(d)(3)(i)(A)"],
            retrieved_text="| Full facepiece | 50 |\n| --- |",
        ),
    ]

    detail = resp001_detail(records)

    assert detail["answer_contains_50"] is True
    assert detail["cited_expected_paragraph"] is True
    assert detail["context_contains_50"] is True


def test_resp001_detail_flags_when_50_is_absent_everywhere():
    records = [
        record("resp-001", "numeric_lookup",
               answer="The provided text does not contain this information.",
               citations=[], retrieved_text="no relevant numbers here"),
    ]

    detail = resp001_detail(records)

    assert detail["answer_contains_50"] is False
    assert detail["cited_expected_paragraph"] is False
    assert detail["context_contains_50"] is False
