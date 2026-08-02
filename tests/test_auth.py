from datetime import timedelta

import jwt
import pytest

from api.auth import create_token, decode_token, hash_password, verify_password


def test_valid_password_verifies_against_its_hash():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_wrong_password_fails_verification():
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_token_round_trips_username_and_roles():
    token = create_token("officer", ["safety_officer"])

    decoded = decode_token(token)

    assert decoded["username"] == "officer"
    assert decoded["roles"] == ["safety_officer"]


def test_expired_token_is_rejected():
    token = create_token("viewer", [], ttl=timedelta(seconds=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_token_signed_with_a_different_secret_is_rejected():
    token = create_token("viewer", [], secret="a-completely-different-secret")

    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(token)


def test_tampered_payload_is_rejected():
    token = create_token("viewer", [])
    header, payload, signature = token.split(".")
    # Flip the last character of the payload segment -- corrupts the claims
    # without touching the signature, so this must fail verification.
    flipped = "A" if payload[-1] != "A" else "B"
    tampered = ".".join([header, payload[:-1] + flipped, signature])

    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered)
