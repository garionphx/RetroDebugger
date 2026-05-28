# RetroDebugger WebSocket regression suite

A pytest suite that exercises RetroDebugger's JSON-over-WebSocket debugger API
(port 3563). It captures how the **current VICE 3.1 build behaves** so the
in-progress VICE 3.1 → 3.10 upgrade can be validated against a stable baseline.
Tests assert *observable behavior* (register values, memory contents, cycle
counts) rather than internal emulator state, so they remain meaningful across
the version jump.

See `../docs/superpowers/specs/2026-05-27-vice-3.10-upgrade-design.md` for the
upgrade design and `../docs/vice-hook-surface.md` for the VICE modification
catalog.

## Prerequisites

1. **RetroDebugger must be running** with the WebSocket server enabled on
   `ws://127.0.0.1:3563/stream`.

   - Enable the server once by setting `RunDebuggerServerWebSockets: true` in
     `~/Library/RetroDebugger/settings.hjson`.
   - Launch:
     ```sh
     "/Applications/Retro Debugger.app/Contents/MacOS/Retro Debugger" -c64 -unpause &
     ```
   - Give it ~6 seconds to bind the port. Verify: `nc -z 127.0.0.1 3563 && echo READY`.

2. **True Drive Emulation must be on** (the drive-memory tests need it):
   Settings → Emulator → C64 → Drive emulation → True drive.

3. **Python deps** are installed in a local virtualenv at `tests/.venv`
   (created automatically the first time; see Setup below).

## Setup (first time only)

```sh
cd tests
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `.venv/` directory is gitignored.

## Running the tests

From the repository root, use the runner script (it activates the venv for you):

```sh
./tests/run-ws-tests.sh
```

A clean run looks like:

```
28 passed, 1 skipped, 1 xfailed in ~21s
```

The `1 skipped` and `1 xfailed` are **expected** — they track two real,
known bugs in the current 3.1 build (see "Known non-passing tests" below).
A run is healthy as long as it reports `28 passed` with **0 failed**.

### Variations

```sh
./tests/run-ws-tests.sh -v                      # one line per test
./tests/run-ws-tests.sh websocket/test_cpu.py   # a single file
./tests/run-ws-tests.sh -k warp                 # tests matching a name
./tests/run-ws-tests.sh --durations=10          # show the 10 slowest tests
```

### Running pytest directly

```sh
cd tests
source .venv/bin/activate
pytest websocket/ -v
```

## What the suite covers

| File | Endpoint family |
|---|---|
| `websocket/test_lifecycle.py` | reset, pause/continue, warp |
| `websocket/test_cpu.py` | cpu/status, counters, makejmp, step/instruction, step/cycle |
| `websocket/test_memory.py` | main memory + drive 1541 read/write, RAM-vs-I/O views |
| `websocket/test_breakpoints.py` | CPU PC breakpoints, memory-access breakpoints |
| `websocket/test_chips.py` | VIC, CIA, SID register read/write |
| `websocket/test_input.py` | keyboard, joystick |
| `websocket/test_load.py` | top-level `load` (PRG) |

Shared fixtures live in `conftest.py`:

- `rd` — one session-scoped WebSocket connection
- `fresh_cpu` — hard-resets the machine before each test (and forces warp off)
- `loaded_fixture` — loads `fixtures/known_state.prg`, runs it to the `park`
  loop at `$0837`, and leaves the CPU paused there with known sentinels in
  memory (`$C000-$C003 = AA BB CC DD`, screen cleared)

`retrodebugger.py` is the WebSocket client. Its `_call()` sends a unique
`token` per request and matches it in the response, skipping asynchronous event
frames — preserve that correlation if you edit the client, or event frames will
race the responses.

## Test fixture

`fixtures/known_state.prg` is a tiny 6502 program (source:
`fixtures/known_state.asm`) that establishes a known machine state. Rebuild it
with KickAssembler after editing the source:

```sh
./tests/fixtures/build.sh
```

`park` is at `$0837`; tests that reference it use that address.

## Known non-passing tests (current 3.1 bugs — Phase 4 fix targets)

- **`test_load.py::test_load_nonexistent_file_does_not_crash`** *(skipped)* —
  loading a nonexistent path crashes the WebSocket connection (no close frame)
  instead of returning an error. 3.10 should return a 4xx and keep the
  connection alive.
- **`test_input.py::test_key_down_accepted_by_api`** *(xfail)* — `key/down`
  calls `alarm_set()` without holding the emulator mutex from the WebSocket
  thread, so the KERNAL keyboard buffer isn't reliably populated. The fix is to
  wrap `key/down`/`key/up` in `LockMutex` in `CDebuggerServerApiVice.cpp`.

These are documented in full in `../docs/superpowers/notes/2026-05-27-phase-0-baseline.md`.
