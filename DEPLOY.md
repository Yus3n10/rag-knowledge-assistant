# Deploy runbook

Target: Oracle Cloud free-tier Ampere A1 (ARM64, Ubuntu 22.04, no GPU).

## Why ARM changes the stack

- Images must be built for `linux/arm64` (see build command below). An amd64
  image will not run on the host at all.
- Generation does NOT run locally. `llama3.1:8b` on ARM CPU turns ~10s
  latency into minutes. Generation goes to Groq (`LLM_PROVIDER=groq`), a
  hosted free tier.
- Embeddings DO still run locally, on Ollama. `nomic-embed-text` is a 137M
  model, CPU-viable even on ARM -- this is not the 8B model, and it must stay
  the same model that built the committed index, or retrieval quality
  silently breaks (see `docker-compose.prod.yml` comment for the full
  reasoning).

## 1. Build the images

Build the frontend first -- the API image copies `web/dist` into itself:

```bash
cd web && npm ci && npm run build && cd ..
```

Then build the API image for the target platform:

```bash
docker buildx build --platform linux/arm64 -t rag-api:arm64 .
```

On the ARM host itself this can also be built natively without `buildx
--platform` (or built once locally with buildx and pushed to a registry the
host pulls from). Cross-building on an amd64 dev machine requires QEMU
emulation, which Docker Desktop provides out of the box.

## 2. Required environment variables

None of these have defaults in `docker-compose.prod.yml` -- an unset value
fails `docker compose up` immediately instead of falling back to a dev
secret.

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password for the `rag` user/db |
| `JWT_SECRET` | Signs/verifies API auth tokens |
| `GROQ_API_KEY` | Groq API key for generation (console.groq.com, free tier) |

Optional, with sane defaults:

| Variable | Default | Purpose |
|---|---|---|
| `GEN_MODEL` | `llama-3.1-8b-instant` | Groq model name |

Set these in the host shell or a `.env` file next to
`docker-compose.prod.yml` (never commit it -- already gitignored).

## 3. Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

This starts three services: `db` (pgvector), `ollama` (embeddings only),
`api`. The `ollama` container needs the embedding model pulled once:

```bash
docker compose -f docker-compose.prod.yml exec ollama ollama pull nomic-embed-text
```

## 4. One-time index build

The corpus (965 chunks) is committed under `data/`, but the database starts
empty -- indexing has to run once against the deployed Postgres:

```bash
DATABASE_URL=postgresql://rag:$POSTGRES_PASSWORD@localhost:5433/rag \
OLLAMA_URL=http://localhost:11434 \
  python -m scripts.build_index
```

Run this from a machine that can reach the deployed `db` and `ollama` ports
(or `docker compose exec` into a container with the repo mounted, adjusting
the URLs to the in-network service names `db`/`ollama`).

## 5. Verify

```bash
curl http://<host>/health
# {"status": "ok", "chunk_count": 965}
```

Then log in as both demo users and confirm the gated-content difference
still holds over the public network (same check as Phase 4a/4b, now remote):

```bash
curl -X POST http://<host>/auth/login -H 'Content-Type: application/json' \
  -d '{"username": "viewer", "password": "..."}'
curl -X POST http://<host>/auth/login -H 'Content-Type: application/json' \
  -d '{"username": "officer", "password": "..."}'
```

Use each token as a bearer credential against `POST /ask` and confirm the
`viewer` token is refused gated content that the `safety_officer` token can
see.

Finally, open `http://<host>/` in a browser -- the API serves the built
frontend (`web/dist`) as static files at `/`, so no separate web server or
reverse proxy is needed.
