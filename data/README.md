# Storage foundation

Placeholder for runtime data. Everything under `data/` is
**generated/runtime data** and is ignored by git (see `.gitignore`);
only `.gitkeep` files are committed to preserve the layout.

| Directory          | Planned content                                  |
| ------------------ | ------------------------------------------------ |
| `data/sqlite/`     | Collector SQLite database (WAL mode), runtime    |
| `data/events/`     | Raw event stream as JSONL files, runtime         |
| `data/analytics/`  | CSV / JSONL analytics exports, generated         |

Rules:

- Database schema is **not** defined at bootstrap time.
- Persistence implementation is **not** created at bootstrap time.
- Nothing under `data/` is ever committed.