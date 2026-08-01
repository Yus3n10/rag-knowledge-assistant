from scripts.rag.answer import answer_question, OVERFETCH_FACTOR


class StubCursor:
    """Mirrors tests/test_retrieve.py's stub: records execute() params, hands
    back canned rows on fetchall() regardless of the requested LIMIT (a real
    DB enforces LIMIT server-side; this stub doesn't need to)."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows


class StubConnection:
    def __init__(self, rows):
        self.cur = StubCursor(rows)

    def cursor(self):
        return self.cur


class StubEmbedder:
    def __init__(self, vector=(0.1, 0.2, 0.3)):
        self.calls = []
        self.vector = list(vector)

    def __call__(self, texts):
        self.calls.append(texts)
        return [self.vector for _ in texts]


class StubGenerator:
    """generator(messages) -> (answer_text, stats), matching what
    scripts.rag.generate.generate produces once model/url/session are bound."""

    def __init__(self, answer="the answer [1910.147(e)(3)]",
                 stats=None):
        self.calls = []
        self.answer = answer
        self.stats = stats or {
            "prompt_tokens": 100, "completion_tokens": 20,
            "latency_s": 4.5, "load_duration_s": 0.0,
        }

    def __call__(self, messages):
        self.calls.append(messages)
        return self.answer, self.stats


# (chunk_id, paragraph_id, text, distance) rows, as SEARCH_SQL's SELECT would
# return them -- ascending distance order.
SIMPLE_ROWS = [
    ("c1", "1910.147(e)(3)", "Only the employee who applied the device may remove it.", 0.12),
    ("c2", "1910.147(c)(1)", "The employer shall establish a program.", 0.34),
]

# A split paragraph (P1) yields two chunks before three distinct paragraphs
# are seen -- exercises dedup-before-truncation.
DUPLICATE_ROWS = [
    ("c1", "P1", "P1 part one.", 0.10),
    ("c2", "P1", "P1 part two.", 0.15),
    ("c3", "P2", "P2 text.", 0.20),
    ("c4", "P3", "P3 part one.", 0.25),
    ("c5", "P3", "P3 part two.", 0.26),
    ("c6", "P4", "P4 text.", 0.30),
]


def test_returns_all_expected_keys():
    conn = StubConnection(SIMPLE_ROWS)
    result = answer_question(
        "who may remove a lockout device", k=2,
        conn=conn, embedder=StubEmbedder(), generator=StubGenerator(),
    )

    assert set(result.keys()) >= {
        "answer", "citations", "citation_report", "ungrounded_numbers",
        "retrieved", "stats",
    }


def test_answer_and_stats_come_from_the_generator():
    conn = StubConnection(SIMPLE_ROWS)
    generator = StubGenerator(answer="custom answer [1910.147(e)(3)]",
                               stats={"prompt_tokens": 5, "completion_tokens": 1,
                                      "latency_s": 1.0, "load_duration_s": 0.0})

    result = answer_question("q", k=2, conn=conn, embedder=StubEmbedder(), generator=generator)

    assert result["answer"] == "custom answer [1910.147(e)(3)]"
    assert result["stats"]["prompt_tokens"] == 5


def test_dedup_by_paragraph_happens_before_truncation_to_k():
    conn = StubConnection(DUPLICATE_ROWS)

    result = answer_question("q", k=3, conn=conn, embedder=StubEmbedder(), generator=StubGenerator())

    # 3 distinct paragraphs, not 3 raw rows -- P1's second chunk must not
    # consume a k-slot, and P1's nearest occurrence (0.10) must be the one kept.
    assert result["retrieved"] == [
        {"paragraph_id": "P1", "distance": 0.10},
        {"paragraph_id": "P2", "distance": 0.20},
        {"paragraph_id": "P3", "distance": 0.25},
    ]


def test_search_is_called_with_an_overfetched_k_so_dedup_has_material():
    conn = StubConnection(DUPLICATE_ROWS)

    answer_question("q", k=3, conn=conn, embedder=StubEmbedder(), generator=StubGenerator())

    _, params = conn.cur.executed[0]
    assert params["k"] == 3 * OVERFETCH_FACTOR


def test_generator_receives_messages_built_from_the_deduped_chunks_only():
    conn = StubConnection(DUPLICATE_ROWS)
    generator = StubGenerator()

    answer_question("q", k=3, conn=conn, embedder=StubEmbedder(), generator=generator)

    user_content = generator.calls[0][-1]["content"]
    assert "[P1]" in user_content
    assert "[P2]" in user_content
    assert "[P3]" in user_content
    assert "[P4]" not in user_content  # truncated away after dedup


def test_citation_report_validates_against_the_deduped_retrieved_set():
    conn = StubConnection(SIMPLE_ROWS)
    generator = StubGenerator(answer="claim [1910.147(e)(3)] and fabricated [1910.999(z)]")

    result = answer_question("q", k=2, conn=conn, embedder=StubEmbedder(), generator=generator)

    assert result["citation_report"]["valid"] == ["1910.147(e)(3)"]
    assert result["citation_report"]["not_retrieved"] == ["1910.999(z)"]


def test_corpus_paragraph_ids_are_forwarded_to_distinguish_fabrication():
    conn = StubConnection(SIMPLE_ROWS)
    generator = StubGenerator(answer="fabricated [1910.999(z)]")

    result = answer_question(
        "q", k=2, conn=conn, embedder=StubEmbedder(), generator=generator,
        corpus_paragraph_ids={"1910.147(e)(3)", "1910.147(c)(1)"},
    )

    assert result["citation_report"]["not_in_corpus"] == ["1910.999(z)"]


def test_ungrounded_numbers_checked_against_concatenated_retrieved_chunk_text():
    conn = StubConnection(SIMPLE_ROWS)
    generator = StubGenerator(answer="The device may be removed after 999 minutes.")

    result = answer_question("q", k=2, conn=conn, embedder=StubEmbedder(), generator=generator)

    assert result["ungrounded_numbers"] == ["999"]


def test_ungrounded_numbers_empty_when_number_present_in_retrieved_text():
    rows = [("c1", "P1", "Wait 999 minutes before removal.", 0.1)]
    conn = StubConnection(rows)
    generator = StubGenerator(answer="Wait 999 minutes.")

    result = answer_question("q", k=1, conn=conn, embedder=StubEmbedder(), generator=generator)

    assert result["ungrounded_numbers"] == []


def test_no_distance_gate_low_and_high_distance_both_reach_the_generator():
    # Regression guard for the settled refusal design: answer_question must
    # never refuse based on distance alone, even for a very high (weak) match.
    rows = [("c1", "P1", "some retrieved text", 0.9999)]
    conn = StubConnection(rows)
    generator = StubGenerator()

    answer_question("q", k=1, conn=conn, embedder=StubEmbedder(), generator=generator)

    assert len(generator.calls) == 1


def test_retrieved_text_is_exposed_for_callers_needing_the_raw_context():
    # eval/run_answers.py needs this for the resp-001 canary check (whether the
    # retrieved context contained the target number at all).
    conn = StubConnection(SIMPLE_ROWS)

    result = answer_question("q", k=2, conn=conn, embedder=StubEmbedder(), generator=StubGenerator())

    assert "Only the employee who applied the device may remove it." in result["retrieved_text"]
