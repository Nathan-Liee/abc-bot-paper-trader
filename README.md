# ABC Bot Paper Trader

Paper-data-only validation collector for the ABC Bot stack.

This repository is a **bootstrap foundation only**. It contains no trading
logic, no AI, no risk engine, no execution engine, and no broker integration.
It is the dedicated **paper-trading / validation collector** and it is kept
**separate from any future ABC Bot engine repository**.

## Scope

| What this repo does                          | What this repo NEVER does           |
| -------------------------------------------- | ----------------------------------- |
| Reserve the collector architecture           | Live trading (forbidden)            |
| Define safety defaults and config foundation | Demo/live order submission          |
| Define the shared event contract shape       | Connect to HFM / MT5 / demo account |
| Define storage (SQLite WAL) layout           | AI, risk, exposure, lot sizing      |
| Run tests / lint / type-check in CI          | Placeholder business logic          |

At this stage every module is a **placeholder boundary** with no implementation.

## Architecture (baseline, fixed)

```text
HFM Demo MT5
     |
     v
MQL5 Bridge
     |
     v
Local IPC / JSONL
     |
     v
Python Collector
     |
     v
SQLite WAL
     |
     v
CSV / JSONL Analytics
```

This architecture is fixed and will not be changed.

## Safety boundaries

Hard-coded in `collector/settings.py` and never read from the environment:

- `live_trading_enabled = False`
- `read_only_mode = True`
- `demo_execution_allowed = False`
- default mode = `PAPER_DATA_ONLY`

Any attempt to enable a safety flag (e.g. via `ABC_BOT_*` environment
variables that request live/demo execution) is **refused with an error**.
Live-trading capability does not exist anywhere in this repository.

## Repository layout

```text
abc-bot-paper-trader/
|-- mql5-bridge/    MQL5 bridge placeholder (source folder, architecture notes)
|-- collector/      Python collector module boundaries (placeholder)
|-- shared/         Canonical event contract + JSON schema placeholders
|-- tests/          unit / integration / replay / failure
|-- scripts/        Operational helper scripts (planned)
|-- config/         Configuration templates
|-- docs/           Documentation foundation
|-- data/           Runtime storage (ignored by git, .gitkeep only)
|-- .github/        CI workflows (test, lint, type-check)
+-- pyproject.toml  Python project definition (uv-managed)
```

## Development setup

Prerequisites: Python >= 3.11 and [uv](https://docs.astral.sh/uv/).

```powershell
uv python pin 3.11        # optional; .python-version is already set
uv sync                   # create .venv, install dev/test deps
uv run pytest             # run the test suite
uv run ruff check .       # lint
uv run ruff format --check .  # format check
uv run mypy collector shared   # type-check
```

No MT5, no HFM, and no broker credentials are required to set up, test, or
run this repository.

## Configuration

- `config/settings.template.yaml` — configuration template; copy to
  `config/settings.local.yaml` and do not commit local overrides.
- `.env.example` — environment variable template; copy to `.env` for local
  non-execution overrides (paths, log level, env name only).

## Status

Bootstrap only. Live trading is prohibited on this repository, including in
future commits. Remaining implementation steps are tracked in
`docs/README.md`.