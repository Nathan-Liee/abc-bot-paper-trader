# MQL5 Bridge — placeholder

**No implementation exists.** This directory only reserves the boundary
for the future MQL5 bridge component of the ABC Bot stack.

The bridge will run inside the HFM Demo MT5 terminal and will be the
**only** component of this repository that touches MT5. It is planned to:

- attach to the terminal's events for symbols/timeframes defined by spec;
- emit validated events into the local IPC / JSONL channel consumed by
  the Python Collector;
- deliberately contain **no order-placement functions at all**
  (read-only observer; live/demo execution is forbidden on this repo).

See `docs/architecture.md` for the placeholder architecture notes.

## Planned layout

```text
mql5-bridge/
|-- src/
|   |-- Include/          shared MQL5 headers (future)
|   |-- Experts/          bridge expert/future
|   +-- Scripts/          auxiliary scripts (future)
+-- docs/architecture.md  placeholder architecture
```