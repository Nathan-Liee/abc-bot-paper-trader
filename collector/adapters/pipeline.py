"""Ingestion pipeline: READ -> NORMALIZE -> VALIDATE -> PERSIST.

Per complete line the pipeline:

1. parses the raw JSON line (malformed -> counted, skipped, cursor
   advances)
2. classifies: bridge-internal telemetry (counted, skipped), unknown
   event type (counted, skipped), canonical event type (proceed)
3. for canonical types outside the out-of-band set, the line lacks the
   orchestrator-provided trade identity that canonical events require;
   it is counted as *identity pending* and preserved raw for later
   reconciliation (no fabricated ids)
4. for canonical out-of-band events: normalize payload, build the
   canonical envelope, validate against the JSON Schema contract, then
   persist event + cursor in ONE transaction (idempotent insert)

Cursor discipline: the cursor advances only after a line is fully
handled. Persistence failures raise PersistenceIngestionError and never
advance the cursor (the runner retries; idempotency absorbs duplicates).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from jsonschema import Draft202012Validator, ValidationError

from collector.adapters.errors import InvalidLineError, PersistenceIngestionError
from collector.adapters.normalize import (
    NormalizedBridgeLine,
    RawLineKind,
    normalize_bridge_line,
    parse_raw_line,
)
from collector.adapters.reader import JsonlFileReader, RawLine
from collector.event_model import (
    ContractValidationError,
    EventEnvelope,
    build_event,
    monotonic_ms,
    now_utc_ms,
)
from collector.persistence import PersistenceError, PersistenceRepository
from collector.persistence.cursor import IngestionCursor
from collector.settings import PROJECT_ROOT
from shared.contracts.lifecycle import OUT_OF_BAND_EVENTS

logger = logging.getLogger("collector.ingestion")

SCHEMA_PATH = PROJECT_ROOT / "shared" / "schemas" / "canonical-event.schema.json"


@dataclass(frozen=True)
class IngestionStats:
    """Observability counters for one pipeline run (task section 17)."""

    lines_read: int = 0
    events_parsed: int = 0
    events_valid: int = 0
    events_persisted: int = 0
    events_invalid: int = 0
    events_identity_pending: int = 0
    internal_event_count: int = 0
    unknown_event_count: int = 0
    malformed_line_count: int = 0
    parse_errors: int = 0
    persistence_errors: int = 0
    cursor_offset: int = 0
    last_event_timestamp: str | None = None
    ingestion_lag_ms: int | None = None
    current_source_file: str = ""
    rotations_seen: int = 0


@dataclass
class _MutableCounters:
    lines_read: int = 0
    events_parsed: int = 0
    events_valid: int = 0
    events_persisted: int = 0
    events_invalid: int = 0
    events_identity_pending: int = 0
    internal_event_count: int = 0
    unknown_event_count: int = 0
    malformed_line_count: int = 0
    parse_errors: int = 0
    persistence_errors: int = 0
    rotations_seen: int = 0
    last_event_timestamp: str | None = None
    last_read_monotonic: int | None = None


class IngestionPipeline:
    """Pipeline for one source file, driven by poll cycles."""

    def __init__(self, repo: PersistenceRepository, reader: JsonlFileReader) -> None:
        self._repo = repo
        self._reader = reader
        self._counters = _MutableCounters()
        self._line_number = 0
        self._cursor: IngestionCursor | None = None
        self._validator: Draft202012Validator | None = None

    @property
    def cursor(self) -> IngestionCursor | None:
        return self._cursor

    @property
    def reader(self) -> JsonlFileReader:
        return self._reader

    # ------------------------------------------------------------------
    # Poll cycle
    # ------------------------------------------------------------------

    def process_once(self) -> IngestionStats:
        """Run one poll cycle and return fresh stats.

        Raises :class:`PersistenceIngestionError` when a persistence
        failure occurred (cursor unchanged; the runner should retry).
        """
        poll = self._reader.poll()
        c = self._counters

        if poll.rotation:
            c.rotations_seen += 1
            logger.warning(
                "ingestion: source rotation detected; cursor reset for %s", self._reader.path
            )
            self._persist_cursor(IngestionCursor.of(str(self._reader.path), 0))

        if poll.unavailable:
            logger.debug("ingestion: source unavailable for %s", self._reader.path)
            return self.stats()

        for line in poll.lines:
            self._process_line(line)

        return self.stats()

    # ------------------------------------------------------------------
    # Per-line processing
    # ------------------------------------------------------------------

    def _process_line(self, line: RawLine) -> None:
        c = self._counters
        c.lines_read += 1
        self._line_number += 1
        c.last_read_monotonic = monotonic_ms()

        text = line.to_text()
        if not text.strip():
            self._advance(line)
            return

        try:
            parsed = parse_raw_line(text)
            normalized = normalize_bridge_line(parsed, ts_collected=now_utc_ms())
        except InvalidLineError as exc:
            c.parse_errors += 1
            c.events_invalid += 1
            c.malformed_line_count += 1
            logger.warning("ingestion: %s at offset %d", exc, line.start_offset)
            self._advance(line)
            return
        c.events_parsed += 1

        if normalized.kind is RawLineKind.INTERNAL:
            c.internal_event_count += 1
            logger.info(
                "ingestion: internal bridge event at offset %d (%s); not canonicalized",
                line.start_offset,
                normalized.code,
            )
            self._advance(line)
            return

        if normalized.kind is RawLineKind.UNKNOWN:
            c.events_invalid += 1
            c.unknown_event_count += 1
            logger.warning(
                "ingestion: unknown event type at offset %d; raw line preserved in source file",
                line.start_offset,
            )
            self._advance(line)
            return

        assert normalized.event_type is not None and normalized.payload is not None

        if normalized.event_type not in OUT_OF_BAND_EVENTS:
            # Trade-path events need orchestrator-owned identity context
            # (trade_id/trigger linkage) that the read-only bridge does
            # not carry. No ids are fabricated; the raw line stays in the
            # source file for later reconciliation.
            c.events_invalid += 1
            c.events_identity_pending += 1
            logger.info(
                "ingestion: %s at offset %d lacks trade identity; preserved raw for reconciliation",
                normalized.event_type.value,
                line.start_offset,
            )
            self._advance(line)
            return

        envelope = self._build_envelope(normalized, ts_collected=now_utc_ms())
        if envelope is None:
            c.events_invalid += 1
            logger.warning(
                "ingestion: contract/schema violation for %s at offset %d; line skipped",
                normalized.event_type.value,
                line.start_offset,
            )
            self._advance(line)
            return

        c.events_valid += 1
        c.last_event_timestamp = envelope.ts_event
        cursor = self._cursor_for(line, last_event_id=envelope.event_id)
        try:
            self._repo.insert_event_with_cursor(envelope, cursor)
        except PersistenceError as exc:
            c.persistence_errors += 1
            raise PersistenceIngestionError(
                f"persistence failed for line at offset {line.start_offset}: {exc}", cause=exc
            ) from exc
        self._cursor = cursor
        c.events_persisted += 1

    def _build_envelope(
        self, normalized: NormalizedBridgeLine, *, ts_collected: str
    ) -> EventEnvelope | None:
        """Build and validate a canonical envelope; None on rejection."""
        assert normalized.event_type is not None and normalized.payload is not None
        try:
            event = build_event(
                normalized.event_type,
                normalized.payload,
                ts_event=normalized.ts_event if normalized.ts_event else None,
                ts_collected=ts_collected,
                ts_monotonic=monotonic_ms(),
            )
            self._validator_for().validate(event.to_dict())
            return event
        except (ContractValidationError, ValidationError) as exc:
            logger.debug("ingestion: envelope rejected: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Cursor discipline
    # ------------------------------------------------------------------

    def _cursor_for(self, line: RawLine, *, last_event_id: str | None) -> IngestionCursor:
        previous_id = last_event_id
        if previous_id is None and self._cursor is not None:
            previous_id = self._cursor.last_event_id
        # Advance past the line content AND its trailing newline so the
        # persisted offset equals the reader's resume point (next line
        # start), not a position mid-line.
        return IngestionCursor.of(
            source_path=str(self._reader.path),
            byte_offset=line.end_offset + 1,
            line_number=self._line_number,
            last_event_id=previous_id,
        )

    def _advance(self, line: RawLine) -> None:
        """Advance past a handled line without an event (progress-only)."""
        cursor = self._cursor_for(line, last_event_id=None)
        self._persist_cursor(cursor)

    def _persist_cursor(self, cursor: IngestionCursor) -> None:
        try:
            self._repo.save_ingestion_cursor(cursor)
        except PersistenceError as exc:
            raise PersistenceIngestionError(
                f"cursor persistence failed for {cursor.source_path}: {exc}", cause=exc
            ) from exc
        self._cursor = cursor

    def _validator_for(self) -> Draft202012Validator:
        if self._validator is None:
            with SCHEMA_PATH.open(encoding="utf-8") as fh:
                self._validator = Draft202012Validator(json.load(fh))
        return self._validator

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> IngestionStats:
        c = self._counters
        lag = None
        if c.last_read_monotonic is not None:
            lag = max(0, monotonic_ms() - c.last_read_monotonic)
        return IngestionStats(
            lines_read=c.lines_read,
            events_parsed=c.events_parsed,
            events_valid=c.events_valid,
            events_persisted=c.events_persisted,
            events_invalid=c.events_invalid,
            events_identity_pending=c.events_identity_pending,
            internal_event_count=c.internal_event_count,
            unknown_event_count=c.unknown_event_count,
            malformed_line_count=c.malformed_line_count,
            parse_errors=c.parse_errors,
            persistence_errors=c.persistence_errors,
            cursor_offset=self._cursor.byte_offset if self._cursor else 0,
            last_event_timestamp=c.last_event_timestamp,
            ingestion_lag_ms=lag,
            current_source_file=str(self._reader.path),
            rotations_seen=c.rotations_seen,
        )


__all__ = ["IngestionPipeline", "IngestionStats", "SCHEMA_PATH"]
