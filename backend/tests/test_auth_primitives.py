"""Password hashing and token primitives."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    hash_password,
    validate_password,
    verify_password,
    verify_password_against,
)
from app.auth.tokens import (
    InvalidAccessTokenError,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
    issue_access_token,
)

SYNTHETIC_PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"
# Near the real clock on purpose: PyJWT rejects a token whose `iat` is in the
# future, so a hardcoded future timestamp would fail for the wrong reason.
NOW = datetime.now(UTC)


def test_a_password_round_trips() -> None:
    assert verify_password(SYNTHETIC_PASSWORD, hash_password(SYNTHETIC_PASSWORD))


def test_a_wrong_password_is_rejected() -> None:
    assert not verify_password("not-the-password", hash_password(SYNTHETIC_PASSWORD))


def test_the_same_password_hashes_differently_each_time() -> None:
    """Distinct salts: identical stored hashes would reveal that two accounts share a
    password."""
    assert hash_password(SYNTHETIC_PASSWORD) != hash_password(SYNTHETIC_PASSWORD)


def test_the_hash_does_not_contain_the_password() -> None:
    assert SYNTHETIC_PASSWORD not in hash_password(SYNTHETIC_PASSWORD)


def test_the_stored_hash_identifies_argon2id() -> None:
    """Pinned deliberately: a dependency bump that silently changed the algorithm
    should fail here rather than in production."""
    assert hash_password(SYNTHETIC_PASSWORD).startswith("$argon2id$")


def test_a_short_password_is_refused() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password("x" * (MIN_PASSWORD_LENGTH - 1))


def test_an_absurdly_long_password_is_refused() -> None:
    """Unbounded input means unbounded hashing work an attacker can request."""
    with pytest.raises(WeakPasswordError):
        validate_password("x" * 10_000)


def test_a_malformed_stored_hash_verifies_false_rather_than_raising() -> None:
    assert not verify_password(SYNTHETIC_PASSWORD, "not-a-hash")


def test_verifying_against_a_missing_account_returns_false() -> None:
    assert not verify_password_against(SYNTHETIC_PASSWORD, None)


def test_a_missing_account_costs_about_as_much_as_a_real_one() -> None:
    """Account-enumeration guard: skipping the hash for an unknown email makes that
    path measurably faster and turns login into an oracle. Timing is noisy, so this
    asserts only the order of magnitude, which is what distinguishes 'hashed' from
    'returned immediately'."""
    stored = hash_password(SYNTHETIC_PASSWORD)

    start = time.perf_counter()
    verify_password_against("wrong-password-entirely", stored)
    real = time.perf_counter() - start

    start = time.perf_counter()
    verify_password_against("wrong-password-entirely", None)
    missing = time.perf_counter() - start

    assert missing > real / 10, "the missing-account path skipped the hash"


def test_an_access_token_round_trips() -> None:
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    token = issue_access_token(user_id=user_id, session_id=session_id, secret=SECRET, now=NOW)

    claims = decode_access_token(token, secret=SECRET)
    assert claims.user_id == user_id
    assert claims.session_id == session_id


def test_a_token_signed_with_another_key_is_rejected() -> None:
    token = issue_access_token(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        secret="SYNTHETIC_OTHER_KEY_ALSO_LONG_ENOUGH_HS256",
        now=NOW,
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, secret=SECRET)


def test_an_expired_token_is_rejected() -> None:
    stale = datetime.now(UTC) - timedelta(days=1)
    token = issue_access_token(
        user_id=uuid.uuid4(), session_id=uuid.uuid4(), secret=SECRET, now=stale
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, secret=SECRET)


def test_an_unsigned_token_is_rejected() -> None:
    """The `alg: none` attack — refused because the algorithm list is pinned."""
    import jwt

    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "sid": str(uuid.uuid4()),
            "iat": int(NOW.timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(forged, secret=SECRET)


def test_a_garbage_token_is_rejected() -> None:
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not.a.token", secret=SECRET)


def test_refresh_tokens_are_unique_and_long() -> None:
    tokens = {generate_refresh_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 32 for token in tokens)


def test_the_refresh_digest_does_not_contain_the_token() -> None:
    """A database disclosure must not hand over usable tokens."""
    token = generate_refresh_token()
    digest = hash_refresh_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_the_refresh_digest_is_deterministic() -> None:
    token = generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
