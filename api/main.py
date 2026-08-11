"""FastAPI wrapper over the RAG answer pipeline.

See docs/superpowers/plans/2026-08-02-api-and-access-control.md (Task 4).

Auth: POST /auth/login exchanges username+password for a JWT (api/auth.py).
POST /ask requires a bearer token. The caller's roles come from the token's
claims ONLY -- the request body must never be allowed to specify roles, or
any caller could grant themselves access to gated content.
"""

import logging
import os
import re

import jwt
import psycopg
import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.auth import create_token, decode_token, verify_password
from scripts.rag.answer import answer_question
from scripts.rag.cost import cost_usd
from scripts.rag.embed import embed_texts
from scripts.rag.generate import generate
from scripts.rag.prompt import SYSTEM_PROMPT
from scripts.rag.requestlog import record_request

logger = logging.getLogger(__name__)

DEFAULTS = {
    "DATABASE_URL": "postgresql://rag:ragdev@localhost:5433/rag",
    "OLLAMA_URL": "http://localhost:11434",
    "EMBED_MODEL": "nomic-embed-text",
    "CF_EMBED_MODEL": "@cf/baai/bge-base-en-v1.5",  # 768-dim, matches vector(768)
    "GEN_MODEL": "llama3.1:8b",
    "GROQ_GEN_MODEL": "llama-3.1-8b-instant",
}

K = 10  # measured knee, see docs/RETRIEVAL_FINDINGS.md -- do not raise to chase a score

# Pulled from SYSTEM_PROMPT's own refusal example rather than copied by hand,
# so a wording change there can never silently drift out of sync with what
# /ask treats as a refusal.
#
# Match only the stable HEAD of that sentence. llama3.1:8b keeps the head and
# paraphrases the tail ("...does not contain information about X"), so matching
# the full example sentence scored genuine refusals as answers and undercounted
# the refusal rate. See tests/test_api.py::test_ask_records_refused_when_the_
# model_paraphrases_the_refusal for the real output that exposed this.
_REFUSAL_EXAMPLE = re.search(r'for example: "([^"]+)"', SYSTEM_PROMPT).group(1)
REFUSAL_PREFIX = _REFUSAL_EXAMPLE.split(" this information")[0].lower()


def _provider_and_model():
    """The same provider/model resolution get_generator() uses, exposed
    separately so /ask can log what was actually asked for without having
    to unpack it out of the generator closure."""
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    # Model names are provider-specific: Groq does not serve "llama3.1:8b"
    # (an Ollama tag), so defaulting to it under LLM_PROVIDER=groq fails every
    # request. Same failure shape as the embedding default -- see get_embedder.
    default_model = (DEFAULTS["GROQ_GEN_MODEL"] if provider == "groq"
                     else DEFAULTS["GEN_MODEL"])
    model = os.environ.get("LLM_MODEL") or os.environ.get("GEN_MODEL", default_model)
    return provider, model


app = FastAPI(title="OSHA RAG API")
security = HTTPBearer()


# --- dependencies (real connections/clients; tests override all three via
# app.dependency_overrides so no test ever touches Postgres or Ollama) -------

def get_conn():
    conn = psycopg.connect(os.environ.get("DATABASE_URL", DEFAULTS["DATABASE_URL"]))
    try:
        yield conn
    finally:
        conn.close()


def get_embedder():
    session = requests.Session()
    provider = os.environ.get("EMBED_PROVIDER", "ollama")
    # The default model differs per provider: an EMBED_MODEL left over from a
    # local Ollama run would be a meaningless name to Cloudflare, and the
    # resulting 404 is a much worse failure than picking the right default.
    default_model = (DEFAULTS["CF_EMBED_MODEL"] if provider == "cloudflare"
                     else DEFAULTS["EMBED_MODEL"])
    model = os.environ.get("EMBED_MODEL", default_model)
    url = os.environ.get("OLLAMA_URL", DEFAULTS["OLLAMA_URL"])
    account_id = os.environ.get("CF_ACCOUNT_ID")
    api_token = os.environ.get("CF_API_TOKEN")

    def embedder(texts):
        vectors, _tokens = embed_texts(
            texts, model=model, url=url, session=session, provider=provider,
            account_id=account_id, api_token=api_token,
        )
        return vectors

    return embedder


def get_generator():
    session = requests.Session()
    provider, model = _provider_and_model()
    url = os.environ.get("OLLAMA_URL", DEFAULTS["OLLAMA_URL"])
    api_key = os.environ.get("GROQ_API_KEY")

    def generator(messages):
        return generate(messages, provider=provider, model=model, url=url,
                         api_key=api_key, session=session)

    return generator


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token")


# --- request bodies ------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class AskRequest(BaseModel):
    question: str
    # Deliberately no "roles" field: FastAPI/Pydantic ignores unknown JSON
    # keys by default, so a client that sends one anyway (see
    # tests/test_api.py::test_ask_ignores_roles_claimed_in_the_request_body)
    # has it silently dropped rather than accepted.


# --- endpoints ------------------------------------------------------------------

@app.get("/health")
def health(conn=Depends(get_conn)):
    """Liveness plus the configuration /ask depends on.

    A database-only check reported "ok" through a deploy where every /ask
    failed, because the generation model name was wrong for the provider.
    Reporting the resolved provider and model makes that class of
    misconfiguration visible without having to make a real request -- which
    on a hosted free tier costs real quota.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks")
        [chunk_count] = cur.fetchone()

    llm_provider, llm_model = _provider_and_model()
    embed_provider = os.environ.get("EMBED_PROVIDER", "ollama")

    # Credentials are reported present/absent, never echoed.
    missing = [name for name, value in (
        ("GROQ_API_KEY", os.environ.get("GROQ_API_KEY") if llm_provider == "groq" else "-"),
        ("CF_ACCOUNT_ID", os.environ.get("CF_ACCOUNT_ID") if embed_provider == "cloudflare" else "-"),
        ("CF_API_TOKEN", os.environ.get("CF_API_TOKEN") if embed_provider == "cloudflare" else "-"),
    ) if not value]

    return {
        "status": "ok" if not missing else "misconfigured",
        "chunk_count": chunk_count,
        "llm": f"{llm_provider}/{llm_model}",
        "embeddings": embed_provider,
        "missing_env": missing,
    }


@app.post("/auth/login")
def login(body: LoginRequest, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT password_hash, roles FROM users WHERE username = %s",
            (body.username,),
        )
        row = cur.fetchone()

    if row is None or not verify_password(body.password, row[0]):
        raise HTTPException(status_code=401, detail="invalid username or password")

    password_hash, roles = row
    token = create_token(body.username, roles)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/ask")
def ask(
    body: AskRequest,
    user=Depends(get_current_user),
    conn=Depends(get_conn),
    embedder=Depends(get_embedder),
    generator=Depends(get_generator),
):
    result = answer_question(
        body.question,
        k=K,
        conn=conn,
        embedder=embedder,
        generator=generator,
        roles=user["roles"],  # from the verified token only, never the body
    )

    provider, model = _provider_and_model()
    refused = not result["citations"] and REFUSAL_PREFIX in result["answer"].lower()
    try:
        record_request(
            conn,
            question=body.question,
            username=user["username"],
            roles=user["roles"],
            provider=provider,
            model=model,
            prompt_tokens=result["stats"]["prompt_tokens"],
            completion_tokens=result["stats"]["completion_tokens"],
            latency_s=result["stats"]["latency_s"],
            citation_count=len(result["citations"]),
            ungrounded_number_count=len(result["ungrounded_numbers"]),
            refused=refused,
            k=K,
            cost_usd=cost_usd(
                provider, model,
                result["stats"]["prompt_tokens"],
                result["stats"]["completion_tokens"],
            ),
        )
    except Exception:
        # record_request already swallows its own errors; this is a second
        # line of defense so a logging problem can never surface as an /ask
        # failure, no matter how record_request is wired up.
        logger.exception("failed to record request_log row")

    return {
        "answer": result["answer"],
        "citations": result["citations"],
        "citation_report": result["citation_report"],
        "ungrounded_numbers": result["ungrounded_numbers"],
        "retrieved": result["retrieved"],
        "stats": result["stats"],
    }


# --- static frontend --------------------------------------------------------
# Serves web/dist (the built Vite app) if present, e.g. in the production
# image. Mounted last and at "/" so it never shadows the routes above --
# Starlette tries routes in registration order, and exact-path routes always
# win over a mount before the mount's prefix match is even considered.
# Absent in the test/dev environment (web/dist isn't committed), so this is
# skipped there and /health, /auth/login, /ask are unaffected.
_dist = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
