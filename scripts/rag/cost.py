"""Cost model for the dashboard: turn measured token counts into USD.

Never invent a dollar figure for a model this table doesn't know -- an
unpriced request must surface as unpriced (None), not silently count as
free. See docs/superpowers/plans/2026-08-03-cost-and-latency-dashboard.md
(Task 3).
"""

# USD per MILLION tokens, keyed by (provider, model): (prompt_rate, completion_rate).
#
# ollama entries are 0.0 -- local inference has no marginal per-token cost.
#
# groq/llama-3.1-8b-instant: $0.05 / $0.08 per million prompt/completion
# tokens. Source: web search of Groq's published pricing (aggregated from
# cloudzero.com/blog/groq-pricing, aipricing.guru/groq-pricing, and
# getmaxim.ai's Groq cost calculator), checked 2026-08-06. Groq's official
# console pricing page is the source of truth going forward -- re-verify
# there before trusting this number for a real spend report.
RATES_PER_MILLION_TOKENS = {
    ("ollama", "llama3.1:8b"): (0.0, 0.0),
    ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
}


def cost_usd(provider, model, prompt_tokens, completion_tokens):
    """USD cost of one request, or None if (provider, model) has no rate.

    None (never 0.0) for an unknown model -- pricing an unknown model at
    zero is how a dashboard quietly understates total spend.
    """
    rates = RATES_PER_MILLION_TOKENS.get((provider, model))
    if rates is None:
        return None
    prompt_rate, completion_rate = rates
    return (prompt_tokens / 1_000_000) * prompt_rate + (completion_tokens / 1_000_000) * completion_rate
