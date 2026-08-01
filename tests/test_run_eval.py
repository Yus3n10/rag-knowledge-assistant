from eval.run_eval import dedupe_paragraphs, find_first_chunk_with_number, is_table_chunk


def chunk(paragraph_id, text="", distance=0.0):
    return {"chunk_id": f"{paragraph_id}#stub", "paragraph_id": paragraph_id,
            "text": text, "distance": distance}


def test_dedup_preserves_first_seen_order():
    chunks = [chunk("1910.147(e)(3)"), chunk("1910.147(c)(1)"), chunk("1910.147(e)(3)")]

    assert dedupe_paragraphs(chunks, k=5) == ["1910.147(e)(3)", "1910.147(c)(1)"]


def test_split_paragraph_does_not_consume_multiple_k_slots():
    # 1910.21(b) split into two chunks (as chunk_id "1910.21(b)#0"/"#3" would),
    # both mapping to the same paragraph_id; without dedup this would occupy
    # 2 of 3 slots that should hold 3 distinct paragraphs.
    chunks = [chunk("1910.21(b)"), chunk("A"), chunk("1910.21(b)"), chunk("B"), chunk("C")]

    result = dedupe_paragraphs(chunks, k=3)

    assert result == ["1910.21(b)", "A", "B"]
    assert len(result) == 3


def test_truncates_to_k_after_dedup_not_before():
    # 6 raw chunks collapse to 4 distinct paragraphs; k=3 keeps only the first 3 distinct
    chunks = [chunk("P1"), chunk("P1"), chunk("P2"), chunk("P3"), chunk("P3"), chunk("P4")]

    assert dedupe_paragraphs(chunks, k=3) == ["P1", "P2", "P3"]


def test_k_is_a_prefix_relationship_across_k_values():
    # dedupe to k=5 then slicing to k=2 must equal deduping straight to k=2 -
    # this is what lets one overfetch serve every k in K_VALUES.
    chunks = [chunk("P1"), chunk("P1"), chunk("P2"), chunk("P3"), chunk("P2"), chunk("P4")]

    assert dedupe_paragraphs(chunks, k=5)[:2] == dedupe_paragraphs(chunks, k=2)


def test_fewer_distinct_paragraphs_than_k_returns_what_is_available():
    chunks = [chunk("P1"), chunk("P1"), chunk("P2")]

    assert dedupe_paragraphs(chunks, k=5) == ["P1", "P2"]


def test_find_first_chunk_with_number_matches_standalone_number_only():
    chunks = [
        chunk("A", text="employers must use Table 1"),
        chunk("B", text="a value of 150 applies here"),
        chunk("C", text="| Full facepiece | 50 |\n| --- |"),
    ]

    assert find_first_chunk_with_number(chunks, "50") == 3


def test_find_first_chunk_with_number_returns_none_when_absent():
    chunks = [chunk("A", text="no numbers of interest"), chunk("B", text="still none")]

    assert find_first_chunk_with_number(chunks, "50") is None


def test_is_table_chunk_detects_markdown_separator():
    assert is_table_chunk("| a | b |\n| --- | --- |\n| 1 | 2 |") is True
    assert is_table_chunk("plain prose, no table here") is False
