# ABC Bot CI Regression Cleanup Report

Date: 2026-08-15
Committed documentation of the CI regression cleanup milestone. Companion: `AGENTS.md` (§3, §5, §15, §16).

Final verdict: **CI BASELINE GREEN**

## 1. Repository Baseline

- Repo: `D:\Project\abc-bot-paper-trader`
- Branch: `main`; remote: `origin https://github.com/Nathan-Liee/abc-bot-paper-trader`
- HEAD before task: `3d6bdee` (unpushed); origin/main HEAD: `f875bb9`
- Working tree: dirty (untracked benchmark artifacts from prior milestone)
- GitHub Actions state before task: **red** — last 5 main runs (`b428f33`, `172f6d2`, `c47d2d5`, `36228cb`, `f875bb9`) all failed at the **Test** step (Lint/Format/Type-check steps passed in CI)
- Local baseline (Windows, Python 3.11.15): full suite green, ruff/format/mypy green — CI-only failure suspected

## 2. CI Failure Inventory

Reproduction commands (local, `uv`):

| Check | Command | Local result |
|---|---|---|
| pytest (359 collected) | `uv run pytest --maxfail=0` | PASS (exit 0) |
| lint | `uv run ruff check .` | PASS |
| format | `uv run ruff format --check .` | PASS (96 files) |
| type-check | `uv run mypy collector shared` | PASS (48 files) |
| schema/migration/safety tests | included in pytest suite | PASS |

GitHub Actions log download blocked (403 without auth). CI failure reproduced by running the suite's reader logic in **WSL Ubuntu-22.04 (Linux)** — the ONLY failing behavior found:

- `tests/unit/test_jsonl_reader.py::test_recreate_after_unlink_is_new_stream`
  - Expected: `poll.rotation is True`
  - Actual on Linux: `poll.rotation is False`, lines `[]`, offset advanced over the new stream

Classification: **CODE BUG** (platform-latent), reproduced as **ENVIRONMENT DIFFERENCE** (Linux `ext4`/drvfs vs Windows NTFS).

## 3. Root Cause Groups

Single shared root cause (one bug, not five):

**Group R1 — rotation detection relied on inode identity alone.**
`JsonlFileReader` detected stream replacement via `(st_dev, st_ino)` mismatch or `size < offset`. After `unlink()` + recreate, Linux filesystems (ext4; also reproduced on WSL drvfs) may **reuse the inode number immediately**. With a same-size new stream (`{"seq":1}` → `{"seq":2}`, both 9 bytes), neither signal fires:

- identity equal (inode reused)
- size equal, not `< offset`
→ the new stream is silently tailed as a continuation of the old one. On Windows (NTFS file IDs, distinct) the test passed, which is why local was green and CI (ubuntu) was red.

Failure mode if unfixed in production: exporter rotation (unlink/rename → recreate) on Linux could be absorbed as a tail; the reader would skip lines of the new stream and parse garbage at the old offset (silent data misalignment after rotation).

Verified via WSL repro (pre-fix): `poll3 rotation=False lines=[]`; post-fix: `poll3 rotation=True lines=[{"seq":2}]`.

## 4. Fixes Applied

Minimal change, architecture preserved, contract/schema/persistence/reconciliation/safety untouched.

`collector/adapters/reader.py`:
- Track `_gap` flag: set when `poll()` finds the file unavailable (stat OSError).
- New rotation branch: if a previous poll was unavailable (`_gap`) and identity was already established → **rotation** (disappearance gap = new stream). This covers inode-reuse recreate, the case inode identity cannot prove.
- Identity-mismatch and size-shrink branches unchanged.
- `reset()` clears `_gap`; docstring updated.

Committed: `1ba7fff` (fix), `99b9653` + `95ed6a9` (AGENTS.md live updates), `aab70e5` (benchmark artifacts: runner fail-closed tests 20, spec, dataset, inventory report — additive, from prior milestone, no trading capability).

## 5. Regression Tests

- `tests/unit/test_jsonl_reader.py::test_recreate_after_unlink_is_new_stream` — existing test, is the regression test: fails pre-fix on Linux, passes post-fix on Linux (WSL) and Windows.
- Repro harness (not committed): reader poll sequence unlink→recreate under WSL; evidence in §3/§4.
- No other tests modified. No test was weakened to pass.

## 6. Local Validation

| Check | Result |
|---|---|
| `uv run pytest` | PASS — 359 collected, exit 0 |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS |
| `uv run mypy collector shared` | PASS — no issues in 48 source files |
| WSL Linux repro of rotation bug | FIXED (rotation=True, line re-read) |

## 7. GitHub Actions Validation

- Push `f875bb9..aab70e5` → run **31820083519** test/lint/type-check job: **success**, all steps PASS (Checkout, Sync, Lint, Format check, Type-check, Test).
- Push `.95ed6a9` (AGENTS.md only) → run **completed success**.
- Required checks: test, lint, format, type-check — all green.

## 8. Security/Safety Checks

- No trading/execution capability touched. Reader change is read-only telemetry; no new API surface.
- Filesystem semantics: gap-based rotation is conservative (any disappearance + reappearance = new stream). The exporter is the only actor that removes/recreates the file; no legitimate resume-after-unlink case exists in the pipeline.
- Safety tests (`tests/mql5/test_bridge_safety.py`, execution-token scans) PASS.
- No credentials, no `.env` changes, no CI workflow changes needed.

## 9. AGENTS.md Live Update

- Start-of-task: CURRENT MILESTONE = CI REGRESSION CLEANUP; work log entry "failure inventory + root cause found" (`99b9653`).
- End-of-task: CURRENT PHASE = AI MODEL BENCHMARK; CURRENT MILESTONE = READY TO RESUME BENCHMARK; CURRENT TASK = RESUME AI MODEL BENCHMARK IMPLEMENTATION; Handoff Snapshot + work log updated with CI green evidence (`95ed6a9`).
- Prior history preserved; work log append-only.

## 10. Commit(s)

| Commit | Message |
|---|---|
| `1ba7fff` | fix(collector): detect rotation on disappearance gap |
| `99b9653` | docs(agent): record CI regression cleanup inventory + root cause |
| `aab70e5` | test(benchmark): runner failure-handling tests + inventory artifacts |
| `95ed6a9` | docs(agent): mark CI baseline green, handoff to benchmark resume |

## 11. Final Verdict

`CI BASELINE GREEN`

- all tests PASS (359)
- ruff PASS
- format PASS
- mypy PASS
- required GitHub Actions PASS (run 31820083519, all steps success)
- no unresolved regression blocker
- working tree clean

## 12. Next Milestone

Next action: **RESUME AI MODEL BENCHMARK IMPLEMENTATION** (per AGENTS.md §5). No benchmark implementation performed in this task, per scope.