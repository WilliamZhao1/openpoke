# Execution Agent Overload: Implementation Progress

Updated: 2026-11-07

The implementation follows `execution-agent-overload-implementation-plan.md`
in separately reviewable steps. Phase 0 is in progress.

## Step 1: Isolated data paths (complete)

**Old behavior:** Each persistent service independently constructed a path under
`server/data/`. Several stores read or created files during imports, before tests
could patch service dependencies.

**New behavior:** `server/data_paths.py` resolves `Settings.data_dir`, configured
with `OPENPOKE_DATA_DIR` and defaulting to the original `server/data/` root.
Execution roster/logs, conversation/working-memory logs, trigger SQLite storage,
Gmail connection/seen-message state, and timezone preferences use that helper.
Relative paths resolve from the process working directory; `~` is expanded and
empty environment values are rejected. Configure the root before imports and
restart the backend after changes; the setting does not migrate files.

`server/tests/run_tests.py` configures a disposable root and dummy integration
credentials before test discovery imports the application. README and
`.env.example` document the setting and the test command.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed all
23 tests: the 18 existing tests and 5 new data-path tests. New coverage includes
the legacy default, environment overrides, path expansion, invalid empty values,
and fresh-process persistence across all configured stores. The integration
test verifies two independent roots and clearing one without affecting the
other; it rejects socket connections. No live Gmail or model calls were used.
`git diff --check` passed for the tracked changes.

## Next steps in Phase 0

1. Add provider usage, component/model, elapsed-time, failure-category metrics,
   and correlation IDs through chat, callbacks, and scheduled work.
2. Add the fixed workflow catalogs and deterministic fake Gmail backend.
3. Add the executable evaluation harness, frozen manifest/inputs, and saved
   full-roster baseline evidence.

Phases 1–6 remain pending.
