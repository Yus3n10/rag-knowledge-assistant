from scripts.osha.render import render_subpart_markdown


def test_renders_section_headings_and_visible_paragraph_ids():
    sections = [{
        "section_id": "1910.23",
        "section_heading": "Ladders.",
        "records": [
            {"paragraph_id": "1910.23(b)", "text": "General requirements.", "tables": []},
            {"paragraph_id": "1910.23(b)(2)", "text": "Rungs spaced 10 inches.", "tables": []},
        ],
    }]

    markdown = render_subpart_markdown("Subpart D - Walking-Working Surfaces", sections)

    assert markdown.startswith("# Subpart D - Walking-Working Surfaces\n")
    assert "## 1910.23 - Ladders." in markdown
    assert "**1910.23(b)(2)**" in markdown
    assert "Rungs spaced 10 inches." in markdown


def test_each_paragraph_id_is_adjacent_to_its_own_text():
    sections = [{
        "section_id": "1910.23",
        "section_heading": "Ladders.",
        "records": [
            {"paragraph_id": "1910.23(b)(1)", "text": "First requirement.", "tables": []},
            {"paragraph_id": "1910.23(b)(2)", "text": "Second requirement.", "tables": []},
        ],
    }]

    markdown = render_subpart_markdown("Subpart D - Walking-Working Surfaces", sections)

    assert "**1910.23(b)(1)**\n\nFirst requirement." in markdown
    assert "**1910.23(b)(2)**\n\nSecond requirement." in markdown


def test_includes_tables_below_their_paragraph():
    sections = [{
        "section_id": "1910.134",
        "section_heading": "Respiratory protection.",
        "records": [{
            "paragraph_id": "1910.134(d)(3)(i)(A)",
            "text": "Employers must use the assigned protection factors.",
            "tables": ["**Table 1**\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"],
        }],
    }]

    markdown = render_subpart_markdown("Subpart I - PPE", sections)

    assert "| A | B |" in markdown
    assert markdown.index("assigned protection factors") < markdown.index("| A | B |")
