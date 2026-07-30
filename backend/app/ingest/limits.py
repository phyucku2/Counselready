"""Bounds on untrusted uploads.

The property that matters: the cap must fire *before* the body is materialized. A
check written after the whole stream has been read into memory is not a limit — the
resource exhaustion it was meant to prevent has already happened by the time it runs.

So this reads incrementally and stops the moment the running total exceeds the cap,
without consuming the rest of the stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

# 100 MiB. A long scanned custody evaluation is comfortably under this; anything above
# it is far more likely to be a mistake or an attack than a filing.
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class UploadTooLargeError(Exception):
    """The upload exceeded the byte cap."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"upload exceeds the {max_bytes} byte limit")
        self.max_bytes = max_bytes


class EmptyUploadError(Exception):
    """The upload contained no bytes."""


async def read_bounded(
    chunks: AsyncIterator[bytes],
    *,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    declared_length: int | None = None,
) -> bytes:
    """Read `chunks` into memory, refusing anything over `max_bytes`.

    `declared_length` (a Content-Length header, say) is used only as a cheap early
    rejection. It is never trusted as the actual size: a client can under-declare or
    omit it entirely, so the running total is what enforces the cap.
    """
    if declared_length is not None and declared_length > max_bytes:
        raise UploadTooLargeError(max_bytes)

    buffer = bytearray()
    async for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            # Abort without draining the rest of the stream. Peak memory is bounded
            # by max_bytes plus the one chunk that crossed the line.
            raise UploadTooLargeError(max_bytes)

    if not buffer:
        raise EmptyUploadError("upload contained no bytes")

    return bytes(buffer)
