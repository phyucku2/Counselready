"""Time-based one-time passwords and recovery codes.

No third party is involved: TOTP (RFC 6238) is a shared secret and a clock, so the
user's existing authenticator app is the whole second factor. That keeps MFA inside
the Azure-only posture (ADR-0002) and free of per-message cost.

SMS was rejected deliberately. It is the weakest common second factor because of
SIM-swap, and for this product it is worse than that: a code sent to a phone on a
shared family plan can land in the hands of the exact person the factor exists to keep
out.

**The TOTP secret is encrypted at rest.** Stored in plaintext, a database disclosure
would let an attacker generate valid codes forever — the second factor would be
decorative. Recovery codes are high-entropy random, so a SHA-256 digest is the right
store for them (same reasoning as refresh tokens: Argon2's slowness buys nothing
against something that cannot be guessed).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

import pyotp
from cryptography.fernet import Fernet, InvalidToken

ISSUER = "CounselReady"

# 160 bits, the RFC 4226 recommendation, base32-encoded for authenticator apps.
SECRET_BYTES = 20

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 10

# One step either side of now, absorbing ordinary clock drift between the user's phone
# and the server. Wider would materially enlarge the window an intercepted code stays
# usable in.
VALID_WINDOW = 1
TOTP_INTERVAL_SECONDS = 30


class MfaNotConfiguredError(RuntimeError):
    """No encryption key is configured, so MFA secrets cannot be stored safely."""


class SecretDecryptionError(RuntimeError):
    """A stored secret could not be decrypted — wrong key, or corrupted data."""


@dataclass(frozen=True)
class Enrolment:
    """What a fresh enrolment produces. The plaintext parts are shown once."""

    encrypted_secret: str
    provisioning_uri: str
    recovery_codes: list[str]
    recovery_digests: list[str]


def generate_encryption_key() -> str:
    """A new Fernet key. For operators provisioning MFA_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()


def _cipher(key: str | None) -> Fernet:
    if not key:
        raise MfaNotConfiguredError("MFA_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise MfaNotConfiguredError("MFA_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt_secret(secret: str, *, key: str | None) -> str:
    return _cipher(key).encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str, *, key: str | None) -> str:
    try:
        return _cipher(key).decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError("stored MFA secret could not be decrypted") from exc


def generate_recovery_code() -> str:
    """A single-use code, grouped for legibility since people type these by hand."""
    raw = secrets.token_hex(RECOVERY_CODE_BYTES).upper()
    return f"{raw[:5]}-{raw[5:10]}-{raw[10:15]}-{raw[15:20]}"


def hash_recovery_code(code: str) -> str:
    """Digest for storage. Normalized so formatting differences do not reject a
    correct code a user typed without the dashes."""
    return hashlib.sha256(normalize_recovery_code(code).encode()).hexdigest()


def normalize_recovery_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def begin_enrolment(*, email: str, key: str | None) -> Enrolment:
    """Mint a secret, its provisioning URI, and a set of recovery codes.

    Nothing here is active until the user proves they can produce a code from it — an
    enrolment that activated on issue would lock out anyone whose scan silently failed.
    """
    secret = pyotp.random_base32(length=32)
    uri = pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS).provisioning_uri(
        name=email, issuer_name=ISSUER
    )
    codes = [generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    return Enrolment(
        encrypted_secret=encrypt_secret(secret, key=key),
        provisioning_uri=uri,
        recovery_codes=codes,
        recovery_digests=[hash_recovery_code(code) for code in codes],
    )


def counter_for(timestamp: int) -> int:
    """The TOTP step a timestamp falls in.

    Recorded after each success so the same code cannot be replayed inside its own
    validity window — without this, a code shoulder-surfed or intercepted stays usable
    for up to ninety seconds.
    """
    return timestamp // TOTP_INTERVAL_SECONDS


def matching_counter(secret: str, code: str, timestamp: int) -> int | None:
    """The step a valid code belongs to, or None if it is not valid.

    Needed because the accepted code may be from an adjacent step; recording `now`
    would leave the neighbouring step replayable.
    """
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit():
        return None
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS)
    current = counter_for(timestamp)
    for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):
        step = current + offset
        if secrets.compare_digest(totp.at(step * TOTP_INTERVAL_SECONDS), cleaned):
            return step
    return None


def verify_code(secret: str, code: str, *, at_timestamp: int) -> bool:
    """True when `code` is valid for `secret` at `at_timestamp`.

    Thin wrapper over `matching_counter`, which is what callers actually need — a bare
    boolean would leave them unable to record which step was consumed and therefore
    unable to block replay.
    """
    return matching_counter(secret, code, at_timestamp) is not None
