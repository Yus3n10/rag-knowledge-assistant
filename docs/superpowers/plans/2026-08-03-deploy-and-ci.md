# Phase 4c: Deployment and CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Tests run automatically on every push, and the system is reachable at a public URL.

**Architecture:** GitHub Actions runs the hermetic test suites with no services. The deployed stack runs Postgres+pgvector and the API in Docker on an Oracle Cloud free-tier ARM VM, with **generation served by a hosted free tier rather than local Ollama** — see the constraint below.

## Prerequisites the builder must do (Claude cannot)

These are external accounts and cannot be automated. Work that does not depend on them is sequenced first.

- [ ] **Create the GitHub repository** and add it as a remote. `git remote -v` is currently empty — GitHub Actions cannot run without this.
- [ ] **Get a Groq API key** (free tier, no card) at console.groq.com, or a Cloudflare Workers AI token.
- [ ] **Provision an Oracle Cloud free-tier ARM instance** (Ampere A1, up to 4 OCPU / 24GB, Ubuntu 22.04). Note: free ARM capacity is frequently unavailable in popular regions and often needs repeated attempts. This is normal, not a misconfiguration.

## Global Constraints

- **The deployed demo must NOT run `llama3.1:8b`.** Oracle's free ARM VM has no GPU. An 8B model on ARM CPU turns ~10s local latency into minutes, which makes the public link useless. `PROJECT_BRIEF.md` already specifies a hosted free tier for the demo and Ollama for development — this phase implements that split rather than reconsidering it.
- **Never commit secrets.** `JWT_SECRET`, `GROQ_API_KEY`, and the database password come from the environment. Add `.env` to `.gitignore` (already done) and verify no key reaches a commit.
- Dependencies: no new Python packages. Groq exposes an OpenAI-compatible HTTP API and `requests` is already present — do NOT add the `groq` or `openai` SDK for what is one POST.
- `data/` stays committed and must never be gitignored.
- Commit messages carry NO AI/Claude/Anthropic attribution and NO Co-Authored-By trailer.

## Measured inputs

| Fact | Value |
|---|---|
| Python tests | 154, hermetic — stub DB, embedder, generator |
| Frontend tests | 16 (vitest) |
| Corpus | 965 chunks, committed to the repo |
| Local warm `/ask` | ~8-12s with `llama3.1:8b` |
| Index build cost | ~75k embedding tokens, idempotent |

Because the suites are hermetic, **CI needs no services and no secrets.** That is a direct payoff from stubbing dependencies in Phase 4a and should stay true — if a future test needs a live Postgres, it belongs behind a marker that CI skips.

---

## Task 1: CI (no external prerequisites)

**Files:** `.github/workflows/ci.yml`

- [ ] Workflow on push and PR: Python 3.11, `pip install -r requirements.txt`, `python -m pytest`; then Node, `npm ci` and `npm test -- --run` in `web/`.
- [ ] **Also run `python -m eval.validate_eval`.** It needs only committed files, and it enforces the project's headline claim: every eval citation resolves to a real corpus paragraph. A typo'd citation should turn CI red.
- [ ] Verify locally with `act` if available; otherwise confirm the YAML parses and every command it runs succeeds locally.
- [ ] Commit. (It cannot actually run until the remote exists.)

## Task 2: LLM provider abstraction

**Files:** `scripts/rag/generate.py`, `tests/test_generate.py`

`generate()` currently posts to `{url}/api/chat` in Ollama's format. Add a second provider without breaking the first.

- [ ] `generate(messages, *, provider="ollama", model, url=None, api_key=None, session=None, options=None) -> (text, stats)`.
- [ ] `provider="groq"` posts to `https://api.groq.com/openai/v1/chat/completions` with a bearer key, OpenAI chat format, and maps `usage.prompt_tokens` / `usage.completion_tokens` into the same `stats` shape Ollama returns. **The stats contract must not change** — Phase 4d's dashboard and every existing caller depend on it.
- [ ] `temperature=0` default for both, so eval runs stay comparable across providers.
- [ ] TDD with a stub session for both providers, showing the RED step. Assert both return identical `stats` keys.
- [ ] `api/main.py` selects the provider from environment variables, defaulting to Ollama so local behaviour is unchanged.
- [ ] **Run the answer eval against Groq** and record the numbers next to the `llama3.1:8b` baseline (citation validity 1.00, gold citation 0.92, ungrounded numbers 0.00, refusal 1.00). A different model will score differently — **report it, do not tune.** Two providers measured on the same 45 questions is a stronger result than one.
- [ ] Commit.

## Task 3: Container images

**Files:** `Dockerfile`, `web/Dockerfile`, `docker-compose.prod.yml`

- [ ] API image on `python:3.11-slim`. **Must build for `linux/arm64`** — the Oracle instance is Ampere. Build with `docker buildx --platform linux/arm64` and verify, since a silently amd64 image will fail only at deploy time.
- [ ] Frontend: build static assets, serve via nginx (or serve them from FastAPI to avoid a second container — simpler, and this is one app).
- [ ] `docker-compose.prod.yml` wiring pgvector + API, reading all secrets from the environment.
- [ ] **The corpus is committed, so the deployed database still needs indexing once.** Document the one-time `python -m scripts.build_index` step against the deployed Postgres, and note it needs an embedding provider — either Ollama's small `nomic-embed-text` (137M, fine on ARM CPU) or a hosted embedding endpoint. Decide and record which.
- [ ] Verify the ARM image runs locally under emulation before deploying.
- [ ] Commit.

## Task 4: Deploy

- [ ] Open ports 80/443 in the Oracle security list **and** in the instance's own `iptables` — Oracle Ubuntu images ship with restrictive local rules, and forgetting the second one is the single most common cause of "the security list looks right but nothing connects."
- [ ] Install Docker, clone the repo, set environment secrets, `docker compose -f docker-compose.prod.yml up -d`.
- [ ] Run the one-time index build. Verify `SELECT count(*) FROM chunks` returns 965.
- [ ] `GET /health` over the public IP. Then log in as both demo users and ask the gated question — **the same two-user check as Phase 4a/4b, now over the public internet.** Paste both responses.
- [ ] Record deployed latency. It will differ from local; that number belongs in the README and in 4d's dashboard.
- [ ] Optional: a DNS name and Let's Encrypt certificate. Nice, not required for the done-criterion.
- [ ] Update the README with the live URL and the deployed-latency figure.
- [ ] Commit.

---

## Expectations

The likely failure here is not code. It is Oracle capacity errors, ARM image mismatches, and firewall rules — all environmental, all normal, none a sign the application is wrong.

**Do not weaken the security posture to get a deploy working.** If the public instance would need the JWT secret committed, or `viewer` given `safety_officer` to make a demo look better, stop and report it. The two-user difference is the thing being demonstrated; defeating it to ship would remove the reason for shipping.
