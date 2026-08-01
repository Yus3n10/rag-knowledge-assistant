from scripts.rag.ground import extract_citations, validate_citations, ungrounded_numbers


# --- extract_citations ---------------------------------------------------

def test_extracts_real_complex_id():
    answer = "Only the employee who applied it may remove it. [1910.134(d)(3)(i)(A)]"
    assert extract_citations(answer) == ["1910.134(d)(3)(i)(A)"]


def test_extracts_multiple_deduplicated_order_preserved():
    answer = (
        "First point [1910.147(e)(3)]. Second point [1910.29(b)(1)]. "
        "Repeat of first [1910.147(e)(3)]."
    )
    assert extract_citations(answer) == ["1910.147(e)(3)", "1910.29(b)(1)"]


def test_no_citations_returns_empty_list():
    answer = "The provided text does not contain this information."
    assert extract_citations(answer) == []


def test_ignores_bracketed_text_that_is_not_a_paragraph_id():
    answer = "The table caption reads TABLE I. - ASSIGNED PROTECTION FACTORS [RESERVED] per [1910.134(d)(3)(i)(A)]."

    assert extract_citations(answer) == ["1910.134(d)(3)(i)(A)"]


def test_ignores_a_bracketed_federal_register_citation():
    answer = "See [59 FR 16362, April 6, 1994; 61 FR 9227, March 7, 1996] and [1910.147(e)(3)]."

    assert extract_citations(answer) == ["1910.147(e)(3)"]


def test_still_extracts_a_fabricated_but_id_shaped_citation():
    # fabrication detection must survive the filter - this id does not exist in the corpus
    assert extract_citations("As stated in [1910.999(z)].") == ["1910.999(z)"]


# --- validate_citations ---------------------------------------------------

def test_retrieved_citation_is_valid():
    result = validate_citations(["1910.147(e)(3)"], ["1910.147(e)(3)", "1910.29(b)(1)"])
    assert result["valid"] == ["1910.147(e)(3)"]
    assert result["not_retrieved"] == []
    assert result["not_in_corpus"] == []


def test_in_corpus_but_not_retrieved():
    result = validate_citations(
        ["1910.147(c)(1)"],
        retrieved_paragraph_ids=["1910.147(e)(3)"],
        corpus_paragraph_ids={"1910.147(e)(3)", "1910.147(c)(1)"},
    )
    assert result["not_retrieved"] == ["1910.147(c)(1)"]
    assert result["valid"] == []
    assert result["not_in_corpus"] == []


def test_fabricated_id_not_in_corpus():
    result = validate_citations(
        ["1910.999(z)(9)"],
        retrieved_paragraph_ids=["1910.147(e)(3)"],
        corpus_paragraph_ids={"1910.147(e)(3)", "1910.147(c)(1)"},
    )
    assert result["not_in_corpus"] == ["1910.999(z)(9)"]
    assert result["valid"] == []
    assert result["not_retrieved"] == []


def test_without_corpus_set_everything_unretrieved_is_not_retrieved():
    result = validate_citations(["1910.999(z)(9)"], ["1910.147(e)(3)"])
    assert result["not_retrieved"] == ["1910.999(z)(9)"]
    assert result["not_in_corpus"] == []


# --- ungrounded_numbers ----------------------------------------------------

def test_number_absent_from_context_is_flagged():
    answer = "The top rail must be 42 inches high."
    context = "The top edge height shall be 39 inches."
    assert ungrounded_numbers(answer, context) == ["42"]


def test_numbers_all_present_returns_empty():
    answer = "The top rail must be 42 inches high."
    context = "The top edge height shall be 42 inches."
    assert ungrounded_numbers(answer, context) == []


def test_comma_forms_treated_as_equal_both_directions():
    answer_comma = "The fine may be up to $1,000."
    context_plain = "penalties may reach 1000 dollars."
    assert ungrounded_numbers(answer_comma, context_plain) == []

    answer_plain = "The fine may be up to 1000 dollars."
    context_comma = "penalties may reach $1,000."
    assert ungrounded_numbers(answer_plain, context_comma) == []


def test_numbers_only_in_citation_brackets_not_flagged():
    answer = "Only the employee who applied it may remove it. [1910.147(e)(3)]"
    context = "Only the employee who applied the device may remove it."
    assert ungrounded_numbers(answer, context) == []
