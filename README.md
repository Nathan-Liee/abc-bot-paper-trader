# ABC Bot Paper Trader

Paper-data-only validation collector for the ABC Bot stack.

This repository is the dedicated **paper-trading / validation collector**
for the ABC Bot project. It contains no trading logic, no AI, no risk
engine, no execution engine, and no live broker integration. It is kept
**separate from any future ABC Bot engine repository**.

## Scope

| What this repo does                          | What this repo NEVER does           |
| -------------------------------------------- | ----------------------------------- |
| Paper-trading validation infrastructure      | Live trading (forbidden)            |
| Safety defaults and config foundation        | Demo/live order submission          |
| Shared canonical event contract              | Connect to HFM / MT5 trading account|
| MQL5 read-only telemetry bridge              | AI, risk, exposure, lot sizing      |
| SQLite WAL storage + analytics exports       | Placeholder business logic          |
| Run tests / lint / type-check in CI          | Live trading capability             |

The collector chain (bridge → JSONL → ingestion → persistence) is
implemented; reconciliation and data collection are later milestones.

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
|-- mql5-bridge/    MQL5 read-only telemetry bridge (source + architecture notes)
|-- collector/      Python collector: event model, persistence, adapters
|-- shared/         Canonical event contract + JSON schema
|-- tests/          unit / integration / replay / failure
|-- scripts/        Operational helper scripts
|-- config/         Configuration templates
|-- docs/           Documentation (architecture, contracts, agent context)
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

Live trading is prohibited on this repository, including in future commits.

Current implementation state and task are tracked in `AGENTS.md` (agent
context) and `docs/architecture.md` (system architecture). Remaining
milestones are tracked in `docs/README.md`.

## Authoritative documentation

- `AGENTS.md` — permanent context for coding agents (current task, boundaries)
- `docs/architecture.md` — system architecture and boundaries
- `docs/contracts/canonical-event-contract.md` — canonical event contract
- `docs/contracts/canonical-event-contract-validation.md` — validation rules
- `shared/schemas/canonical-event.schema.json` — machine-checkable contract