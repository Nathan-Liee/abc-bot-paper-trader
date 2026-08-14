"""Error taxonomy for the JSONL ingestion adapter.

Three classes, mirroring the task classification:

* :class:`TransientIngestionError` - the input may succeed on retry
  (file temporarily unavailable, incomplete line). The cursor is never
  advanced and the runner retries with a bounded poll interval.
* :class:`InvalidLineError` - the line is permanently unusable
  (malformed JSON, malformed envelope, unknown type, contract or schema
  violation, missing trade identity). The line is skipped, counted, and
  the cursor advances past it so the stream cannot be blocked forever.
* :class:`PersistenceIngestionError` - the canonical event could not be
  committed (wraps ``PersistenceError``). The cursor is never advanced;
  the runner retries with bounded backoff and event idempotency absorbs
  any duplicate commit.
"""

from __future__ import annotations

from collector.persistence.errors import PersistenceError


class IngestionError(Exception):
    """Base class for all ingestion adapter errors."""


class TransientIngestionError(IngestionError):
    """Retryable input condition; the cursor must not advance."""


class InvalidLineError(IngestionError):
    """Permanent line-level problem; the line must be skipped safely."""


class PersistenceIngestionError(IngestionError):
    """Persistence failure while committing a line; the cursor must not advance."""

    def __init__(self, message: str, *, cause: PersistenceError | None = None) -> None:
        super().__init__(message)
        self.cause = cause


__all__ = [
    "IngestionError",
    "InvalidLineError",
    "PersistenceIngestionError",
    "TransientIngestionError",
]
