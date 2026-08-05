"""Record one row per answered question for the cost/latency dashboard.

See docs/superpowers/plans/2026-08-03-cost-and-latency-dashboard.md (Task 1).
A recording failure must never break answering -- record_request swallows
any error from the insert, logs it, and returns normally.
"""

import logging

logger = logging.getLogger(__name__)

INSERT_SQL = """
INSERT INTO request_log (
    question, username, roles, provider, model,
    prompt_tokens, completion_tokens, latency_s,
    citation_count, ungrounded_number_count, refused, k, cost_usd
) VALUES (
    %(question)s, %(username)s, %(roles)s, %(provider)s, %(model)s,
    %(prompt_tokens)s, %(completion_tokens)s, %(latency_s)s,
    %(citation_count)s, %(ungrounded_number_count)s, %(refused)s, %(k)s, %(cost_usd)s
)
"""


def record_request(conn, **fields):
    """Insert one request_log row. Never raises -- on any error, log it and
    return, so a dashboard problem can never become an API outage."""
    try:
        with conn.cursor() as cur:
            cur.execute(INSERT_SQL, fields)
        conn.commit()
    except Exception:
        logger.exception("failed to record request_log row")
