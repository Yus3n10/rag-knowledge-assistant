import json
import re
from pathlib import Path

from scripts.rag.chunk import chunk_records

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"

# Independent (test-owned) patterns for "does this piece open at a defined term",
# deliberately not imported from chunk.py so the test pins real output rather than
# re-checking the implementation's own regex against itself.
OPENS_AT_MEANS_TERM = re.compile(
    r"^(Definitions\b|[A-Z][A-Za-z0-9()/'\-]*(?:\s+[A-Za-z0-9()/'\-]+){0,6}\s+means\b)"
)
OPENS_AT_PERIOD_TERM = re.compile(
    r"^[A-Z][A-Za-z0-9()/'\-]*(?:\s+[a-zA-Z0-9()/'\-]+){0,6}\s*\."
)


def load_section_for(paragraph_id, filename):
    """Load the real corpus section containing paragraph_id, for TDD tests that must
    pin actual chunker behavior on real corpus text rather than a synthetic approximation."""
    payload = json.loads((CORPUS_DIR / filename).read_text(encoding="utf-8"))
    for section in payload["sections"]:
        for record in section["records"]:
            if record["paragraph_id"] == paragraph_id:
                return section, payload["subpart"], payload["subpart_name"]
    raise AssertionError(f"{paragraph_id} not found in {filename}")


def piece_body(chunk):
    """The chunk text with the 'heading_trail\\n\\n' prefix stripped off."""
    return chunk["text"].split("\n\n", 1)[1]


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


# --- Defect A/B: definition-aware splitting on real corpus paragraphs -------------

def test_1910_21b_every_piece_opens_at_a_defined_term():
    """Defect A: 1910.21(b) (60 'means' definitions) piece 4 used to open mid-
    'Rope descent system means ...', stranded from its opener sentence."""
    section, subpart, subpart_name = load_section_for(
        "1910.21(b)", "subpart-d-walking-working-surfaces.json")
    chunks = chunk_records(section, subpart, subpart_name)
    pieces = [c for c in chunks if c["paragraph_id"] == "1910.21(b)"]

    assert len(pieces) > 1, "expected 1910.21(b) to still split (it is far over budget)"
    for piece in pieces:
        body = piece_body(piece)
        assert OPENS_AT_MEANS_TERM.match(body), f"piece opens mid-definition: {body[:80]!r}"


def test_1910_147b_every_piece_opens_at_a_defined_term():
    """Defect B: 1910.147(b) uses 'Term . Definition', not 'Term means ...' (only 3
    ordinary, non-defining occurrences of 'means'). Old pieces 1 and 2 opened mid-
    'Hot tap' and mid-'Tagout device'."""
    section, subpart, subpart_name = load_section_for(
        "1910.147(b)", "subpart-j-lockout-tagout.json")
    chunks = chunk_records(section, subpart, subpart_name)
    pieces = [c for c in chunks if c["paragraph_id"] == "1910.147(b)"]

    assert len(pieces) > 1, "expected 1910.147(b) to still split (it is over budget)"
    for piece in pieces:
        body = piece_body(piece)
        assert OPENS_AT_PERIOD_TERM.match(body), f"piece opens mid-definition: {body[:80]!r}"


# --- Defect C: tables are atomic, one chunk per table -----------------------------

def test_1910_137_yields_one_table_chunk_per_table():
    section, subpart, subpart_name = load_section_for(
        "1910.137(c)(2)(xii)", "subpart-i-personal-protective-equipment.json")
    raw_tables = next(r["tables"] for r in section["records"]
                       if r["paragraph_id"] == "1910.137(c)(2)(xii)")
    assert len(raw_tables) == 5  # sanity check on the fixture claim

    chunks = chunk_records(section, subpart, subpart_name)
    table_chunks = [c for c in chunks
                    if c["paragraph_id"] == "1910.137(c)(2)(xii)" and c["kind"] == "table"]

    assert len(table_chunks) == 5


def test_1910_137_no_chunk_has_table_data_rows_without_that_tables_header():
    section, subpart, subpart_name = load_section_for(
        "1910.137(c)(2)(xii)", "subpart-i-personal-protective-equipment.json")
    raw_tables = next(r["tables"] for r in section["records"]
                       if r["paragraph_id"] == "1910.137(c)(2)(xii)")

    chunks = chunk_records(section, subpart, subpart_name)
    table_chunks = [c for c in chunks
                    if c["paragraph_id"] == "1910.137(c)(2)(xii)" and c["kind"] == "table"]

    for raw_table in raw_tables:
        rows = raw_table.splitlines()
        header_row = rows[0]
        data_rows = [r for r in rows[2:] if r.strip()]

        # every chunk that carries any of this table's data rows must also carry its header
        for data_row in data_rows:
            for chunk in table_chunks:
                if data_row in chunk["text"]:
                    assert header_row in chunk["text"], (
                        f"chunk has a data row with no header: {data_row!r}")


def test_1910_134_apf_table_chunk_contains_the_planted_regression_value():
    """resp-001 is a planted regression test: APF 50 exists only in
    1910.134(d)(3)(i)(A)'s table, never in record['text']."""
    section, subpart, subpart_name = load_section_for(
        "1910.134(d)(3)(i)(A)", "subpart-i-personal-protective-equipment.json")
    chunks = chunk_records(section, subpart, subpart_name)
    table_chunks = [c for c in chunks
                    if c["paragraph_id"] == "1910.134(d)(3)(i)(A)" and c["kind"] == "table"]

    assert table_chunks
    assert any("50" in c["text"] for c in table_chunks)


# --- Cross-cutting: kind key and paragraph_id stability ----------------------------

def test_every_chunk_has_a_kind_of_prose_or_table():
    section, subpart, subpart_name = load_section_for(
        "1910.137(c)(2)(xii)", "subpart-i-personal-protective-equipment.json")
    chunks = chunk_records(section, subpart, subpart_name)

    assert chunks
    assert all(c["kind"] in ("prose", "table") for c in chunks)


def test_chunks_carry_paragraph_id_unchanged():
    for filename in ["subpart-d-walking-working-surfaces.json",
                      "subpart-i-personal-protective-equipment.json",
                      "subpart-j-lockout-tagout.json"]:
        payload = json.loads((CORPUS_DIR / filename).read_text(encoding="utf-8"))
        for section in payload["sections"]:
            chunks = chunk_records(section, payload["subpart"], payload["subpart_name"])
            paragraph_ids = {r["paragraph_id"] for r in section["records"]}
            for chunk in chunks:
                assert chunk["paragraph_id"] in paragraph_ids
