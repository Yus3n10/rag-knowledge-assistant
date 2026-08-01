from scripts.rag.prompt import build_messages


CHUNKS = [
    {"chunk_id": "chunk-1", "paragraph_id": "1910.147(e)(3)",
     "text": "1910.147 The control of hazardous energy (lockout/tagout). > Release from lockout or tagout.\n\nOnly the employee who applied the device may remove it.",
     "distance": 0.12},
    {"chunk_id": "chunk-2", "paragraph_id": "1910.147(c)(1)",
     "text": "1910.147 The control of hazardous energy (lockout/tagout). > Energy control program.\n\nThe employer shall establish a program.",
     "distance": 0.34},
]


def test_every_chunk_paragraph_id_appears_bracketed_in_prompt():
    messages = build_messages("who may remove a lockout device", CHUNKS)
    user_content = messages[-1]["content"]

    for chunk in CHUNKS:
        assert f"[{chunk['paragraph_id']}]" in user_content


def test_chunk_order_is_preserved():
    messages = build_messages("q", CHUNKS)
    user_content = messages[-1]["content"]

    first_pos = user_content.index("[1910.147(e)(3)]")
    second_pos = user_content.index("[1910.147(c)(1)]")
    assert first_pos < second_pos


def test_question_text_appears_in_prompt():
    messages = build_messages("who may remove a lockout device", CHUNKS)
    user_content = messages[-1]["content"]

    assert "who may remove a lockout device" in user_content


def test_refusal_instruction_present_in_system_message():
    messages = build_messages("q", CHUNKS)
    system_content = messages[0]["content"]

    assert "does not contain the answer" in system_content.lower() or \
        "say so" in system_content.lower()


def test_only_from_provided_text_instruction_present():
    messages = build_messages("q", CHUNKS)
    system_content = messages[0]["content"]

    assert "only" in system_content.lower()


def test_empty_chunk_list_still_yields_refusal_instruction():
    messages = build_messages("who may remove a lockout device", [])
    system_content = messages[0]["content"]

    assert "does not contain the answer" in system_content.lower() or \
        "say so" in system_content.lower()


def test_build_messages_returns_list_of_role_content_dicts():
    messages = build_messages("q", CHUNKS)

    assert isinstance(messages, list)
    assert len(messages) >= 1
    for m in messages:
        assert "role" in m
        assert "content" in m


def test_prompt_version_constant_exists():
    from scripts.rag.prompt import PROMPT_VERSION
    assert isinstance(PROMPT_VERSION, str)
    assert len(PROMPT_VERSION) > 0
