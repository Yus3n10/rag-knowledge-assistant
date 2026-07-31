"""Turn corpus paragraphs into embeddable chunks."""

import re

MAX_CHARS = 2000
SENTENCE_END = re.compile(r"(?<=[.;:])\s+")

# Definitions-style detection: the corpus uses two formats for defined terms.
#   "Term means ..."      -- e.g. "Rope descent system means a suspension system..."
#   "Term . Definition"   -- e.g. "Hot tap . A procedure used in the repair..."
# A paragraph is treated as definitions-style if enough of its sentences open with
# one of these shapes; detected per-paragraph rather than hardcoded by paragraph_id
# so a future corpus expansion with more definitions blobs is handled automatically.
TERM_MEANS = re.compile(r"^([A-Z][A-Za-z0-9()/'\-]*(?:\s+[A-Za-z0-9()/'\-]+){0,6})\s+means\b")
TERM_PERIOD = re.compile(r"^[A-Z][A-Za-z0-9()/'\-]*(?:\s+[a-zA-Z0-9()/'\-]+){0,6}\s*\.$")
# "The means of connection ..." / "A means of attachment ..." -- ordinary use of the
# noun "means", not a definition. TERM_MEANS would otherwise mistake the bare
# determiner for the defined term.
BARE_DETERMINERS = {"the", "a", "an", "some", "any", "this", "these", "those", "such", "it"}
DEFINITIONS_MIN_TERMS = 3


def _is_term_means(sentence):
    match = TERM_MEANS.match(sentence)
    return bool(match) and match.group(1).strip().lower() not in BARE_DETERMINERS


def _is_term_period(sentence):
    return bool(TERM_PERIOD.match(sentence))


def _definitions_term_start(sentences):
    """Return the term-start predicate for this paragraph's definition format, or
    None if it isn't definitions-style."""
    if sum(1 for s in sentences if _is_term_means(s)) >= DEFINITIONS_MIN_TERMS:
        return _is_term_means
    if sum(1 for s in sentences if _is_term_period(s)) >= DEFINITIONS_MIN_TERMS:
        return _is_term_period
    return None


def heading_trail(section, record):
    """Readable ancestry: section heading then each parent paragraph's text."""
    parts = [f"{section['section_id']} {section['section_heading']}"]
    for parent in record.get("parent_headings", []):
        parts.append(parent["text"])
    return " > ".join(parts)


def _pack(units, budget):
    """Greedily pack whole units (sentences, or whole definitions) into pieces no
    longer than budget. Never splits inside a unit."""
    pieces, current = [], ""
    for unit in units:
        if current and len(current) + 1 + len(unit) > budget:
            pieces.append(current)
            current = unit
        else:
            current = f"{current} {unit}".strip()
    if current:
        pieces.append(current)
    return pieces


def _group_definitions(sentences, is_term_start):
    """Group sentences so each group is one whole definition: starts at a defined
    term and absorbs every following sentence up to (not including) the next term."""
    groups, current = [], ""
    for sentence in sentences:
        if is_term_start(sentence) and current:
            groups.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        groups.append(current)
    return groups


def split_text(text, budget):
    """Split into pieces no longer than budget. Definitions-style paragraphs split
    before each defined term (both 'Term means' and 'Term . Definition' formats);
    everything else splits on sentence boundaries."""
    if len(text) <= budget:
        return [text]
    sentences = [s for s in SENTENCE_END.split(text) if s.strip()]
    is_term_start = _definitions_term_start(sentences)
    units = _group_definitions(sentences, is_term_start) if is_term_start else sentences
    return _pack(units, budget)


def chunk_records(section, subpart, subpart_name):
    chunks = []
    for record in section["records"]:
        trail = heading_trail(section, record)
        budget = MAX_CHARS - len(trail) - 2
        paragraph_id = record["paragraph_id"]

        # Rule 2: tables are atomic -- one chunk per table, never merged with prose
        # or with each other, so a query about one table's data never retrieves
        # another table's rows undifferentiated.
        for i, table in enumerate(record.get("tables", [])):
            chunks.append({
                "chunk_id": f"{paragraph_id}#t{i}",
                "paragraph_id": paragraph_id,
                "section_id": section["section_id"],
                "subpart": subpart,
                "heading_trail": trail,
                "text": f"{trail}\n\n{table}",
                "kind": "table",
            })

        pieces = split_text(record["text"], budget)
        for n, piece in enumerate(pieces):
            chunk_id = paragraph_id if len(pieces) == 1 else f"{paragraph_id}#{n}"
            chunks.append({
                "chunk_id": chunk_id,
                "paragraph_id": paragraph_id,
                "section_id": section["section_id"],
                "subpart": subpart,
                "heading_trail": trail,
                "text": f"{trail}\n\n{piece}",
                "kind": "prose",
            })
    return chunks
