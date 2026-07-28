"""Filesystem-backed object store for local development and tests.

Not for production: no encryption at rest, no access control, no durability guarantees.
The Azure Blob implementation lands when the owner provisions a subscription
(ADR-0002); this exists so the ingest pipeline is fully testable before then.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.storage.base import ObjectNotFoundError


class LocalObjectStore:
    """Stores objects as files under a root directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        # Keys are built by `storage_key` from a UUID and a hex digest, never from
        # user input, but resolve and check anyway: a traversal here would write
        # outside the store, and the cost of being sure is one comparison.
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"key escapes the store root: {key!r}")
        return candidate

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, True)
