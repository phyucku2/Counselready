"""WebAuthn registration and authentication.

Two things worth stating plainly, because they shape what this can and cannot promise:

* **The biometric is not sent to us.** Face ID unlocks a private key held in the
  device's secure enclave; we receive a signature. We never see, store, or transmit
  biometric data, which is also why this adds no biometric-privacy obligations.
* **A passkey is only as private as the device it sits on.** If another person's face
  or fingerprint is enrolled on that phone — routine among partners, and often
  forgotten years later — they can use the passkey. The product surfaces this at
  enrolment rather than assuming the device is the user's alone (CLAUDE.md §3).

Challenges are held server-side and consumed once. A challenge accepted twice would let
a captured registration or assertion be replayed.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

CHALLENGE_BYTES = 32


class PasskeyVerificationError(Exception):
    """The browser's response did not verify."""


@dataclass(frozen=True)
class RelyingParty:
    """Identifies us to the authenticator.

    `rp_id` must be the site's registered domain and `origin` the exact origin the
    browser saw. This binding is what makes a passkey phishing-resistant: a credential
    created for one origin cannot be used on another.
    """

    rp_id: str
    name: str
    origin: str


@dataclass(frozen=True)
class RegisteredPasskey:
    credential_id: bytes
    public_key: bytes
    sign_count: int
    backed_up: bool


def new_challenge() -> bytes:
    return secrets.token_bytes(CHALLENGE_BYTES)


def encode_challenge(challenge: bytes) -> str:
    """Base64url for storing in a session record."""
    return base64.urlsafe_b64encode(challenge).decode().rstrip("=")


def decode_challenge(encoded: str) -> bytes:
    return base64url_to_bytes(encoded)


def registration_options(
    *,
    party: RelyingParty,
    user_id: bytes,
    user_name: str,
    display_name: str | None,
    challenge: bytes,
    existing_credentials: list[bytes],
) -> str:
    """Options for `navigator.credentials.create`, as JSON.

    `user_verification=REQUIRED` is what makes this a *second* factor rather than mere
    possession: the authenticator must confirm the human — Face ID, fingerprint, or a
    device PIN — not merely that the device is present.
    """
    options = generate_registration_options(
        rp_id=party.rp_id,
        rp_name=party.name,
        user_id=user_id,
        user_name=user_name,
        user_display_name=display_name or user_name,
        challenge=challenge,
        # Excluding known credentials stops a user silently registering the same
        # authenticator twice and thinking they have two backups when they have one.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=credential_id)
            for credential_id in existing_credentials
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return options_to_json(options)


def verify_registration(
    *, party: RelyingParty, credential_json: str, challenge: bytes
) -> RegisteredPasskey:
    try:
        verified = verify_registration_response(
            credential=credential_json,
            expected_challenge=challenge,
            expected_rp_id=party.rp_id,
            expected_origin=party.origin,
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError) as exc:
        raise PasskeyVerificationError(str(exc)) from exc

    return RegisteredPasskey(
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        backed_up=bool(verified.credential_backed_up),
    )


def authentication_options(
    *, party: RelyingParty, challenge: bytes, allowed_credentials: list[bytes]
) -> str:
    """Options for `navigator.credentials.get`, as JSON."""
    options = generate_authentication_options(
        rp_id=party.rp_id,
        challenge=challenge,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=credential_id) for credential_id in allowed_credentials
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options_to_json(options)


def verify_authentication(
    *,
    party: RelyingParty,
    credential_json: str,
    challenge: bytes,
    public_key: bytes,
    stored_sign_count: int,
) -> int:
    """Verify an assertion and return the new signature counter.

    The counter check is delegated to the library, which treats a stored zero as "this
    authenticator does not count" rather than as a clone signal — synced passkeys
    commonly report zero, and failing them would break the most common setup.
    """
    try:
        verified = verify_authentication_response(
            credential=credential_json,
            expected_challenge=challenge,
            expected_rp_id=party.rp_id,
            expected_origin=party.origin,
            credential_public_key=public_key,
            credential_current_sign_count=stored_sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError) as exc:
        raise PasskeyVerificationError(str(exc)) from exc

    return int(verified.new_sign_count)
