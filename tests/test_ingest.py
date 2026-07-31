import json
from pathlib import Path

from scripts.ingest_osha import SUBPARTS, build_corpus, resolve_sections

FIXTURES = Path(__file__).parent / "fixtures"


class StubSession:
    """Serves fixtures matched by exact URL suffix; errors on anything else."""

    def __init__(self):
        self.calls = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append(url)
        if url.endswith("SubpartD"):
            name = "1910SubpartD.html"
        elif url.endswith("1910.134"):
            name = "1910.134.html"
        elif url.endswith("1910.147"):
            name = "1910.147.html"
        else:
            raise ValueError(f"StubSession has no fixture for {url}")
        return type("R", (), {
            "text": (FIXTURES / name).read_text(encoding="utf-8"),
            "raise_for_status": lambda self: None,
        })()


def test_builds_subpart_payload_with_records_and_headings(tmp_path):
    subpart = {
        "subpart": "Subpart J",
        "subpart_name": "General Environmental Controls",
        "slug": "subpart-j-lockout-tagout",
        "sections": ["1910.147"],
    }

    payload = build_corpus(subpart, tmp_path, session=StubSession(), delay=0)

    assert payload["subpart"] == "Subpart J"
    section = payload["sections"][0]
    assert section["section_id"] == "1910.147"
    assert len(section["records"]) > 100
    child = next(r for r in section["records"] if r["paragraph_id"] == "1910.147(a)(1)(i)")
    assert [h["paragraph_id"] for h in child["parent_headings"]] == [
        "1910.147(a)", "1910.147(a)(1)",
    ]


def test_writes_json_and_markdown_and_caches_raw_html(tmp_path):
    subpart = {
        "subpart": "Subpart J",
        "subpart_name": "General Environmental Controls",
        "slug": "subpart-j-lockout-tagout",
        "sections": ["1910.147"],
    }

    build_corpus(subpart, tmp_path, session=StubSession(), delay=0)

    assert (tmp_path / "raw" / "1910.147.html").exists()
    assert (tmp_path / "corpus" / "subpart-j-lockout-tagout.md").exists()
    written = json.loads((tmp_path / "corpus" / "subpart-j-lockout-tagout.json").read_text(encoding="utf-8"))
    assert written["sections"][0]["section_id"] == "1910.147"


def test_subpart_j_is_scoped_to_lockout_tagout_only():
    subpart_j = next(s for s in SUBPARTS if s["subpart"] == "Subpart J")
    assert subpart_j["sections"] == ["1910.147"]


def test_records_source_urls_for_subpart_and_its_sections(tmp_path):
    subpart = {
        "subpart": "Subpart J",
        "subpart_name": "General Environmental Controls",
        "slug": "subpart-j-lockout-tagout",
        "sections": ["1910.147"],
    }

    payload = build_corpus(subpart, tmp_path, session=StubSession(), delay=0)

    base = "https://www.osha.gov/laws-regs/regulations/standardnumber/1910"
    assert payload["source_url"] == f"{base}/1910.147"
    assert payload["sections"][0]["source_url"] == f"{base}/1910.147"


def test_discovers_sections_when_subpart_config_has_an_index(tmp_path):
    subpart = {
        "subpart": "Subpart D",
        "subpart_name": "Walking-Working Surfaces",
        "slug": "subpart-d-walking-working-surfaces",
        "sections": ["1910.134", "1910.147"],
    }

    payload = build_corpus(subpart, tmp_path, session=StubSession(), delay=0)

    assert len(payload["sections"]) == 2
    assert [s["section_id"] for s in payload["sections"]] == ["1910.134", "1910.147"]


def test_resolve_sections_discovers_ids_from_index(tmp_path):
    subpart = {
        "subpart": "Subpart D",
        "subpart_name": "Walking-Working Surfaces",
        "slug": "subpart-d-walking-working-surfaces",
        "index": "1910SubpartD",
    }

    section_ids = resolve_sections(subpart, tmp_path, session=StubSession(), delay=0)

    # The real Subpart D index fixture lists 1910.21-1910.30
    assert len(section_ids) == 10
