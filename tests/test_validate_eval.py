from pathlib import Path

from eval.validate_eval import load_corpus_index, load_questions, validate

KNOWN = {
    "1910.147(e)(3)": {
        "subpart": "Subpart J",
        "section_id": "1910.147",
        "text": "Each lockout or tagout device shall be removed by the employee who applied it.",
    },
    "1910.23(b)(2)": {
        "subpart": "Subpart D",
        "section_id": "1910.23",
        "text": "Ladder rungs are spaced not less than 10 inches and not more than 14 inches apart.",
    },
}


def good(**overrides):
    q = {
        "id": "loto-001",
        "question": "What must be verified before removing a lockout device?",
        "category": "procedural",
        "expected_answer": "The machine is shut down and employees are clear.",
        "expected_citation": {
            "subpart": "Subpart J",
            "section_id": "1910.147",
            "paragraph_id": "1910.147(e)(3)",
        },
        "notes": "",
    }
    q.update(overrides)
    return q


def test_accepts_a_valid_question():
    assert validate([good()], KNOWN) == []


def test_rejects_citation_not_present_in_corpus():
    q = good(expected_citation={
        "subpart": "Subpart J", "section_id": "1910.147",
        "paragraph_id": "1910.147(z)(99)",
    })

    errors = validate([q], KNOWN)

    assert any("1910.147(z)(99)" in e for e in errors)


def test_rejects_duplicate_ids():
    errors = validate([good(), good()], KNOWN)

    assert any("duplicate id" in e.lower() for e in errors)


def test_rejects_unknown_category():
    errors = validate([good(category="trick_question")], KNOWN)

    assert any("category" in e.lower() for e in errors)


def test_negative_question_requires_notes_and_no_citation():
    missing_notes = good(id="neg-001", category="negative",
                         expected_citation=None, notes="")

    errors = validate([missing_notes], KNOWN)

    assert any("notes" in e.lower() for e in errors)


def test_negative_question_must_not_carry_a_citation():
    q = good(id="neg-002", category="negative", notes="Forklift training is in 1910.178, not in scope.")

    errors = validate([q], KNOWN)

    assert any("expected_citation" in e for e in errors)


def test_composition_check_flags_skewed_mix():
    questions = [good(id=f"q-{i}") for i in range(20)]  # 100% procedural

    errors = validate(questions, KNOWN, check_composition=True)

    assert any("composition" in e.lower() for e in errors)


def test_reports_citation_missing_paragraph_id_instead_of_crashing():
    q = good(expected_citation={"subpart": "Subpart J", "section_id": "1910.147"})

    errors = validate([q], KNOWN)

    assert any("missing paragraph_id" in e for e in errors)


def test_rejects_empty_expected_answer_on_non_negative_question():
    errors = validate([good(expected_answer="   ")], KNOWN)

    assert any("expected_answer" in e for e in errors)


def test_allows_empty_expected_answer_on_negative_question():
    q = good(id="neg-010", category="negative", expected_citation=None,
             expected_answer="", notes="Forklift training lives in 1910.178, out of corpus.")

    assert validate([q], KNOWN) == []


def test_rejects_citation_naming_the_wrong_section():
    q = good(expected_citation={
        "subpart": "Subpart J", "section_id": "1910.23",
        "paragraph_id": "1910.147(e)(3)",
    })

    errors = validate([q], KNOWN)

    assert any("says section 1910.23" in e for e in errors)


def test_rejects_citation_naming_the_wrong_subpart():
    q = good(expected_citation={
        "subpart": "Subpart D", "section_id": "1910.147",
        "paragraph_id": "1910.147(e)(3)",
    })

    errors = validate([q], KNOWN)

    assert any("says Subpart D" in e for e in errors)


def test_rejects_numeric_answer_whose_number_is_absent_from_the_cited_paragraph():
    q = good(id="ladder-001", category="numeric_lookup",
             expected_answer="Rungs are spaced not more than 40 inches apart.",
             expected_citation={
                 "subpart": "Subpart D", "section_id": "1910.23",
                 "paragraph_id": "1910.23(b)(2)",
             })

    errors = validate([q], KNOWN)

    assert any("40" in e and "do not appear" in e for e in errors)


def test_accepts_numeric_answer_whose_numbers_appear_in_the_cited_paragraph():
    q = good(id="ladder-002", category="numeric_lookup",
             expected_answer="Not less than 10 inches and not more than 14 inches.",
             expected_citation={
                 "subpart": "Subpart D", "section_id": "1910.23",
                 "paragraph_id": "1910.23(b)(2)",
             })

    assert validate([q], KNOWN) == []


def test_rejects_empty_question_text():
    errors = validate([good(question="  ")], KNOWN)

    assert any("question text" in e for e in errors)


def test_real_question_set_validates_against_the_real_corpus():
    root = Path(__file__).resolve().parent.parent

    questions = load_questions(root / "eval" / "questions.jsonl")
    corpus_index = load_corpus_index(root / "data" / "corpus")

    assert validate(questions, corpus_index) == []


def test_malformed_jsonl_names_the_offending_line(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text('{"id": "ok"}\n{"id": "broken",}\n', encoding="utf-8")

    try:
        load_questions(path)
    except ValueError as exc:
        assert ":2:" in str(exc)
    else:
        raise AssertionError("expected ValueError naming line 2")
