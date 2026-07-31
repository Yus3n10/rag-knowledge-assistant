from eval.validate_eval import validate

KNOWN = {"1910.147(e)(3)", "1910.23(b)(2)"}


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
