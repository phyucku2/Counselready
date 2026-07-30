"""Password hashing.

Argon2id, the algorithm OWASP recommends for new applications. Parameters are stated
explicitly rather than inherited from library defaults so a dependency bump cannot
silently weaken them.

The verification helper deliberately does constant work whether or not the account
exists — see `verify_password_against`.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import HashingError, InvalidHashError, VerificationError
from argon2.low_level import Type

# OWASP's second recommended configuration: 19 MiB, 2 iterations, 1 degree of
# parallelism. Chosen over the higher-memory variant because it is the one that stays
# comfortable on a small container without pushing login latency into the seconds.
_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# A precomputed hash of a value no one can supply, used to burn the same CPU on a
# missing account as on a real one.
_DUMMY_HASH = _HASHER.hash("password-for-an-account-that-does-not-exist")

# Long enough to matter, short enough that a password manager's output fits. The upper
# bound exists because Argon2 hashes whatever it is given, and an unbounded password is
# an unbounded amount of hashing work an attacker can request.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


class WeakPasswordError(ValueError):
    """The password does not meet the length policy."""


def validate_password(password: str) -> None:
    """Raise `WeakPasswordError` if the password is unusable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    """Hash a password for storage. Validates the policy first."""
    validate_password(password)
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True when `password` matches `password_hash`."""
    try:
        return _HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError, HashingError):
        return False


def verify_password_against(password: str, password_hash: str | None) -> bool:
    """Verify, doing the same work when the account does not exist.

    Skipping the hash for an unknown email makes login measurably faster for
    non-existent accounts, which turns the endpoint into an account-enumeration oracle.
    For this product that is not an abstract concern: an abusive ex-partner probing
    whether their former spouse has an account is a plausible and harmful use of it.
    """
    if password_hash is None:
        # Burn the same CPU, discard the (always false) result.
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, password_hash)


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than we now require.

    Called after a successful login so hashes migrate forward as the parameters are
    raised, rather than staying at whatever was current when the account was created.
    """
    try:
        return _HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
