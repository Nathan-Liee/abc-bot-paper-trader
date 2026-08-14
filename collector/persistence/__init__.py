"""SQLite WAL persistence layer: immutable audit stream + derived state.

Public surface:

* :class:`PersistenceRepository` - the single write/query path
* ``InsertResult`` - idempotent append outcome
* ``apply_derived_state`` - pure event-to-derived-state projection
* ``run_integrity_checks`` / ``IntegrityReport`` - non-destructive checks
* ``export_events_*`` / ``export_trades_*`` / ``export_reconciliations_*`` -
  deterministic CSV/JSONL exports
* ``PersistenceError`` - every persistence failure raises this
"""

from collector.persistence.cursor import (
    IngestionCursor,
    read_ingestion_cursor,
    write_ingestion_cursor,
)
from collector.persistence.errors import PersistenceError
from collector.persistence.export import (
    export_events_csv,
    export_events_jsonl,
    export_reconciliations_csv,
    export_reconciliations_jsonl,
    export_trades_csv,
    export_trades_jsonl,
)
from collector.persistence.integrity import (
    ERROR,
    PASS,
    WARNING,
    IntegrityCheck,
    IntegrityReport,
    run_integrity_checks,
)
from collector.persistence.migrations import MIGRATIONS, Migration, apply_migrations
from collector.persistence.projector import apply_derived_state
from collector.persistence.records import (
    InvalidTradeRecord,
    OrderRecord,
    PositionRecord,
    ReconciliationRecord,
    TradeRecord,
)
from collector.persistence.repository import InsertResult, PersistenceRepository

__all__ = [
    "ERROR",
    "IngestionCursor",
    "InsertResult",
    "IntegrityCheck",
    "IntegrityReport",
    "InvalidTradeRecord",
    "MIGRATIONS",
    "Migration",
    "OrderRecord",
    "PASS",
    "PersistenceError",
    "PersistenceRepository",
    "PositionRecord",
    "ReconciliationRecord",
    "TradeRecord",
    "WARNING",
    "apply_derived_state",
    "apply_migrations",
    "export_events_csv",
    "export_events_jsonl",
    "export_reconciliations_csv",
    "export_reconciliations_jsonl",
    "export_trades_csv",
    "export_trades_jsonl",
    "read_ingestion_cursor",
    "run_integrity_checks",
    "write_ingestion_cursor",
]
