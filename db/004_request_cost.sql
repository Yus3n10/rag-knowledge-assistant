-- Phase 4d Task 4 (Step 1): computed cost per request, for the dashboard.
--
-- Nullable on purpose: an unpriced (provider, model) stores SQL NULL, not
-- 0.0, so SUM(cost_usd) skips it instead of silently counting it as free.
-- See scripts/rag/cost.py.
--
-- Not part of docker-entrypoint-initdb.d. Apply directly, e.g.:
--   docker compose exec -T db psql -U rag -d rag -f db/004_request_cost.sql

ALTER TABLE request_log ADD COLUMN cost_usd DOUBLE PRECISION;
