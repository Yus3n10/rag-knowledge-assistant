-- Phase 4a Task 1: access-control schema.
--
-- SYNTHETIC GATING NOTICE: all OSHA 29 CFR text in this corpus is public
-- domain. Gating 1910.147 behind the safety_officer role below does not
-- reflect any real confidentiality classification of that content -- it
-- exists solely to demonstrate that role-based access control is wired up
-- and enforced end to end (in the retrieval SQL, not filtered after the
-- fact). Presenting this gate as a real classification would misrepresent
-- the corpus.
--
-- This file is NOT part of docker-entrypoint-initdb.d (which only runs on a
-- fresh volume). Apply it directly to the running container, e.g.:
--   docker compose exec -T db psql -U rag -d rag -f db/002_access_control.sql

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    roles         TEXT[] NOT NULL DEFAULT '{}'
);

ALTER TABLE chunks ADD COLUMN required_role TEXT;
-- NULL means public. Every existing chunk defaults to NULL on add, so no
-- explicit backfill statement is needed -- this comment documents that intent.

UPDATE chunks
SET required_role = 'safety_officer'
WHERE section_id LIKE '1910.147%';
