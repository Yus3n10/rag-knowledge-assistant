"""Build the messages sent to the LLM from a question and retrieved chunks.

Versioned separately from retrieval/generation so a score change can be
attributed to a wording change here and nowhere else.
"""

PROMPT_VERSION = "p3-v1"

SYSTEM_PROMPT = (
    "You are an OSHA regulation assistant. Answer ONLY using the regulation "
    "text provided below, in the user message. Do not use any outside or "
    "prior knowledge.\n\n"
    "For every claim you make, cite the paragraph ID it came from in square "
    "brackets immediately after the claim, e.g. [1910.147(e)(3)]. Every "
    "sentence of your answer must be traceable to a citation.\n\n"
    "If the provided text does not contain the answer, say so explicitly "
    "(for example: \"The provided text does not contain this information.\") "
    "and cite nothing."
)


def build_messages(question, chunks):
    """Return the chat messages list for scripts.rag.generate.generate.

    chunks is the list[dict] returned by scripts.rag.retrieve.search, already
    ordered most-relevant-first; that order is preserved verbatim in the
    rendered context. An empty chunks list still produces a user message
    instructing refusal, rather than a bare question.
    """
    if chunks:
        context = "\n\n".join(
            f"[{chunk['paragraph_id']}]\n{chunk['text']}" for chunk in chunks
        )
    else:
        context = "(No regulation text was retrieved for this question.)"

    user_content = f"{context}\n\nQuestion: {question}"

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
