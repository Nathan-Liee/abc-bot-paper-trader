"""Verify that every placeholder module boundary is importable.

Validates the import structure of the bootstrap foundation without
requiring any connection to MT5 / HFM / a demo account.
"""

from __future__ import annotations

import importlib
import json

from collector.settings import PROJECT_ROOT

MODULES = (
    "collector",
    "collector.settings",
    "collector.adapters",
    "collector.event_model",
    "collector.journal",
    "collector.persistence",
    "collector.observability",
    "collector.modes",
    "collector.config",
    "collector.reconciliation",
    "collector.reconciliation.broker",
    "collector.reconciliation.classifier",
    "collector.reconciliation.mock",
    "collector.reconciliation.reconciler",
    "collector.reconciliation.runner",
    "collector.reconciliation.types",
    "shared",
    "shared.contracts",
    "shared.constants",
)


def test_all_placeholder_modules_import() -> None:
    for name in MODULES:
        importlib.import_module(name)


def test_event_schema_placeholder_is_valid_json() -> None:
    schema_path = PROJECT_ROOT / "shared" / "schemas" / "event.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert schema["title"] == "canonical-event"


def test_storage_layout_is_committed() -> None:
    expected = (
        "data/sqlite",
        "data/events",
        "data/analytics",
        "tests/unit",
        "tests/integration",
        "tests/replay",
        "tests/failure",
    )
    for relative in expected:
        assert (PROJECT_ROOT / relative).is_dir(), f"missing {relative}"
