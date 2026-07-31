from pathlib import Path

from scripts.osha.parse import parse_section

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_section_identity():
    section_id, heading, records = parse_section(load("1910.147.html"))

    assert section_id == "1910.147"
    assert heading == "The control of hazardous energy (lockout/tagout)."
    assert len(records) > 100


def test_paragraph_ids_are_native_osha_ids():
    _, _, records = parse_section(load("1910.147.html"))
    ids = [r["paragraph_id"] for r in records]

    assert "1910.147(a)(1)(i)" in ids
    assert all(i.startswith("1910.147") for i in ids)


def test_paragraph_text_is_clean_prose():
    _, _, records = parse_section(load("1910.147.html"))
    by_id = {r["paragraph_id"]: r for r in records}

    text = by_id["1910.147(a)(1)(ii)"]["text"]
    assert text == "This standard does not cover the following:"


def test_tables_are_extracted_as_markdown_not_flattened_into_text():
    _, _, records = parse_section(load("1910.134.html"))
    with_tables = [r for r in records if r["tables"]]

    assert with_tables, "expected at least one paragraph carrying a table"
    markdown = with_tables[0]["tables"][0]
    assert markdown.startswith("**Table 1")
    assert "| --- |" in markdown
    # the table's numbers must NOT have leaked into the prose text
    assert "Quarter mask" not in with_tables[0]["text"]
