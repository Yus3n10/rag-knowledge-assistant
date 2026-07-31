"""Scrape and structure the OSHA 29 CFR 1910 corpus (Subparts D, I, and 1910.147)."""

import json
from pathlib import Path

from scripts.osha.discover import section_ids_from_subpart
from scripts.osha.fetch import fetch_html
from scripts.osha.hierarchy import attach_parent_headings
from scripts.osha.parse import parse_section
from scripts.osha.render import render_subpart_markdown

BASE_URL = "https://www.osha.gov/laws-regs/regulations/standardnumber/1910"

SUBPARTS = [
    {
        "subpart": "Subpart D",
        "subpart_name": "Walking-Working Surfaces",
        "slug": "subpart-d-walking-working-surfaces",
        "index": "1910SubpartD",
    },
    {
        "subpart": "Subpart I",
        "subpart_name": "Personal Protective Equipment",
        "slug": "subpart-i-personal-protective-equipment",
        "index": "1910SubpartI",
    },
    {
        # Scoped deliberately: Subpart J as a whole is out of scope, only 1910.147.
        "subpart": "Subpart J",
        "subpart_name": "General Environmental Controls",
        "slug": "subpart-j-lockout-tagout",
        "sections": ["1910.147"],
    },
]


def resolve_sections(subpart, data_dir, *, session, delay):
    if "sections" in subpart:
        return subpart["sections"]
    index_url = f"{BASE_URL}/{subpart['index']}"
    html = fetch_html(index_url, data_dir / "raw" / f"{subpart['index']}.html",
                      session=session, delay=delay)
    return section_ids_from_subpart(html)


def build_corpus(subpart, data_dir, *, session=None, delay=1.0):
    data_dir = Path(data_dir)
    section_ids = resolve_sections(subpart, data_dir, session=session, delay=delay)
    if not section_ids:
        raise ValueError(f"no sections resolved for {subpart['subpart']}")

    sections = []
    for section_id in section_ids:
        url = f"{BASE_URL}/{section_id}"
        html = fetch_html(url, data_dir / "raw" / f"{section_id}.html",
                          session=session, delay=delay)
        parsed_id, heading, records = parse_section(html)
        if parsed_id != section_id:
            raise ValueError(
                f"requested {section_id} but page reports {parsed_id} ({url})")
        attach_parent_headings(records)
        sections.append({
            "section_id": parsed_id,
            "section_heading": heading,
            "source_url": url,
            "records": records,
        })

    if not any(section["records"] for section in sections):
        raise ValueError(
            f"{subpart['subpart']}: parsed 0 paragraphs from {len(sections)} sections")

    if "index" in subpart:
        subpart_url = f"{BASE_URL}/{subpart['index']}"
    else:
        subpart_url = f"{BASE_URL}/{section_ids[0]}"

    payload = {
        "subpart": subpart["subpart"],
        "subpart_name": subpart["subpart_name"],
        "source_url": subpart_url,
        "sections": sections,
    }

    corpus_dir = data_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / f"{subpart['slug']}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (corpus_dir / f"{subpart['slug']}.md").write_text(
        render_subpart_markdown(f"{subpart['subpart']} - {subpart['subpart_name']}", sections),
        encoding="utf-8")

    return payload


def main():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    for subpart in SUBPARTS:
        payload = build_corpus(subpart, data_dir)
        count = sum(len(s["records"]) for s in payload["sections"])
        print(f"{subpart['subpart']}: {len(payload['sections'])} sections, {count} paragraphs")


if __name__ == "__main__":
    main()
