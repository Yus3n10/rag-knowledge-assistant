"""The end-to-end answer pipeline: retrieve, prompt, generate, ground.

Wires scripts.rag.retrieve, scripts.rag.prompt, and scripts.rag.ground
together. No new logic beyond dedup/aggregation lives here -- everything else
is a call into an already-tested module. See
docs/superpowers/plans/2026-08-01-generation-and-grounding.md (Task 5).

No distance gate: refusal is a model judgment made over the retrieved
context (see the plan's "Refusal design" section, settled by measurement).
"""

from scripts.rag.retrieve import search
from scripts.rag.prompt import build_messages
from scripts.rag.ground import extract_citations, validate_citations, ungrounded_numbers

# Retrieve k*OVERFETCH_FACTOR raw chunks before dedup so a split paragraph's
# extra chunks don't consume k-slots that should hold distinct paragraphs.
# Matches eval/run_eval.py's OVERFETCH_FACTOR, which is how the k=10 recall/
# completeness numbers in docs/RETRIEVAL_FINDINGS.md were actually measured.
OVERFETCH_FACTOR = 4


def _dedupe_chunks_by_paragraph(chunks, k):
    """First-seen chunk per distinct paragraph_id (chunks already ascending by
    distance), truncated to k distinct paragraphs. Keeps the whole chunk
    record (not just the id) since build_messages needs each chunk's text."""
    seen = set()
    kept = []
    for chunk in chunks:
        pid = chunk["paragraph_id"]
        if pid in seen:
            continue
        seen.add(pid)
        kept.append(chunk)
        if len(kept) == k:
            break
    return kept


def _retrieved_entry(chunk, context_chunks):
    """One retrieved entry for chunk's paragraph. distance/paragraph_id come
    from the deduped chunk, but heading_trail/text are built from EVERY
    context_chunks chunk sharing that paragraph_id -- not just chunk itself.

    A paragraph split into prose + table chunks (e.g. 1910.134(d)(3)(i)(A))
    must show all of it: building this from the deduped `chunks` list would
    show only the first-seen chunk and silently omit the table, reproducing
    the Phase 3 bug fixed in commit f0ccff1 (this time in the UI instead of
    the prompt context).

    Chunk text is stored as "heading_trail\\n\\n<body>" (see
    chunk.chunk_records); text without that separator (e.g. stub data) is
    used as-is with an empty heading_trail.
    """
    siblings = [c for c in context_chunks if c["paragraph_id"] == chunk["paragraph_id"]]
    heading_trail, bodies = None, []
    for sibling in siblings:
        head, sep, body = sibling["text"].partition("\n\n")
        if heading_trail is None:
            heading_trail = head if sep else ""
        bodies.append(body if sep else head)
    return {
        "paragraph_id": chunk["paragraph_id"],
        "distance": chunk["distance"],
        "heading_trail": heading_trail,
        "text": "\n\n".join(bodies),
    }


def answer_question(question, *, k=10, conn, embedder, generator, corpus_paragraph_ids=None, roles=None):
    """Run one question through the full pipeline.

    generator(messages) -> (answer_text, stats), matching
    scripts.rag.generate.generate once model/url/session are bound by the caller.

    roles is forwarded to scripts.rag.retrieve.search unchanged (None means
    public content only -- see that module's docstring). This is the only
    place the API layer can reach the permission filter, since it lives in
    retrieval's SQL, not applied after the fact.

    Returns answer, citations, citation_report, ungrounded_numbers,
    retrieved (one entry per paragraph: paragraph_id, distance, heading_trail,
    and text joined from all of that paragraph's chunks -- so a client can
    show the source text behind a citation), retrieved_text (concatenated
    chunk text, exposed for callers that need the raw context -- e.g. the
    resp-001 canary check in eval/run_answers.py), and stats.
    """
    raw_chunks = search(question, k=k * OVERFETCH_FACTOR, conn=conn, embedder=embedder, roles=roles)
    chunks = _dedupe_chunks_by_paragraph(raw_chunks, k)

    # Paragraph dedup above only decides WHICH k paragraphs are in scope (for
    # the "retrieved" metadata and citation validation). It must NOT decide
    # which of a paragraph's chunks the model gets to see: a split paragraph's
    # prose and table chunks carry different content, and dropping one as a
    # "duplicate" can silently discard the chunk holding the answer. So the
    # prompt context gets every raw chunk belonging to a selected paragraph,
    # not just the first-seen one.
    selected_paragraph_ids = {chunk["paragraph_id"] for chunk in chunks}
    context_chunks = [c for c in raw_chunks if c["paragraph_id"] in selected_paragraph_ids]

    messages = build_messages(question, context_chunks)
    answer, stats = generator(messages)

    citations = extract_citations(answer)
    retrieved_paragraph_ids = [chunk["paragraph_id"] for chunk in chunks]
    citation_report = validate_citations(citations, retrieved_paragraph_ids, corpus_paragraph_ids)

    # Matches what the model was actually shown (context_chunks), not the
    # paragraph-deduped set -- otherwise an answer legitimately drawn from a
    # chunk that dedup treated as a "duplicate" would be flagged ungrounded.
    retrieved_text = "\n\n".join(chunk["text"] for chunk in context_chunks)

    return {
        "answer": answer,
        "citations": citations,
        "citation_report": citation_report,
        "ungrounded_numbers": ungrounded_numbers(answer, retrieved_text),
        "retrieved": [_retrieved_entry(chunk, context_chunks) for chunk in chunks],
        "retrieved_text": retrieved_text,
        "stats": stats,
    }
