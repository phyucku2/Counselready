# ADR-0008 — Multi-factor authentication

**Date:** 2026-07-28
**Status:** Accepted
**Owner decision:** no (engineering choices); the *requirement* is CLAUDE.md §3

## Problem

ADR-0007 shipped passwords and sessions but left the launch-blocking gap: a password
alone still opened the account. For this product the attacker with the best shot at
guessing or knowing a password is frequently the opposing party — someone who has lived
with the user, knows their pets' names and children's birthdays, and may have had access
to their devices. A second factor is what makes the first one survivable.

## Decision

### TOTP, and no vendor

RFC 6238 time-based codes, verified locally against a shared secret. The user's existing
authenticator app is the entire second factor.

**SMS was rejected**, not merely skipped. It is the weakest common second factor because
of SIM-swap, and here it is worse than weak: a code sent to a phone on a shared family
plan can land with the exact person the factor exists to keep out. Email codes have the
same problem when the account was set up during a relationship.

The side benefit is architectural: no third party, no per-message cost, no egress. MFA
stays inside the Azure-only posture (ADR-0002) with nothing to sign or configure.

### The TOTP secret is encrypted at rest

Fernet, keyed by `MFA_ENCRYPTION_KEY`. Stored in plaintext, a database disclosure would
let an attacker generate valid codes indefinitely — the second factor would be
decorative precisely when it mattered. Serving in staging or production without the key
stops the boot; locally its absence makes enrolment return 503 rather than storing a
secret in the clear.

### Enrolment is two steps

Setup issues a secret and a provisioning URI; MFA activates only once the user produces
a working code. Activating on issue would lock out anyone whose QR scan silently failed
— with no second device and no support desk, that is an unrecoverable account.

Re-running setup on an *unconfirmed* enrolment is allowed, so a failed scan is
self-service. Re-running it on an *active* one is refused, since that would silently
rotate the secret out from under a working authenticator.

### A password alone yields a challenge, not a session

With MFA active, `POST /auth/login` returns a five-minute challenge token carrying no
authority. Tokens are issued only by `POST /auth/mfa/verify`. Both token types carry a
`typ` claim that is checked on decode, so a challenge cannot be presented to an
authenticated route and an access token cannot be exchanged as a challenge — tested in
both directions.

### Codes cannot be replayed inside their own window

The TOTP step of each accepted code is recorded, and a code from that step or earlier is
refused. Without this, a code glimpsed over a shoulder or read off a lock screen stays
usable for up to ninety seconds.

### Recovery codes are the lost-device path

Ten single-use codes, issued once at enrolment, stored as SHA-256 digests (high-entropy
random, so Argon2's slowness would buy nothing). Accepted with or without their
separators, because people retype them from paper. Disabling MFA destroys them, so an
old code cannot bypass a later re-enrolment.

### Disabling requires the password *and* a current code

Someone who walks up to an unlocked laptop must not be able to strip the second factor
off the account. This is the same reasoning that makes `logout-all` a first-release
feature rather than hardening.

## What this does not cover

**Rate limiting on code attempts.** The login rate limiter guards the password step, but
the verify step is currently unthrottled — a six-digit code with a ±1 step window is
brute-forceable given enough attempts against one challenge. The challenge's five-minute
lifetime bounds it, but not enough. **This is a known gap and should close before
launch**; it is recorded on the roadmap rather than left to be rediscovered.

**Trusted devices / "remember this browser".** Convenience feature, deliberately absent:
it is exactly the mechanism that would let a shared or previously-compromised device skip
the factor.

## Consequences

- Login now has two possible successful shapes. Clients must handle both, which is why
  the challenge response is explicitly labelled rather than distinguished by absence.
- `MFA_ENCRYPTION_KEY` joins `JWT_SECRET` as an owner-provisioned secret. Key rotation
  would require re-encrypting stored secrets — no rotation procedure exists yet.
- Enforcing MFA for *all* accounts (rather than offering it) is a product decision for
  the owner. The mechanism is now in place either way.

## Dependencies added

- `pyotp` 2.10.0 — MIT
- `cryptography` 49.0.0 — Apache-2.0 OR BSD-3-Clause

Both permissive. No QR-image library: the client renders the provisioning URI locally, so
the secret never passes through an image pipeline.

## Verification

159 tests green: 81 unit, 78 integration against live PostgreSQL 16 through the real ASGI
app. `mypy --strict` clean, 96% coverage. Encryption at rest and digest-only recovery
storage are both proven by scanning the actual stored rows.
