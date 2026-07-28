"""Access and refresh tokens.

Two different things with two different threat models:

* **Access token** — a short-lived signed JWT. Never stored server-side; the signature
  is the whole check. Short TTL is what limits the damage of one leaking.
* **Refresh token** — a long, opaque random string. Stored only as a SHA-256 digest, so
  a database disclosure does not yield usable tokens.

The refresh digest uses SHA-256 rather than Argon2 on purpose. Argon2 is slow by design
to make *guessing* a low-entropy human password expensive. A 256-bit random token cannot
be guessed, so the slowness would buy nothing and would put a deliberate CPU cost on
every refresh.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)

# 32 bytes of urlsafe randomness — 256 bits of entropy.
REFRESH_TOKEN_BYTES = 32


class InvalidAccessTokenError(Exception):
    """The access token is missing, malformed, expired, or wrongly signed."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


def issue_access_token(
    *, user_id: uuid.UUID, session_id: uuid.UUID, secret: str, now: datetime
) -> str:
    """Sign a short-lived access token.

    `now` is injected rather than read from the clock so expiry behaviour is testable
    without sleeping and without time-of-day flakiness.
    """
    expires_at = now + ACCESS_TOKEN_TTL
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> AccessTokenClaims:
    """Verify and decode an access token, or raise `InvalidAccessTokenError`.

    Expiry is checked against the real clock by PyJWT. Tests exercise the expired path
    by issuing a token with a past `now`, which needs no clock injection here.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            # Pinning the algorithm list is what prevents an attacker presenting an
            # unsigned ("alg": "none") or asymmetric-confusion token.
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "sid"]},
        )
    except InvalidTokenError as exc:
        raise InvalidAccessTokenError(str(exc)) from exc

    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidAccessTokenError("token claims are malformed") from exc


def generate_refresh_token() -> str:
    """A new opaque refresh token. Returned once, never stored in this form."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """The digest stored in the database."""
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_expiry(now: datetime) -> datetime:
    return now + REFRESH_TOKEN_TTL
