from scripts.build_index import COLUMNS, chunks_to_rows


class StubEmbedder:
    """Fake embed_texts: returns one vector per text, encoding text length so a
    pairing bug (wrong vector for wrong chunk) would be caught."""

    def __init__(self):
        self.calls = []

    def __call__(self, texts, **kwargs):
        self.calls.append(texts)
        vectors = [[float(len(t))] * 3 for t in texts]
        return vectors, len(texts) * 7


SECTION = {
    "section_id": "1910.147",
    "section_heading": "The control of hazardous energy (lockout/tagout).",
    "records": [
        {"paragraph_id": "1910.147(e)(3)",
         "text": "Each device shall be removed by the employee who applied it.",
         "tables": [], "parent_headings": []},
        {"paragraph_id": "1910.147(x)", "text": "Table paragraph.",
         "tables": ["| Type | APF |\n| --- | --- |\n| Full facepiece | 50 |"],
         "parent_headings": []},
    ],
}


def test_every_chunk_produces_exactly_one_row():
    embedder = StubEmbedder()
    rows, tokens = chunks_to_rows([SECTION], "Subpart J", "General Environmental Controls",
                                   embed=embedder)

    # SECTION yields 3 chunks: 1910.147(e)(3) prose, 1910.147(x) table, and
    # 1910.147(x) prose (its own "Table paragraph." text, separate from the table)
    assert len(rows) == 3
    assert tokens == 3 * 7


def test_row_column_order_matches_table_schema():
    embedder = StubEmbedder()
    rows, _ = chunks_to_rows([SECTION], "Subpart J", "General Environmental Controls",
                              embed=embedder)

    assert COLUMNS == ("chunk_id", "paragraph_id", "section_id", "subpart",
                        "heading_trail", "text", "embedding")
    for row in rows:
        assert len(row) == len(COLUMNS)


def test_chunk_ids_are_unique_across_the_corpus():
    embedder = StubEmbedder()
    section_two = {
        "section_id": "1910.140",
        "section_heading": "Personal fall protection systems.",
        "records": [{"paragraph_id": "1910.140(b)", "tables": [], "parent_headings": [],
                      "text": "Some other paragraph text."}],
    }
    rows, _ = chunks_to_rows([SECTION, section_two], "Subpart J",
                              "General Environmental Controls", embed=embedder)

    chunk_ids = [row[0] for row in rows]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_embedding_in_row_matches_the_vector_returned_for_that_chunks_text():
    embedder = StubEmbedder()
    rows, _ = chunks_to_rows([SECTION], "Subpart J", "General Environmental Controls",
                              embed=embedder)

    # embedder encodes each vector as [len(text)]*3, so the row's embedding must
    # match the length of that row's own text -- catches a pairing/reordering bug.
    for row in rows:
        text = row[5]
        embedding = row[6]
        assert embedding == [float(len(text))] * 3
