from pathlib import Path

from scripts.osha.discover import section_ids_from_subpart

FIXTURES = Path(__file__).parent / "fixtures"


def test_lists_subpart_d_sections_in_numeric_order():
    html = (FIXTURES / "1910SubpartD.html").read_text(encoding="utf-8")

    assert section_ids_from_subpart(html) == [
        "1910.21", "1910.22", "1910.23", "1910.24", "1910.25",
        "1910.26", "1910.27", "1910.28", "1910.29", "1910.30",
    ]
