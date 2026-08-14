"""Streaming ingestion runner.

Owns the repository lifecycle and drives the pipeline on a bounded poll
interval (never a busy loop). Graceful shutdown is cooperative: the
caller supplies a ``stop_check`` (e.g. ``threading.Event.is_set``) and
the runner exits between polls.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from collector.adapters.errors import IngestionError, PersistenceIngestionError
from collector.adapters.pipeline import IngestionPipeline, IngestionStats
from collector.adapters.reader import JsonlFileReader
from collector.persistence import PersistenceRepository

logger = logging.getLogger("collector.ingestion.runner")


class IngestionRunner:
    """Bounded-poll ingestion runner for one JSONL source file."""

    def __init__(
        self, repo: PersistenceRepository, source_path: Path, *, poll_seconds: float = 1.0
    ) -> None:
        self._repo = repo
        self._source_path = source_path
        self._poll_seconds = max(poll_seconds, 0.05)
        self._pipeline: IngestionPipeline | None = None

    @property
    def pipeline(self) -> IngestionPipeline | None:
        return self._pipeline

    def start(self) -> IngestionPipeline:
        """Open the repository and resume the cursor, then return the pipeline."""
        self._repo.open()
        cursor = self._repo.get_ingestion_cursor(str(self._source_path))
        start_offset = 0 if cursor is None else cursor.byte_offset
        self._pipeline = IngestionPipeline(
            self._repo,
            JsonlFileReader(self._source_path, start_offset=start_offset),
        )
        logger.info("ingestion: resuming %s at byte offset %d", self._source_path, start_offset)
        return self._pipeline

    def process_once(self) -> IngestionStats:
        if self._pipeline is None:
            raise RuntimeError("runner not started; call start() first")
        return self._pipeline.process_once()

    def run(self, stop_check: Callable[[], bool] | None = None) -> IngestionStats:
        """Poll until *stop_check* returns True (or forever when None)."""
        pipeline = self._pipeline if self._pipeline is not None else self.start()
        stats = pipeline.stats()
        while True:
            if stop_check is not None and stop_check():
                break
            try:
                stats = pipeline.process_once()
            except PersistenceIngestionError:
                logger.exception("ingestion: persistence failure; cursor preserved; retrying")
                stats = pipeline.stats()
            except (IngestionError, OSError):
                logger.exception("ingestion: transient failure; retrying")
            time.sleep(self._poll_seconds)
        return stats

    def close(self) -> None:
        self._repo.close()


__all__ = ["IngestionRunner"]
