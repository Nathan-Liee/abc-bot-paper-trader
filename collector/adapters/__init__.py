"""Data source adapters: JSONL ingestion from the read-only MQL5 bridge.

Public surface:

* :class:`JsonlFileReader` - incremental append-only tail reader with
  byte-accurate cursor accounting
* :class:`IngestionPipeline` - READ -> NORMALIZE -> VALIDATE -> PERSIST
* :class:`IngestionRunner` - bounded poll loop with graceful shutdown
* ``normalize`` / ``errors`` - classification and error taxonomy
"""

from collector.adapters.errors import (
    IngestionError,
    InvalidLineError,
    PersistenceIngestionError,
    TransientIngestionError,
)
from collector.adapters.normalize import (
    BRIDGE_SOURCE,
    NormalizedBridgeLine,
    RawLineKind,
    normalize_bridge_line,
    parse_raw_line,
)
from collector.adapters.pipeline import IngestionPipeline, IngestionStats
from collector.adapters.reader import JsonlFileReader, PollResult, RawLine
from collector.adapters.replay import ReplayResult, replay_source
from collector.adapters.runner import IngestionRunner

__all__ = [
    "BRIDGE_SOURCE",
    "IngestionError",
    "IngestionPipeline",
    "IngestionRunner",
    "IngestionStats",
    "InvalidLineError",
    "JsonlFileReader",
    "NormalizedBridgeLine",
    "PersistenceIngestionError",
    "PollResult",
    "RawLine",
    "RawLineKind",
    "ReplayResult",
    "TransientIngestionError",
    "normalize_bridge_line",
    "parse_raw_line",
    "replay_source",
]
