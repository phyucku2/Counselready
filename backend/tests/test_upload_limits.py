"""Upload bounds.

The property under test is not "oversized uploads are rejected" but "oversized
uploads are rejected *before* being materialized". A limit that fires after the body
is in memory has already permitted the exhaustion it exists to prevent, and it passes
a naive test identically — so these assert on how much was consumed, not just on the
exception.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.ingest.limits import EmptyUploadError, UploadTooLargeError, read_bounded


class CountingStream:
    """Yields fixed-size chunks forever, recording how many bytes were pulled."""

    def __init__(self, chunk_size: int = 1024) -> None:
        self.chunk_size = chunk_size
        self.bytes_yielded = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            self.bytes_yielded += self.chunk_size
            yield b"x" * self.chunk_size


async def _chunks(*payloads: bytes) -> AsyncIterator[bytes]:
    for payload in payloads:
        yield payload


async def test_a_stream_over_the_cap_is_refused(no_declared_length: None) -> None:
    with pytest.raises(UploadTooLargeError):
        await read_bounded(_chunks(b"x" * 100), max_bytes=50)


async def test_the_stream_is_abandoned_rather_than_drained(no_declared_length: None) -> None:
    """The decisive check: an endless stream must stop being read almost immediately,
    not consumed to completion and measured afterwards."""
    stream = CountingStream(chunk_size=1024)
    with pytest.raises(UploadTooLargeError):
        await read_bounded(stream.__aiter__(), max_bytes=4096)

    # Bounded by the cap plus the single chunk that crossed it.
    assert stream.bytes_yielded <= 4096 + 1024


async def test_an_undeclared_length_does_not_bypass_the_cap(no_declared_length: None) -> None:
    """Content-Length is a client-supplied hint; the running total is the enforcement."""
    with pytest.raises(UploadTooLargeError):
        await read_bounded(_chunks(b"x" * 100), max_bytes=50, declared_length=None)


async def test_an_understated_length_does_not_bypass_the_cap(no_declared_length: None) -> None:
    """A client claiming 10 bytes and sending 100 must still be refused."""
    with pytest.raises(UploadTooLargeError):
        await read_bounded(_chunks(b"x" * 100), max_bytes=50, declared_length=10)


async def test_an_overstated_length_is_refused_without_reading_anything(
    no_declared_length: None,
) -> None:
    """An honest oversized declaration is refused up front — the cheapest rejection."""
    stream = CountingStream()
    with pytest.raises(UploadTooLargeError):
        await read_bounded(stream.__aiter__(), max_bytes=50, declared_length=10_000)
    assert stream.bytes_yielded == 0


async def test_an_upload_exactly_at_the_cap_is_accepted(no_declared_length: None) -> None:
    """The boundary is inclusive; an off-by-one here rejects legitimate documents."""
    assert await read_bounded(_chunks(b"x" * 50), max_bytes=50) == b"x" * 50


async def test_an_empty_upload_is_refused(no_declared_length: None) -> None:
    with pytest.raises(EmptyUploadError):
        await read_bounded(_chunks(), max_bytes=50)


async def test_an_upload_of_only_empty_chunks_is_refused(no_declared_length: None) -> None:
    with pytest.raises(EmptyUploadError):
        await read_bounded(_chunks(b"", b""), max_bytes=50)


async def test_chunks_are_reassembled_in_order(no_declared_length: None) -> None:
    assert await read_bounded(_chunks(b"abc", b"def", b"ghi"), max_bytes=50) == b"abcdefghi"


@pytest.fixture()
def no_declared_length() -> None:
    """Marker fixture; keeps each test's intent readable at the call site."""
    return None
