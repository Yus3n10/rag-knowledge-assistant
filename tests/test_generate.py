from scripts.rag.generate import generate


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class StubSession:
    def __init__(self, payload):
        self.calls = []
        self._payload = payload

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        return StubResponse(self._payload)


def _payload(content="the answer", prompt_eval_count=100, eval_count=20,
             load_duration=5_000_000_000):
    return {
        "message": {"role": "assistant", "content": content},
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
        "total_duration": 6_000_000_000,
        "load_duration": load_duration,
        "prompt_eval_duration": 500_000_000,
        "eval_duration": 500_000_000,
    }


def test_extracts_answer_text_from_message_content():
    session = StubSession(_payload(content="lockout requires a tag"))

    answer, stats = generate(
        [{"role": "user", "content": "what is lockout"}],
        model="llama3.1:8b", url="http://localhost:11434", session=session,
    )

    assert answer == "lockout requires a tag"


def test_returns_prompt_and_completion_tokens_from_eval_counts():
    session = StubSession(_payload(prompt_eval_count=1075, eval_count=43))

    _, stats = generate(
        [{"role": "user", "content": "hi"}],
        model="llama3.1:8b", url="http://localhost:11434", session=session,
    )

    assert stats["prompt_tokens"] == 1075
    assert stats["completion_tokens"] == 43


def test_surfaces_load_duration_seconds_converted_from_nanoseconds():
    session = StubSession(_payload(load_duration=5_000_000_000))

    _, stats = generate(
        [{"role": "user", "content": "hi"}],
        model="llama3.1:8b", url="http://localhost:11434", session=session,
    )

    assert stats["load_duration_s"] == 5.0


def test_defaults_temperature_to_zero_in_posted_body():
    session = StubSession(_payload())

    generate(
        [{"role": "user", "content": "hi"}],
        model="llama3.1:8b", url="http://localhost:11434", session=session,
    )

    posted_body = session.calls[0][1]
    assert posted_body["options"]["temperature"] == 0
    assert posted_body["stream"] is False
    assert posted_body["model"] == "llama3.1:8b"
    assert posted_body["messages"] == [{"role": "user", "content": "hi"}]


def test_explicit_options_can_override_the_temperature_default():
    session = StubSession(_payload())

    generate(
        [{"role": "user", "content": "hi"}],
        model="llama3.1:8b", url="http://localhost:11434", session=session,
        options={"temperature": 0.7},
    )

    posted_body = session.calls[0][1]
    assert posted_body["options"]["temperature"] == 0.7


def test_raises_on_missing_message_content():
    session = StubSession({
        "message": {"role": "assistant"},
        "prompt_eval_count": 10, "eval_count": 5,
        "total_duration": 1, "load_duration": 0,
    })

    try:
        generate(
            [{"role": "user", "content": "hi"}],
            model="llama3.1:8b", url="http://localhost:11434", session=session,
        )
        assert False, "expected a ValueError for missing message content"
    except ValueError:
        pass


def test_raises_on_empty_message_content():
    session = StubSession(_payload(content=""))

    try:
        generate(
            [{"role": "user", "content": "hi"}],
            model="llama3.1:8b", url="http://localhost:11434", session=session,
        )
        assert False, "expected a ValueError for empty message content"
    except ValueError:
        pass
