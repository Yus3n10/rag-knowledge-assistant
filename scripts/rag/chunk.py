"""Turn corpus paragraphs into embeddable chunks."""

import re

MAX_CHARS = 2000
SENTENCE_END = re.compile(r"(?<=[.;:])\s+")


def heading_trail(section, record):
    """Readable ancestry: section heading then each parent paragraph's text."""
    parts = [f"{section['section_id']} {section['section_heading']}"]
    for parent in record.get("parent_headings", []):
        parts.append(parent["text"])
    return " > ".join(parts)


def split_text(text, budget):
    """Split on sentence boundaries into pieces no longer than budget."""
    if len(text) <= budget:
        return [text]
    pieces, current = [], ""
    for sentence in SENTENCE_END.split(text):
        if current and len(current) + 1 + len(sentence) > budget:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_records(section, subpart, subpart_name):
    chunks = []
    for record in section["records"]:
        trail = heading_trail(section, record)
        body = " ".join([record["text"]] + record.get("tables", []))
        budget = MAX_CHARS - len(trail) - 2
        pieces = split_text(body, budget)
        for n, piece in enumerate(pieces):
            chunk_id = record["paragraph_id"] if len(pieces) == 1 else f"{record['paragraph_id']}#{n}"
            chunks.append({
                "chunk_id": chunk_id,
                "paragraph_id": record["paragraph_id"],
                "section_id": section["section_id"],
                "subpart": subpart,
                "heading_trail": trail,
                "text": f"{trail}\n\n{piece}",
            })
    return chunks
