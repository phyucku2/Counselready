# ADR-0007 — Authentication

**Date:** 2026-07-28
**Status:** Accepted
**Owner decision:** no (engineering choices, recorded for override)

## Problem

Every route that touches a case file needs a gate, and ADR-0006 stopped short of an
upload endpoint precisely because there wasn't one. Beyond the ordinary requirement,
this product has a specific threat that shapes the design: the person most motivated to
get into a user's account is often the opposing party in their case, who knows their
email address, their pets' names, and their children's birthdays. CLAUDE.md §3 treats
account takeover here as a life-safety issue rather than a security inconvenience.

## Decision

### Passwords: Argon2id, with the parameters stated explicitly

OWASP's second recommended configuration (19 MiB, 2 iterations, parallelism 1), written
out rather than inherited from library defaults so a dependency bump cannot silently
weaken them. A test asserts the stored hash begins with `$argon2id$`, so a change of
algorithm fails in CI rather than in production. Successful logins re-hash when the
parameters have moved on.

### Login does not disclose whether an account exists

An unknown email runs the verification against a dummy hash, so the missing-account path
costs the same as a real one. Wrong password, unknown email, and deactivated account all
return an identical 401 body.

This is not box-ticking. A chatty login endpoint lets someone confirm that their former
spouse has an account here — which, for a product that holds a case file about that
person, is itself harmful information. A test asserts the two responses are
byte-identical, and another asserts the timing difference stays within an order of
magnitude.

Registration is the deliberate exception: it must tell a user their address is already
taken, or a real person who forgot they signed up cannot get in. The mitigation there is
rate limiting, not a fiction.

### Two token types, two threat models

**Access tokens** are short-lived (15 min) signed JWTs, never stored server-side. The
algorithm list is pinned on decode, which is what refuses an `alg: none` forgery — there
is a test for exactly that.

**Refresh tokens** are 256-bit opaque random strings, stored only as a SHA-256 digest. A
database disclosure yields no usable session, proven by a test that scans the stored rows
for the issued token.

The digest is SHA-256 rather than Argon2 on purpose: Argon2 is slow to make *guessing* a
low-entropy human password expensive. A 256-bit random token cannot be guessed, so the
slowness would buy nothing and put a deliberate CPU cost on every refresh.

### Refresh rotation with replay detection

Each refresh rotates the token and records the old digest as used. Presenting an
already-rotated token **revokes the whole session**. That is a stolen token being
replayed, and since we cannot tell the thief from the legitimate holder, ending the
session for both is the only safe response.

### Logout takes effect immediately

`current_user` re-checks that the session behind the token is still live on every
request. Without that, logout would be cosmetic until the access token lapsed — up to
fifteen minutes during which a stolen token still works. `POST /auth/logout-all` ends
every session at once, because "someone else may be in my account" needs a single action
that works now, and shipping it in a later hardening pass would leave the highest-risk
users without it.

### Rate limiting is per identity

Ten failures in fifteen minutes, counted from the `auth_event` audit trail. The limit
holds even when the correct password is then supplied, so guessing cannot be confirmed by
a lucky attempt inside a throttled window. A test proves throttling one account does not
deny service to another, since a per-IP-only limiter would let one targeted user lock out
everyone behind a shared address.

### The signing key must be strong, and its absence is fatal where it matters

`JWT_SECRET` under 32 characters stops the boot (RFC 7518 §3.2 — an HMAC key shorter than
the hash output weakens HS256). PyJWT only warns about this; a signing key is not a place
to accept a warning.

Absent entirely, the app mints an ephemeral key for single-process local development, and
refuses to start in staging or production, or under more than one worker. The
multi-worker case matters: each worker would mint a different key, so a token signed by
one is rejected by the next — an intermittent, baffling logout rather than an honest
failure.

## Not in this portion

**MFA.** It is a launch requirement, not optional, for the reason in the opening
paragraph — but it is its own portion (roadmap 0.3b) with enrolment, recovery codes, and
a lost-device path to design. Shipping it half-built would be worse than shipping it next.

**Password reset.** Needs an email-sending seam, which under ADR-0002 must be an
egress seam that ships off by default and inside the Azure tenant.

**Login alerting.** The `auth_event` trail now records what a "new sign-in to your
account" notification would need; the notification itself rides with the email seam.

## Consequences

- The upload route unblocked by this can now be built (ADR-0006's deferral).
- Every case-data route depends on `current_user`, so forgetting the gate requires
  actively omitting a dependency rather than merely failing to add a check.
- The `auth_event` table holds email addresses and outcomes, no case material and no
  credentials.
- Sessions accumulate rows; expired sessions and their used-token records need a pruning
  job. Deferred with the queue decision (ADR-0006), not forgotten.

## A measurement bug this portion uncovered

Coverage was reporting **57%** for `app/auth/service.py` when the real figure was **95%**.
SQLAlchemy's asyncio bridge executes ORM work inside greenlets, and coverage.py does not
trace those without `concurrency = ["thread", "greenlet"]`. Every async database path in
the project had been under-reported, so the 85% gate had been measuring less than it
claimed. Fixed in `pyproject.toml`; project coverage is now honestly 97%.

## Dependencies added

- `argon2-cffi` 25.1.0 — MIT
- `PyJWT` 2.13.0 — MIT
- `pydantic[email]` (email-validator) — for `EmailStr`

All permissive, passing CLAUDE.md §6.

## Verification

136 tests green: 96 unit, 40 integration against live PostgreSQL 16, driven through the
real ASGI app. `mypy --strict` clean, 97% coverage. All four migrations round-trip.
