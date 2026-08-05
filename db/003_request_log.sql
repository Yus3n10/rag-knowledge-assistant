-- Phase 4d Task 1: request log for the cost/latency dashboard.
--
-- Not part of docker-entrypoint-initdb.d (which only runs on a fresh
-- volume). Apply it directly to the running container, e.g.:
--   docker compose exec -T db psql -U rag -d rag -f db/003_request_log.sql

CREATE TABLE request_log (
    id                      SERIAL PRIMARY KEY,
    asked_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    question                TEXT,
    username                TEXT,
    roles                   TEXT[],
    provider                TEXT,
    model                   TEXT,
    prompt_tokens           INT,
    completion_tokens       INT,
    latency_s               DOUBLE PRECISION,
    citation_count          INT,
    ungrounded_number_count INT,
    refused                 BOOLEAN,
    k                       INT
);
