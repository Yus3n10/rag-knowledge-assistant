from eval.metrics import per_paragraph_recall, strict_completeness, required_paragraphs


def q(qid, category, **cite):
    return {"id": qid, "category": category, "expected_citation": cite or None}


def test_negative_questions_have_no_required_paragraphs():
    assert required_paragraphs({"id": "n1", "category": "negative",
                                "expected_citation": None}) == []


def test_recall_is_macro_averaged_not_micro_averaged():
    # one single-gold question, fully hit; one five-gold question, one of five hit.
    questions = [
        q("single", "numeric_lookup", paragraph_id="A"),
        q("multi", "procedural", paragraph_ids=["B", "C", "D", "E", "F"]),
    ]
    retrieved = {"single": ["A"], "multi": ["B"]}

    # macro: (1.0 + 0.2) / 2 = 0.6
    # micro would be 2 hits / 6 golds = 0.333 - this test fails under micro
    assert per_paragraph_recall(questions, retrieved, k=5) == 0.6


def test_negatives_are_excluded_from_recall_not_scored_as_zero():
    questions = [
        q("single", "numeric_lookup", paragraph_id="A"),
        {"id": "neg", "category": "negative", "expected_citation": None},
    ]
    retrieved = {"single": ["A"], "neg": ["Z"]}

    assert per_paragraph_recall(questions, retrieved, k=5) == 1.0


def test_strict_completeness_requires_every_gold_and_ignores_single_gold_questions():
    questions = [
        q("single", "numeric_lookup", paragraph_id="A"),
        q("m1", "procedural", paragraph_ids=["B", "C"]),
        q("m2", "conditional", paragraph_ids=["D", "E"]),
    ]
    retrieved = {"single": ["A"], "m1": ["B", "C"], "m2": ["D", "X"]}

    assert strict_completeness(questions, retrieved, k=5) == 0.5


def test_recall_only_counts_the_first_k_retrieved():
    questions = [q("single", "numeric_lookup", paragraph_id="A")]

    assert per_paragraph_recall(questions, {"single": ["X", "Y", "Z", "W", "V", "A"]}, k=5) == 0.0
