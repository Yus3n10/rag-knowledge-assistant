CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    chunk_id      TEXT PRIMARY KEY,
    paragraph_id  TEXT NOT NULL,
    section_id    TEXT NOT NULL,
    subpart       TEXT NOT NULL,
    heading_trail TEXT NOT NULL,
    text          TEXT NOT NULL,
    embedding     vector(768)
);

CREATE INDEX chunks_paragraph_id_idx ON chunks (paragraph_id);
