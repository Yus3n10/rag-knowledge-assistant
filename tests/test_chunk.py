from scripts.rag.chunk import chunk_records

SECTION = {
    "section_id": "1910.147",
    "section_heading": "The control of hazardous energy (lockout/tagout).",
    "records": [
        {"paragraph_id": "1910.147(e)(3)", "text": "Each device shall be removed by the employee who applied it.",
         "tables": [], "parent_headings": [{"paragraph_id": "1910.147(e)", "text": "Release from lockout or tagout."}]},
        {"paragraph_id": "1910.147(x)", "text": "Table paragraph.",
         "tables": ["| Type | APF |\n| --- | --- |\n| Full facepiece | 50 |"], "parent_headings": []},
    ],
}


def test_chunk_text_carries_the_heading_trail():
    chunks = chunk_records(SECTION, "Subpart J", "General Environmental Controls")

    first = chunks[0]
    assert first["chunk_id"] == "1910.147(e)(3)"
    assert "The control of hazardous energy" in first["text"]
    assert "Release from lockout or tagout." in first["text"]
    assert "removed by the employee who applied it" in first["text"]


def test_table_content_is_appended_to_its_paragraph_chunk():
    chunks = chunk_records(SECTION, "Subpart J", "General Environmental Controls")

    table_chunk = [c for c in chunks if c["paragraph_id"] == "1910.147(x)"][0]
    # the APF value lives only in the table; it must survive into the chunk text
    assert "50" in table_chunk["text"]
    assert "Full facepiece" in table_chunk["text"]


def test_oversized_paragraph_splits_with_the_trail_repeated():
    big = {
        "section_id": "1910.140",
        "section_heading": "Personal fall protection systems.",
        "records": [{"paragraph_id": "1910.140(b)", "tables": [], "parent_headings": [],
                     "text": " ".join(f"Term{i} means definition number {i}." for i in range(400))}],
    }

    chunks = chunk_records(big, "Subpart I", "Personal Protective Equipment")

    assert len(chunks) > 1
    assert [c["chunk_id"] for c in chunks] == [f"1910.140(b)#{i}" for i in range(len(chunks))]
    assert all("Personal fall protection systems." in c["text"] for c in chunks)
    assert all(c["paragraph_id"] == "1910.140(b)" for c in chunks)
    assert all(len(c["text"]) <= 2400 for c in chunks)
