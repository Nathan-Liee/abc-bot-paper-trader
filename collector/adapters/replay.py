"""Deterministic replay of a raw bridge source into a fresh SQLite DB.

Replay grounds the adapter's correctness: given a committed synthetic
fixture, we drive the exact production code path (reader -> normalize ->
validate -> persist) and assert deterministic counts. This is used by
tests and by the manual verification workflow, and intentionally does
not depend on wall-clock timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from collector.adapters.pipeline import IngestionPipeline, IngestionStats
from collector.adapters.reader import JsonlFileReader
from collector.persistence import PersistenceRepository
from collector.persistence.cursor import IngestionCursor


@dataclass(frozen=True)
class ReplayResult:
    """Deterministic outcome of replaying a source file."""

    stats: IngestionStats
    persisted_event_types: tuple[str, ...]
    persisted_count: int
    duplicate_count: int
    final_cursor: IngestionCursor | None


def replay_source(source_path: Path, db_path: Path, *, max_cycles: int = 100) -> ReplayResult:
    """Replay *source_path* from offset zero into a fresh *db_path*.

    The database is created fresh (any existing file is removed first);
    migrations run through ``PersistenceRepository``. ``max_cycles``
    guards against runaway loops (each cycle re-polls until EOF).
    """
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with PersistenceRepository(db_path) as repo:
        pipeline = IngestionPipeline(repo, JsonlFileReader(source_path, start_offset=0))
        stats = pipeline.stats()
        cycles = 0
        while cycles < max_cycles:
            stats = pipeline.process_once()
            cycles += 1
            if not stats.lines_read or not pipeline.reader.holds_partial:
                break
        return _result(repo, pipeline, stats)


def _result(
    repo: PersistenceRepository, pipeline: IngestionPipeline, stats: IngestionStats
) -> ReplayResult:
    events = list(repo.query_events(limit=10_000))
    return ReplayResult(
        stats=stats,
        persisted_event_types=tuple(e.event_type for e in events),
        persisted_count=len(events),
        duplicate_count=0,
        final_cursor=pipeline.cursor,
    )


__all__ = ["ReplayResult", "replay_source"]
