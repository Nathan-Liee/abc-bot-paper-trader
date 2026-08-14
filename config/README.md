# Configuration foundation

This directory holds configuration **templates only**. Local overrides
are never committed (see `.gitignore`).

## Files

- `settings.template.yaml` — YAML configuration template. Copy to
  `config/settings.local.yaml` and edit.
- `.env.example` (repository root) — environment variable template. Copy
  to `.env` and edit.

## Rules

- Only **non-execution** values are configurable: environment name
  (`development` / `test` / `production`), storage paths, log level.
- Safety flags are hard-coded in `collector/settings.py` and are **not**
  configurable here:
  - `live_trading_enabled: false` (always)
  - `read_only_mode: true` (always)
  - `demo_execution_allowed: false` (always)
  - mode: `PAPER_DATA_ONLY` (always)
- Never add broker / account / API credentials to any file in this
  repository. There are no credentials to configure at bootstrap time.