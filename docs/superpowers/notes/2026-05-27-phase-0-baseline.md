# Phase 0 — VICE 3.10 upgrade baseline findings

**Date:** 2026-05-27
**Branch:** vice-3.10-upgrade

## Reference sources acquired

- Vanilla VICE 3.1: `~/vice-ref/3.1/src/` (downloaded from SourceForge releases — vice-3.1.tar.gz)
- Vanilla VICE 3.10: `~/vice-ref/3.10/src/` (downloaded from SourceForge releases — vice-3.10.tar.gz)

## Baseline diff summary

Diff command: `diff -ruN ~/vice-ref/3.1/src/ src/Emulators/vice/`
Diff size: 2,715,007 lines (92 MB on disk)

The large size is expected: the `-N` flag in `diff -ruN` treats absent files as empty, so files that exist on one side only each contribute their entire content as additions or deletions. There are no "Only in ..." summary lines — every difference is rendered as a full unified diff.

Breakdown (using 1969-epoch timestamp as the marker for a file absent on that side):

- Files only in slajerek's tree (new additions — ViceInterface/, root/ extras, arch/ extensions): **408**
- Files only in vanilla 3.1 (absent from slajerek's tree — removed, restructured, or renamed): **7,174**
- Files present in both trees but different (the real modification set): **524**
- Files with `c64d_` / RetroDebugger hook markers (C64DEBUGGER, c64d, RetroDebugger, RETRO_DEBUGGER) in the canonical hook directories: **67**

Note: The expected 96 from the spec was not reached — the grep covered only 7 directories
(`c64/`, `drive/`, `monitor/`, `core/`, `root/`, `arch/`, `viciisc/`). The 67 count is correct
for those directories. Additional hook-carrying files may exist in other subdirectories not yet
surveyed (e.g., `sound/`, `resid/`).

The high "only in vanilla" count (7,174) reflects that slajerek's tree is a subset of vanilla
VICE: many platform/architecture/machine targets from the vanilla source (CBM-II, PET, VIC20,
Plus/4, C128, DTV, SCPU, etc.) were removed or not carried over. The in-tree `src/Emulators/vice/`
is scoped to the C64 + drive + monitor stack.

## Spot-check of modification style

Three representative files were diffed against their vanilla 3.1 counterparts:

### `c64/cart/reu.c` — 268 lines of diff

Additions (+79), Deletions (-24). The deletions are **not** functional removals — they are:
- `#include "types.h"` replaced by `#include "vicetypes.h"` (renamed header)
- `static` qualifier removed from several functions to expose them for external linkage (e.g.,
  `set_reu_enabled`, `set_reu_size`, `set_reu_filename`) — these become callable from ViceInterface
- One `static int reu_enabled` made `volatile int reu_enabled`

Additions include: `#include "ViceWrapper.h"`, `LOGD(...)` debug log calls, and
`c64d_maincpu_clk++` increments inserted at two clock-bump sites in REU cycle functions.

Pattern: mixed diff (both `+` and `-` lines), but the `-` lines are header renames and
`static`-to-public promotions, not logic deletions.

### `drive/drive.c` — 199 lines of diff

Additions (+138), Deletions (-1). The single deletion is `#include "types.h"` (replaced by
`#include "vicetypes.h"`). Everything else is pure addition:
- Two new fields initialized in `drive_init_structure`: `GCR_dirty_track_for_snapshot`,
  `GCR_dirty_track_needs_refresh`, `P64_dirty_for_snapshot`
- Commented-out `LOGD` stubs (left as `//`)
- NULL-guard additions in `drive_gcr_data_writeback_all` before dereferencing `drive_context[i]`
  and `drive` — these are safety patches, not control-flow changes
- 125-line block of new functions appended at end of file (beyond vanilla's last line)

Pattern: almost entirely additive; the one `-` line is a header rename.

### `monitor/monitor.c` — 186 lines of diff

Additions (+41), Deletions (-9). Deletions are header rename (`types.h` → `vicetypes.h`) plus
`static` qualifier removal from `make_prompt`, `monitor_open`, `monitor_process`, `monitor_close`
(same pattern as reu.c — promoting internal functions to external linkage). A closing brace and
one `monitor_close(1)` call are also restructured.

Additions include: `#include "DebuggerDefs.h"`, a new `execute_monitor_command_jump_trap`
function + trampoline inserted into `mon_jump`, and `c64d_set_debug_mode(DEBUGGER_MODE_RUNNING)`
calls in `mon_instructions_step`, `mon_instructions_next`, and `mon_instruction_return`.

Pattern: mixed diff; deletions are `static`-removal and header renames, not logic deletions.

**Overall modification style:** The dominant pattern across all three samples is:
1. Header rename: `types.h` → `vicetypes.h` (appears in every modified file)
2. `static` qualifier removal to expose functions
3. Pure additions: new `c64d_*` hook calls, `LOGD` debug traces, new functions appended at EOF
4. No original VICE logic is deleted or restructured — control flow is augmented, not replaced

## MTEngineSDL coupling

- MTEngineSDL location: `/Users/garion/develop/MTEngineSDL`
  (CMakeLists references it as `../MTEngineSDL` relative to the RetroDebugger repo root;
  the repo lives at `~/develop/MTEngineSDL`, not `~/Projects/MTEngineSDL`)
- Files referencing VICE internals: **7** (across 3 platform variants + 1 GUI file)
- Categories:
  - 6 files: logging infrastructure only — `DBG_Log.h`/`.mm` (macOS), `DBG_Log.h`/`.cpp` (Linux),
    `DBG_Log.h`/`.cpp` (Windows). These define three log-level bitmasks:
    `DBGLVL_VICE_DEBUG (1<<23)`, `DBGLVL_VICE_MAIN (1<<24)`, `DBGLVL_VICE_VERBOSE (1<<25)`,
    and the corresponding macros `LOGVD`, `LOGVM`, `LOGVV`.
  - 1 file: `src/Engine/GUI/Helpers/CGuiViewDebugLog.cpp` — renders toggle switches for the
    three VICE log levels in the engine's debug log UI.
- Concrete VICE symbols MTEngineSDL touches: **none**. MTEngineSDL references no VICE-internal
  symbols, types, or headers. The VICE coupling is entirely in named log-level constants
  (`DBGLVL_VICE_*`) that are defined within MTEngineSDL's own `DBG_Log.h`. These are
  string-labelled log channels, not structural dependencies on VICE internals.
- Risk assessment: **Low**. Upgrading VICE from 3.1 to 3.10 requires zero changes to MTEngineSDL.
  The log-level bitmasks are stable values with no tie to VICE version. No MTEngineSDL source file
  includes any VICE header or references any `c64d_*`, `vicii_*`, `maincpu_*`, or `drive_*`
  symbol. The only action needed is confirming MTEngineSDL is still at `../MTEngineSDL` relative
  to the repo at build time (it is, at `~/develop/MTEngineSDL`).

## Known surprises / open issues

1. **`types.h` → `vicetypes.h` rename is pervasive.** Every modified vanilla VICE file replaces
   `#include "types.h"` with `#include "vicetypes.h"`. This rename must be forward-ported
   mechanically when replaying patches onto 3.10 — the 3.10 source may have a different type
   header name or layout.

2. **`static` promotions create ABI surface.** The pattern of removing `static` from previously
   internal functions (to make them callable from ViceInterface) means those function signatures
   are part of the upgrade contract. Phase 1 must catalog every such promotion.

3. **7,174 "only in vanilla" entries.** The slajerek tree is a heavily stripped version of the
   vanilla source. The diff is not a delta of a complete VICE install — it is a curated subset.
   The 7,174 missing files are intentionally absent (other machine targets, autoconf infrastructure,
   build tooling). Phase 4 should not attempt to restore these.

4. **MTEngineSDL not at expected `~/Projects/MTEngineSDL` path.** CMakeLists says `../MTEngineSDL`
   (relative to the repo at `~/Projects/RetroDebugger/`), which resolves to
   `~/Projects/MTEngineSDL`. But the actual install is at `~/develop/MTEngineSDL`. This path
   mismatch will cause a build failure unless the CMakeLists path or a symlink is corrected
   before Phase 4 (the build phase). Track as a pre-build blocker.

5. **c64d_ file count discrepancy (67 vs spec's ~96).** The 67 count covers 7 subdirectories.
   The spec's ~96 likely includes additional directories not in the grep scope (e.g., `resid/`,
   `sound/`, platform-specific files under `arch/`). Phase 1 should run the hook scan with a
   wider glob.

## Followup decisions for Phase 1

- Phase 1 hook catalog should grep all of `src/Emulators/vice/` recursively (not directory-by-
  directory) to avoid missing hook files outside the 7 directories surveyed here.
- Phase 1 should specifically catalog every `static`-removal (function promotion) in addition
  to `c64d_*` hook sites — these are implicit API surface.
- Phase 1 should note the `types.h`→`vicetypes.h` rename in each file, since this is a
  mechanical change that will need automation when replaying patches onto 3.10.
- Before Phase 4 begins: resolve the MTEngineSDL path discrepancy (symlink or CMakeLists edit).
