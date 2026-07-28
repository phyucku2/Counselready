"""Object storage seam.

Documents live in blob storage, never in the database (ADR-0002). This protocol is
the boundary: the Azure implementation needs a subscription and credentials, which are
owner-side, so the service depends on the protocol and the tests supply a local
implementation.

Keys are content-addressed. Storing the same bytes twice is idempotent, which is what
lets the ingest service write the blob before the database row without risking a
duplicate object.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


class ObjectNotFoundError(KeyError):
    """Raised when a key has no stored object."""


class ObjectStore(Protocol):
    """Minimal blob interface. Deliberately small — anything richer belongs to the
    concrete backend, not to the seam every caller depends on."""

    async def put(self, key: str, data: bytes) -> None:
        """Store `data` at `key`. Idempotent for identical content."""
        ...

    async def get(self, key: str) -> bytes:
        """Return the object at `key`, or raise `ObjectNotFoundError`."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the object at `key`. Deleting a missing key is not an error."""
        ...


def content_hash(data: bytes) -> str:
    """SHA-256 of the document bytes, used for both deduplication and the storage key."""
    return hashlib.sha256(data).hexdigest()


def storage_key(case_id: str, digest: str) -> str:
    """Content-addressed key, namespaced per case.

    Namespacing by case keeps one case's objects separable — it makes a per-case
    deletion a prefix operation rather than a scan, which matters when a user asks for
    their case to be destroyed (CLAUDE.md §3).
    """
    return f"cases/{case_id}/documents/{digest}"
