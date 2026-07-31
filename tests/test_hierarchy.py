from scripts.osha.hierarchy import ancestor_ids, attach_parent_headings


def test_ancestor_ids_peels_trailing_groups():
    assert ancestor_ids("1910.147(a)(1)(i)") == [
        "1910.147",
        "1910.147(a)",
        "1910.147(a)(1)",
    ]


def test_ancestor_ids_of_top_level_paragraph():
    assert ancestor_ids("1910.147(a)") == ["1910.147"]


def test_attaches_only_resolvable_ancestors_outermost_first():
    records = [
        {"paragraph_id": "1910.23(b)", "text": "General requirements for all ladders."},
        {"paragraph_id": "1910.23(b)(2)(i)", "text": "Rungs must be spaced 6 inches apart."},
    ]

    result = attach_parent_headings(records)
    child = result[1]

    # 1910.23(b)(2) has no standalone block, so it is skipped, not faked
    assert child["parent_headings"] == [
        {"paragraph_id": "1910.23(b)", "text": "General requirements for all ladders."}
    ]


def test_truncates_long_heading_text():
    records = [
        {"paragraph_id": "1910.147(a)", "text": "x" * 300},
        {"paragraph_id": "1910.147(a)(1)", "text": "child"},
    ]

    result = attach_parent_headings(records)

    assert len(result[1]["parent_headings"][0]["text"]) == 120
