"""Password hashing and JWT issuance/verification for the API.

Uses Passlib (bcrypt) for hashing and PyJWT (HS256) for tokens -- no
hand-rolled crypto. See docs/superpowers/plans/2026-08-02-api-and-access-control.md
(Task 3).
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

# Obviously-a-dev-default: real deployments must set JWT_SECRET in the
# environment. Never commit a real secret here.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me-before-deploying-anywhere-real")
JWT_ALGORITHM = "HS256"
DEFAULT_TTL = timedelta(hours=8)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password):
    return _pwd_context.hash(password)


def verify_password(password, password_hash):
    return _pwd_context.verify(password, password_hash)


def create_token(username, roles, *, secret=JWT_SECRET, ttl=DEFAULT_TTL):
    """Issue a signed JWT carrying username and roles, with an exp claim."""
    payload = {
        "sub": username,
        "roles": list(roles),
        "exp": datetime.now(timezone.utc) + ttl,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_token(token, *, secret=JWT_SECRET):
    """Verify and decode a token. Returns {"username": ..., "roles": [...]}.

    Raises jwt's exceptions (ExpiredSignatureError, InvalidSignatureError,
    DecodeError, etc. -- all subclasses of InvalidTokenError) on any invalid
    token; callers turn those into 401s.
    """
    payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    return {"username": payload["sub"], "roles": payload.get("roles", [])}
