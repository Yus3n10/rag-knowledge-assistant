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
