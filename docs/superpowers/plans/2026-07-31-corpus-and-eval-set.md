# OSHA Corpus & Eval Set Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a committed, provenance-documented OSHA corpus (3 subparts, structured JSON + human-readable Markdown) and a ~45-question hand-verified eval set, with a validator that machine-checks every citation resolves to a real paragraph.

**Architecture:** A single reusable ingestion module scrapes osha.gov's server-rendered section pages, parses each `div.paragraph--type--regulations-standard-number` block into a record keyed by its native OSHA paragraph ID (e.g. `1910.147(a)(1)(ii)`), and emits both machine JSON and eyeball-able Markdown per subpart. Raw HTML is cached on first fetch so parsing iterations never re-hit the site. The eval set is authored by hand against the Markdown, then guarded by a validator that fails CI if any citation is unresolvable or the category mix drifts.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, `pytest`. No scraping framework — 20 static pages don't warrant one.

## Verified Facts (confirmed against live osha.gov before writing this plan)

These were checked, not assumed. Do not re-derive them; do notice if reality has changed.

- Pages are **server-rendered**. `curl` returns full content — no JS execution needed.
- Paragraph block selector: `div.paragraph--type--regulations-standard-number`
- Inside each block: `<span id="1910.147(a)(1)(ii)">` carries the **paragraph ID verbatim**, and `div.field--name-field-standard-paragraph-body-p` carries the body.
- Section title lives in `<title>`, format: `1910.147 - The control of hazardous energy (lockout/tagout). | Occupational Safety and Health Administration`
- Subpart index URL pattern: `https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartD` — links to sections match `standardnumber/1910/1910.NN`.
  - Subpart D → 1910.21–1910.30 (10 sections)
  - Subpart I → 1910.132–1910.140 (9 sections)
  - Subpart J → **only 1910.147** is in scope (do not ingest 1910.141–.146)
- **Tables are nested inside paragraph bodies.** `get_text()` on the body flattens numeric tables into unreadable runs of digits. Tables MUST be extracted to Markdown and removed from the body before text extraction. Verified on 1910.134 Table 1 (Assigned Protection Factors) and 1910.28.
- Observed paragraph counts: 1910.147→120, 1910.134→211, 1910.23→80, 1910.136→7. Expect roughly 1,500–2,500 records total.
- Ancestor paragraph IDs are derivable by trimming trailing `(...)` groups. ~65% of ancestors exist as their own records; the rest legitimately have no standalone block. Missing ancestors are skipped, not errors.

## Global Constraints

- Python 3.11+ (the machine's default `python`), Windows, no WSL.
- Dependencies limited to `requests`, `beautifulsoup4`, `pytest`. Adding any other runtime dependency requires justification against the "$0 / minimal stack" constraint in `PROJECT_BRIEF.md`.
- `data/raw/` and `data/corpus/` are **committed to git**, not gitignored.
- Scraping etiquette: identify via User-Agent, 1-second delay between live fetches, always read from cache when present.
- Commit messages carry **no AI/Claude/Anthropic attribution and no Co-Authored-By trailer**.
- All paths in this plan are relative to `C:\Users\LENOVO\Claude Local\rag-knowledge-assistant`.

## File Structure

| File | Responsibility |
|---|---|
| `requirements.txt` | Pin the three dependencies |
| `scripts/osha/fetch.py` | HTTP + on-disk raw HTML cache. Knows nothing about parsing. |
| `scripts/osha/parse.py` | HTML → paragraph records for one section. Knows nothing about HTTP or files. |
| `scripts/osha/hierarchy.py` | Paragraph-ID arithmetic: ancestors, parent-heading assembly. Pure functions. |
| `scripts/osha/render.py` | Records → Markdown for one subpart. |
| `scripts/ingest_osha.py` | CLI orchestration: config of subparts, wires the above, writes outputs. |
| `eval/validate_eval.py` | Schema + citation-resolvability + composition checks on `questions.jsonl` |
| `tests/` | pytest tests, one module per source module |

Split by responsibility so the parser can be tested against cached fixtures with zero network, and the fetch layer tested with zero HTML knowledge.

---

### Task 1: Project scaffold and HTTP cache layer

**Files:**
- Create: `requirements.txt`
- Create: `scripts/osha/__init__.py` (empty)
- Create: `scripts/osha/fetch.py`
- Create: `tests/test_fetch.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing
- Produces: `fetch_html(url: str, cache_path: Path, *, session=None, delay: float = 1.0) -> str` — returns HTML text; reads `cache_path` if it exists, otherwise GETs, writes cache, sleeps `delay`.

- [ ] **Step 1: Initialize the repo and write dependency + ignore files**

```bash
git init
```

`requirements.txt`:
```
requests==2.34.2
beautifulsoup4==4.15.0
pytest==8.3.4
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

Note: `data/` is deliberately absent from `.gitignore` — the corpus is committed.

- [ ] **Step 2: Write the failing test**

`tests/test_fetch.py`:
```python
from pathlib import Path
from scripts.osha.fetch import fetch_html


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append(url)
        return FakeResponse(self.text)


def test_fetches_and_writes_cache(tmp_path):
    cache = tmp_path / "1910.147.html"
    session = FakeSession("<html>live</html>")

    result = fetch_html("https://example.gov/x", cache, session=session, delay=0)

    assert result == "<html>live</html>"
    assert cache.read_text(encoding="utf-8") == "<html>live</html>"
    assert session.calls == ["https://example.gov/x"]


def test_reads_cache_without_network(tmp_path):
    cache = tmp_path / "1910.147.html"
    cache.write_text("<html>cached</html>", encoding="utf-8")
    session = FakeSession("<html>live</html>")

    result = fetch_html("https://example.gov/x", cache, session=session, delay=0)

    assert result == "<html>cached</html>"
    assert session.calls == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.osha.fetch'`

- [ ] **Step 4: Write the implementation**

`scripts/osha/__init__.py`: empty file.

`scripts/osha/fetch.py`:
```python
import time
from pathlib import Path

import requests

USER_AGENT = "rag-knowledge-assistant/0.1 (portfolio project; contact pgeagoni@gmail.com)"


def fetch_html(url, cache_path, *, session=None, delay=1.0):
    cache_path = Path(cache_path)
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    session = session or requests.Session()
    response = session.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    html = response.text

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    if delay:
        time.sleep(delay)
    return html
```

Add an empty `tests/__init__.py` and `scripts/__init__.py` so the package imports resolve.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore scripts/ tests/
git commit -m "feat: add cached HTTP fetch layer for OSHA ingestion"
```

---

### Task 2: Parse one section page into paragraph records

**Files:**
- Create: `scripts/osha/parse.py`
- Create: `tests/fixtures/1910.147.html` (cached real page)
- Create: `tests/test_parse.py`

**Interfaces:**
- Consumes: nothing (pure HTML → data)
- Produces:
  - `table_to_markdown(table) -> str` — a bs4 `<table>` Tag to a Markdown table, caption bolded above it.
  - `parse_section(html: str) -> tuple[str, str, list[dict]]` — returns `(section_id, section_heading, records)`. Each record is `{"paragraph_id": str, "text": str, "tables": list[str]}`.

- [ ] **Step 1: Save a real page as a test fixture**

```bash
mkdir -p tests/fixtures
curl -s -A "rag-knowledge-assistant/0.1 (portfolio project; contact pgeagoni@gmail.com)" \
  "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147" \
  -o tests/fixtures/1910.147.html
curl -s -A "rag-knowledge-assistant/0.1 (portfolio project; contact pgeagoni@gmail.com)" \
  "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.134" \
  -o tests/fixtures/1910.134.html
```

`1910.134` is the fixture that exercises table extraction; `1910.147` exercises the common case.

- [ ] **Step 2: Write the failing test**

`tests/test_parse.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.osha.parse'`

- [ ] **Step 4: Write the implementation**

`scripts/osha/parse.py`:
```python
from bs4 import BeautifulSoup

PARAGRAPH_SELECTOR = "div.paragraph--type--regulations-standard-number"
BODY_SELECTOR = "div.field--name-field-standard-paragraph-body-p"


def table_to_markdown(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [" ".join(c.get_text(" ", strip=True).split()) for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join([" --- "] * width) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]

    caption = table.find("caption")
    prefix = f"**{caption.get_text(' ', strip=True)}**\n\n" if caption else ""
    return prefix + "\n".join(lines)


def parse_section(html):
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True).split("|")[0].strip()
    section_id, _, section_heading = title.partition(" - ")
    section_id = section_id.strip()
    section_heading = section_heading.strip()

    records = []
    for block in soup.select(PARAGRAPH_SELECTOR):
        span = block.find("span", id=True)
        body = block.select_one(BODY_SELECTOR)
        if span is None or body is None:
            continue

        tables = []
        for table in body.find_all("table"):
            markdown = table_to_markdown(table)
            if markdown:
                tables.append(markdown)
            table.decompose()

        records.append({
            "paragraph_id": span["id"].strip(),
            "text": " ".join(body.get_text(" ", strip=True).split()),
            "tables": tables,
        })

    return section_id, section_heading, records
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/osha/parse.py tests/test_parse.py tests/fixtures/
git commit -m "feat: parse OSHA section HTML into paragraph records with table extraction"
```

---

### Task 3: Paragraph-ID hierarchy and parent headings

**Files:**
- Create: `scripts/osha/hierarchy.py`
- Create: `tests/test_hierarchy.py`

**Interfaces:**
- Consumes: records from `parse_section` (Task 2)
- Produces:
  - `ancestor_ids(paragraph_id: str) -> list[str]` — e.g. `"1910.147(a)(1)(i)"` → `["1910.147", "1910.147(a)", "1910.147(a)(1)"]`
  - `attach_parent_headings(records: list[dict]) -> list[dict]` — mutates/returns records, each gaining `"parent_headings": list[dict]` where each entry is `{"paragraph_id": str, "text": str}` for resolvable ancestors only, outermost first. Heading text is truncated to 120 chars.

- [ ] **Step 1: Write the failing test**

`tests/test_hierarchy.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hierarchy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.osha.hierarchy'`

- [ ] **Step 3: Write the implementation**

`scripts/osha/hierarchy.py`:
```python
import re

GROUP_PATTERN = re.compile(r"\([^)]*\)")
HEADING_MAX_CHARS = 120


def ancestor_ids(paragraph_id):
    base = paragraph_id.split("(")[0]
    groups = GROUP_PATTERN.findall(paragraph_id)
    return [base + "".join(groups[:i]) for i in range(len(groups))]


def attach_parent_headings(records):
    by_id = {r["paragraph_id"]: r for r in records}
    for record in records:
        headings = []
        for ancestor in ancestor_ids(record["paragraph_id"]):
            parent = by_id.get(ancestor)
            if parent is None:
                continue
            headings.append({
                "paragraph_id": ancestor,
                "text": parent["text"][:HEADING_MAX_CHARS],
            })
        record["parent_headings"] = headings
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hierarchy.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/osha/hierarchy.py tests/test_hierarchy.py
git commit -m "feat: derive paragraph hierarchy and parent headings from OSHA paragraph IDs"
```

---

### Task 4: Discover section URLs from a subpart index page

**Files:**
- Create: `scripts/osha/discover.py`
- Create: `tests/fixtures/1910SubpartD.html`
- Create: `tests/test_discover.py`

**Interfaces:**
- Consumes: nothing
- Produces: `section_ids_from_subpart(html: str) -> list[str]` — sorted, deduplicated section IDs like `["1910.21", "1910.22", ...]`.

- [ ] **Step 1: Save the subpart index fixture**

```bash
curl -s -A "rag-knowledge-assistant/0.1 (portfolio project; contact pgeagoni@gmail.com)" \
  "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartD" \
  -o tests/fixtures/1910SubpartD.html
```

- [ ] **Step 2: Write the failing test**

`tests/test_discover.py`:
```python
from pathlib import Path

from scripts.osha.discover import section_ids_from_subpart

FIXTURES = Path(__file__).parent / "fixtures"


def test_lists_subpart_d_sections_in_numeric_order():
    html = (FIXTURES / "1910SubpartD.html").read_text(encoding="utf-8")

    assert section_ids_from_subpart(html) == [
        "1910.21", "1910.22", "1910.23", "1910.24", "1910.25",
        "1910.26", "1910.27", "1910.28", "1910.29", "1910.30",
    ]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_discover.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.osha.discover'`

- [ ] **Step 4: Write the implementation**

`scripts/osha/discover.py`:
```python
import re

SECTION_LINK_PATTERN = re.compile(r"standardnumber/1910/(1910\.\d+)")


def section_ids_from_subpart(html):
    found = set(SECTION_LINK_PATTERN.findall(html))
    return sorted(found, key=lambda s: int(s.split(".")[1]))
```

Regex rather than bs4 here: the target is an href substring, and the surrounding markup varies between the body list and the sidebar nav. Matching the URL pattern directly is both shorter and less brittle than walking two different DOM structures.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_discover.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/osha/discover.py tests/test_discover.py tests/fixtures/1910SubpartD.html
git commit -m "feat: discover section IDs from OSHA subpart index pages"
```

---

### Task 5: Markdown renderer

**Files:**
- Create: `scripts/osha/render.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Consumes: final corpus records (schema finalized in Task 6)
- Produces: `render_subpart_markdown(subpart_name: str, sections: list[dict]) -> str` where each section is `{"section_id", "section_heading", "records"}`.

The Markdown is what the eval questions get hand-verified against, so paragraph IDs must be visible on every paragraph — a question's citation is only verifiable if the reader can see the ID next to the text.

- [ ] **Step 1: Write the failing test**

`tests/test_render.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.osha.render'`

- [ ] **Step 3: Write the implementation**

`scripts/osha/render.py`:
```python
def render_subpart_markdown(subpart_name, sections):
    lines = [f"# {subpart_name}", ""]
    for section in sections:
        lines.append(f"## {section['section_id']} - {section['section_heading']}")
        lines.append("")
        for record in section["records"]:
            lines.append(f"**{record['paragraph_id']}**")
            lines.append("")
            lines.append(record["text"])
            lines.append("")
            for table in record["tables"]:
                lines.append(table)
                lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_render.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/osha/render.py tests/test_render.py
git commit -m "feat: render subpart corpus as human-readable Markdown"
```

---

### Task 6: Ingestion CLI — wire it together and produce the corpus

**Files:**
- Create: `scripts/ingest_osha.py`
- Create: `tests/test_ingest.py`
- Create (generated): `data/raw/*.html`, `data/corpus/*.json`, `data/corpus/*.md`

**Interfaces:**
- Consumes: `fetch_html` (Task 1), `parse_section` (Task 2), `attach_parent_headings` (Task 3), `section_ids_from_subpart` (Task 4), `render_subpart_markdown` (Task 5)
- Produces: `build_corpus(subpart: dict, data_dir: Path, *, session=None, delay=1.0) -> dict` — the subpart payload written to JSON.

**Final JSON schema** (one file per subpart, `data/corpus/<slug>.json`):
```json
{
  "subpart": "Subpart D",
  "subpart_name": "Walking-Working Surfaces",
  "source_url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartD",
  "sections": [
    {
      "section_id": "1910.23",
      "section_heading": "Ladders.",
      "source_url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.23",
      "records": [
        {
          "paragraph_id": "1910.23(b)(2)",
          "text": "Ladder rungs, steps, and cleats are spaced ...",
          "tables": [],
          "parent_headings": [
            {"paragraph_id": "1910.23(b)", "text": "General requirements for all ladders ."}
          ]
        }
      ]
    }
  ]
}
```

This extends the brief's schema with `subpart`, `tables`, and `source_url`. `subpart` is required because `expected_citation.subpart` in the eval set must resolve against it; `tables` is required because numeric-lookup questions target table values; `source_url` makes each record independently traceable back to osha.gov.

- [ ] **Step 1: Write the failing test**

`tests/test_ingest.py`:
```python
import json
from pathlib import Path

from scripts.ingest_osha import SUBPARTS, build_corpus

FIXTURES = Path(__file__).parent / "fixtures"


class StubSession:
    """Serves the subpart index and one section page from fixtures."""

    def __init__(self):
        self.calls = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append(url)
        name = "1910SubpartD.html" if "SubpartD" in url else "1910.147.html"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.ingest_osha'`

- [ ] **Step 3: Write the implementation**

`scripts/ingest_osha.py`:
```python
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

    sections = []
    for section_id in section_ids:
        url = f"{BASE_URL}/{section_id}"
        html = fetch_html(url, data_dir / "raw" / f"{section_id}.html",
                          session=session, delay=delay)
        parsed_id, heading, records = parse_section(html)
        attach_parent_headings(records)
        sections.append({
            "section_id": parsed_id,
            "section_heading": heading,
            "source_url": url,
            "records": records,
        })

    payload = {
        "subpart": subpart["subpart"],
        "subpart_name": subpart["subpart_name"],
        "source_url": f"{BASE_URL}/{subpart.get('index', section_ids[0])}",
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the real ingestion**

Run: `python -m scripts.ingest_osha`
Expected output shape (exact counts will vary):
```
Subpart D: 10 sections, ~700 paragraphs
Subpart I: 9 sections, ~600 paragraphs
Subpart J: 1 sections, 120 paragraphs
```

Sanity-check before committing: open `data/corpus/subpart-i-personal-protective-equipment.md`, find the Assigned Protection Factors table, and confirm it renders as a readable Markdown table rather than a run-on line of numbers. If it doesn't, the bug is in Task 2's table handling — fix there, not here.

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests pass

- [ ] **Step 7: Commit the code and the corpus separately**

```bash
git add scripts/ingest_osha.py tests/test_ingest.py
git commit -m "feat: add OSHA corpus ingestion CLI"
git add data/
git commit -m "data: add OSHA 1910 corpus for Subparts D, I, and 1910.147"
```

---

### Task 7: Corpus provenance documentation

**Files:**
- Create: `data/README.md`

Satisfies the "corpus sourced and documented (where it came from, licensing)" criterion in `PROJECT_BRIEF.md` without making a reader dig through the scraper.

- [ ] **Step 1: Write the provenance doc**

`data/README.md` — replace `<YYYY-MM-DD>` with the date the ingestion in Task 6 was actually run, and the counts with the real printed output:

```markdown
# Corpus Provenance

## Source

U.S. Occupational Safety and Health Administration, Title 29 CFR Part 1910
(Occupational Safety and Health Standards for General Industry), scraped from
osha.gov on <YYYY-MM-DD>.

| Subpart | Scope | Index URL |
|---|---|---|
| Subpart D | Walking-Working Surfaces (1910.21-1910.30) | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartD |
| Subpart I | Personal Protective Equipment (1910.132-1910.140) | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910SubpartI |
| Subpart J | Lockout/Tagout — **1910.147 only** | https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147 |

Subpart J is deliberately scoped to 1910.147 alone. The rest of Subpart J
(1910.141-1910.146) is out of scope.

## Licensing

U.S. federal regulatory text. Works of the U.S. federal government are not
subject to copyright protection in the United States (17 U.S.C. § 105) and are
in the public domain. No license restrictions apply to redistribution of the
regulatory text in this directory.

## Why the corpus is committed to this repo

`data/raw/` (cached source HTML) and `data/corpus/` (parsed output) are committed
rather than gitignored. The corpus is small and public-domain, and committing it
means anyone cloning this repository gets a working system without network access
to osha.gov and without depending on OSHA's page structure remaining unchanged.
`scripts/ingest_osha.py` documents how the corpus was produced; it does not need
to be re-run to use the repository.

## Regenerating

    python -m scripts.ingest_osha

Delete `data/raw/` first to force a live re-fetch; otherwise cached HTML is reused.

## Scope note

This corpus is a subset of 29 CFR 1910 selected for a portfolio retrieval system.
It is not a complete or authoritative copy of OSHA's standards and must not be
relied on for compliance purposes. Consult osha.gov or eCFR for authoritative text.
```

- [ ] **Step 2: Commit**

```bash
git add data/README.md
git commit -m "docs: document corpus provenance and licensing"
```

---

### Task 8: Eval set schema and validator

**Files:**
- Create: `eval/questions.jsonl` (seeded with 3 example questions in this task; filled out in Task 9)
- Create: `eval/validate_eval.py`
- Create: `tests/test_validate_eval.py`

**Interfaces:**
- Consumes: `data/corpus/*.json` from Task 6
- Produces:
  - `load_corpus_paragraph_ids(corpus_dir: Path) -> set[str]`
  - `validate(questions: list[dict], known_paragraph_ids: set[str]) -> list[str]` — returns a list of human-readable error strings; empty means valid.

**Question schema:**
```json
{
  "id": "loto-001",
  "question": "What must an energy control procedure include before a lockout device is removed?",
  "category": "procedural",
  "expected_answer": "The authorized employee must verify the machine is properly shut down and that all employees are safely positioned or clear.",
  "expected_citation": {"subpart": "Subpart J", "section_id": "1910.147", "paragraph_id": "1910.147(e)(3)"},
  "notes": ""
}
```

Rules the validator enforces:
1. Every `id` is unique.
2. `category` ∈ `{numeric_lookup, procedural, conditional, negative, near_miss}`.
3. Non-`negative` questions have an `expected_citation` whose `paragraph_id` **exists in the corpus**. This is the machine check that backs the "hand-verified" claim — a typo'd citation cannot silently pass.
4. `negative` questions have `expected_citation: null` and a **non-empty `notes`** naming the absent topic. This enforces the brief's rule that "not covered" is a documented claim, not a guess.
5. Category mix is within tolerance of the target composition (±5 percentage points): numeric_lookup 35%, procedural 25%, conditional 20%, negative 15%, near_miss 5%.

- [ ] **Step 1: Write the failing test**

`tests/test_validate_eval.py`:
```python
from eval.validate_eval import validate

KNOWN = {"1910.147(e)(3)", "1910.23(b)(2)"}


def good(**overrides):
    q = {
        "id": "loto-001",
        "question": "What must be verified before removing a lockout device?",
        "category": "procedural",
        "expected_answer": "The machine is shut down and employees are clear.",
        "expected_citation": {
            "subpart": "Subpart J",
            "section_id": "1910.147",
            "paragraph_id": "1910.147(e)(3)",
        },
        "notes": "",
    }
    q.update(overrides)
    return q


def test_accepts_a_valid_question():
    assert validate([good()], KNOWN) == []


def test_rejects_citation_not_present_in_corpus():
    q = good(expected_citation={
        "subpart": "Subpart J", "section_id": "1910.147",
        "paragraph_id": "1910.147(z)(99)",
    })

    errors = validate([q], KNOWN)

    assert any("1910.147(z)(99)" in e for e in errors)


def test_rejects_duplicate_ids():
    errors = validate([good(), good()], KNOWN)

    assert any("duplicate id" in e.lower() for e in errors)


def test_rejects_unknown_category():
    errors = validate([good(category="trick_question")], KNOWN)

    assert any("category" in e.lower() for e in errors)


def test_negative_question_requires_notes_and_no_citation():
    missing_notes = good(id="neg-001", category="negative",
                         expected_citation=None, notes="")

    errors = validate([missing_notes], KNOWN)

    assert any("notes" in e.lower() for e in errors)


def test_negative_question_must_not_carry_a_citation():
    q = good(id="neg-002", category="negative", notes="Forklift training is in 1910.178, not in scope.")

    errors = validate([q], KNOWN)

    assert any("expected_citation" in e for e in errors)


def test_composition_check_flags_skewed_mix():
    questions = [good(id=f"q-{i}") for i in range(20)]  # 100% procedural

    errors = validate(questions, KNOWN, check_composition=True)

    assert any("composition" in e.lower() for e in errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validate_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.validate_eval'`

- [ ] **Step 3: Write the implementation**

Create `eval/__init__.py` (empty).

`eval/validate_eval.py`:
```python
"""Validate the hand-authored eval question set against the corpus."""

import json
import sys
from collections import Counter
from pathlib import Path

CATEGORIES = {"numeric_lookup", "procedural", "conditional", "negative", "near_miss"}

TARGET_COMPOSITION = {
    "numeric_lookup": 0.35,
    "procedural": 0.25,
    "conditional": 0.20,
    "negative": 0.15,
    "near_miss": 0.05,
}
COMPOSITION_TOLERANCE = 0.05


def load_corpus_paragraph_ids(corpus_dir):
    ids = set()
    for path in Path(corpus_dir).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for section in payload["sections"]:
            for record in section["records"]:
                ids.add(record["paragraph_id"])
    return ids


def load_questions(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def validate(questions, known_paragraph_ids, *, check_composition=False):
    errors = []

    seen = set()
    for q in questions:
        qid = q.get("id")
        if qid in seen:
            errors.append(f"duplicate id: {qid}")
        seen.add(qid)

        category = q.get("category")
        if category not in CATEGORIES:
            errors.append(f"{qid}: unknown category {category!r}")
            continue

        citation = q.get("expected_citation")
        if category == "negative":
            if citation is not None:
                errors.append(f"{qid}: negative questions must have expected_citation null")
            if not (q.get("notes") or "").strip():
                errors.append(f"{qid}: negative questions require notes naming the absent topic")
        else:
            if not citation:
                errors.append(f"{qid}: missing expected_citation")
            elif citation["paragraph_id"] not in known_paragraph_ids:
                errors.append(
                    f"{qid}: citation {citation['paragraph_id']} not found in corpus")

    if check_composition and questions:
        counts = Counter(q.get("category") for q in questions)
        total = len(questions)
        for category, target in TARGET_COMPOSITION.items():
            actual = counts[category] / total
            if abs(actual - target) > COMPOSITION_TOLERANCE:
                errors.append(
                    f"composition: {category} is {actual:.0%}, target {target:.0%} "
                    f"(+/-{COMPOSITION_TOLERANCE:.0%})")

    return errors


def main():
    root = Path(__file__).resolve().parent.parent
    questions = load_questions(root / "eval" / "questions.jsonl")
    known = load_corpus_paragraph_ids(root / "data" / "corpus")

    errors = validate(questions, known, check_composition=len(questions) >= 40)
    for error in errors:
        print(error)

    print(f"\n{len(questions)} questions, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_validate_eval.py -v`
Expected: 7 passed

- [ ] **Step 5: Seed `eval/questions.jsonl` with three real questions**

Do not invent these. Open `data/corpus/subpart-j-lockout-tagout.md`, read the actual paragraphs, and write three questions whose answers and paragraph IDs you have read with your own eyes — one `procedural`, one `numeric_lookup`, one `negative`. One JSON object per line.

- [ ] **Step 6: Run the validator against the real corpus**

Run: `python -m eval.validate_eval`
Expected: `3 questions, 0 errors`

If a citation error appears, the question's paragraph ID is wrong — fix the question, not the validator.

- [ ] **Step 7: Commit**

```bash
git add eval/ tests/test_validate_eval.py
git commit -m "feat: add eval question schema and corpus-backed validator"
```

---

### Task 9: Author the full eval question set

**Files:**
- Modify: `eval/questions.jsonl` (3 questions → ~45)

This task is a collaborative authoring session, not an automated one. The claim this project is built to defend is "every eval question was hand-verified against the actual regulation" — so the loop below must not be replaced by a generation script.

**Target composition** (~45 questions):

| Category | Count | What it tests |
|---|---|---|
| `numeric_lookup` | 16 | Precision on specific values (heights, spacings, table figures) |
| `procedural` | 11 | Retrieval across multi-paragraph sequences |
| `conditional` | 9 | Handling of scoped/exception language |
| `negative` | 7 | Hallucination detection — the model should decline, not guess |
| `near_miss` | 3 | Precision against similar wording in the wrong section |

Spread roughly proportionally across the three subparts. `numeric_lookup` questions should draw on the extracted tables (Subpart I respirator APFs, Subpart D ladder/guardrail dimensions) as well as inline figures.

**The authoring loop, per question:**

- [ ] **Step 1: Read the source paragraph in the rendered Markdown**

Open `data/corpus/<subpart>.md` and read the actual paragraph. The paragraph ID is printed in bold directly above its text.

- [ ] **Step 2: Draft the question**

Claude may propose candidate questions from the same Markdown. Every candidate is confirmed, edited, or rejected against the paragraph text before it is written to the file — a proposal is not a verification.

- [ ] **Step 3: Write the JSON line**

```json
{"id": "ladder-004", "question": "What is the minimum clear width between ladder side rails on a fixed ladder?", "category": "numeric_lookup", "expected_answer": "16 inches (41 cm), measured between the side rails at the rung level.", "expected_citation": {"subpart": "Subpart D", "section_id": "1910.23", "paragraph_id": "1910.23(d)(2)"}, "notes": ""}
```

For `negative` questions, `expected_citation` is `null` and `notes` states what is absent and where it actually lives:

```json
{"id": "neg-003", "question": "How many hours of forklift operator training does OSHA require annually?", "category": "negative", "expected_answer": "Not covered by this corpus.", "expected_citation": null, "notes": "Powered industrial truck training is 1910.178(l), in Subpart N, which is outside the three ingested subparts."}
```

- [ ] **Step 4: Re-run the validator after every few questions**

Run: `python -m eval.validate_eval`
Expected: growing question count, `0 errors`

A citation error means the paragraph ID was mistyped or the wrong paragraph was cited. Fix the question.

- [ ] **Step 5: Final validation with composition check**

Run: `python -m eval.validate_eval`
Expected: `45 questions, 0 errors` — the composition check activates automatically at 40+ questions and will fail if the category mix drifted more than 5 points from target.

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add eval/questions.jsonl
git commit -m "data: add hand-verified OSHA eval question set"
```

---

## Definition of Done for This Plan

- `python -m pytest -v` passes.
- `python -m eval.validate_eval` reports ~45 questions, 0 errors.
- `data/corpus/*.md` is readable, with tables rendering as tables.
- `data/README.md` states scrape date, source URLs, and public-domain status.
- Everything is committed, including `data/`.

Explicitly **not** in this plan (next phase): chunking, embeddings, pgvector, retrieval, the metric computation that consumes this eval set, and the API. This plan produces the ground truth those will be measured against.
