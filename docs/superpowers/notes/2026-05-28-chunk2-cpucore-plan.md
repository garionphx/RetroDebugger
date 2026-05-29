# Chunk 2 CPU-core re-merge plan (reassessment, 2026-05-28)

Triggered by discovering drivecpu.c's inlined 6502 core is stale 3.1. This doc maps ALL
stale inlined cores and the remaining Chunk 2 surface, with a validated methodology and
recommended sequencing. The cycle-exact core re-merges are the genuine hard core of the
VICE 3.1->3.10 upgrade (and the source of the 1541-accuracy goal).

## Architecture: who inlines what

RD inlines cross-dir core `.c` files into their host CPU/device file (aux-core inline
convention). Discovered inline relationships:

- `drivecpu.c`      inlines `6510core.c`     (markers lines 496-3693)  -> drive 6502
- `drivecpu65c02.c` inlines `65c02core.c`    (//#include line 410)     -> drive 65C02  [DONE]
- `c64cpusc.c`      inlines `mainc64cpu.c`   (lines 217-4356), which itself inlines
                    `6510dtvcore.c` (nested, //#include at line 1299)  -> MAIN C64 CPU
- `c64acia1.c`      inlines `aciacore.c`     (lines 96-1322)           -> ACIA 6551
- `cpmcart.c`       inlines `z80core.c`      [DONE, CART batch]
- `digimax.c`/`shortbus_digimax.c`/`userport_digimax.c` inline `digimaxcore.c` [DONE]

NOTE: main CPU core is `6510dtvcore.c` (handles both 6510 and DTV via #ifdef C64DTV), NOT
`6510core.c`. Drive core is `6510core.c`. They are SEPARATE files, each with its own
inlined copy. No sharing -> each needs its own re-merge.

## Stale-core inventory (cycle-exact 3-way re-merges needed)

| Core (host)                         | upstream Δ 3.1->3.10 | _DUMMY 3.1->3.10 | isolated merge conflicts | status |
|-------------------------------------|----------------------|------------------|--------------------------|--------|
| 6510core.c (drivecpu.c)             | 1304 lines           | 0 -> 107         | 68                       | STALE  |
| 6510dtvcore.c (c64cpusc.c, nested)  | 521 lines            | 12 -> 34         | TBD                      | STALE  |
| mainc64cpu.c (c64cpusc.c)           | 317 lines            | n/a              | TBD                      | STALE  |
| aciacore.c (c64acia1.c)             | 413 lines            | n/a              | 30                       | STALE  |
| 65c02core.c (drivecpu65c02.c)       | 130 lines            | n/a              | -                        | DONE   |

Staleness evidence: drive 6510core has 0 `_DUMMY` (3.10 has 107); c64cpusc.c has
`#include "clkguard.h"` + `clk_guard_t *maincpu_clk_guard` (3.10 removed clkguard); its 12
`_DUMMY` are 3.1's dtvcore dummies, not 3.10. RD instrumentation is PERVASIVE in 6510core
(~hooks woven through nearly every instruction).

## VALIDATED methodology: isolated per-core 3-way merge

The whole-file diff3 on drivecpu.c is CORRUPTED (the inlined core shifts everything ->
3 spurious drivecpu_execute defs). But merging the ISOLATED inlined-core region aligns
cleanly (6510core -> 68 well-formed conflicts). So:

1. Extract RD's inlined core region (between the `/// X.c starts/ends here` markers) -> ours.
2. base = vanilla 3.1 core, theirs = vanilla 3.10 core (both sed `types.h`->`vicetypes.h`).
3. `git merge-file -p --diff3 ours base theirs` -> conflicts only where RD hooks meet 3.10 changes.
4. Resolve each: take 3.10 cycle-exact logic as base truth, re-apply RD's debugger-hook delta
   on top (same principle as every prior merge). Highest care: a misplaced hook = wrong
   drive/CPU timing. The >-gate canNOT validate cycle placement -> manual review of each
   resolved instruction hook.
5. >-gate: resolved core vs vanilla 3.10 core (sed vicetypes->types). `>`=0 (no dropped 3.10
   cycle logic, except documented intentional); `<`=RD hooks (eyeball each).
6. Re-insert between the host file's `/// X.c starts/ends here` markers.
7. Apply the host-file scaffolding 3.10 delta separately (drivecpu.c/c64cpusc.c wrapper:
   loop condition, CLOCK tcycles, ORIGIN_MEMSPACE/CPU_LOG_ID/CPU_IS_JAMMED, JAM rename, etc.).

## Full remaining Chunk 2 surface (honest inventory)

A. CYCLE-EXACT CORE RE-MERGES (the delicate heart):
   A1. drivecpu.c inlined 6510core.c    (68 conflicts) -> drive 6502 / 1541 accuracy
   A2. c64cpusc.c inlined mainc64cpu.c + nested 6510dtvcore.c -> main C64 CPU
   A3. c64acia1.c inlined aciacore.c    (30 conflicts) -> ACIA 6551 (also clkguard straggler)

B. DRIVE-CLUSTER type/clkguard migration (mechanical; drivecpu.c part done on /tmp working copy):
   B1. drivecpu.c scaffolding: drive_context_t->diskunit_context_t, drop clkguard +
       drivecpu_prevent_clk_overflow, 3.10 scaffolding delta (field map in flags-doc DECISION 11).
   B2. drive.c: diskunit migration (58 refs) + drop prevent_clk_overflow call at :514.
   B3. drive-overflow.c/.h: DELETE (gone in 3.10).

C. CLKGUARD-removal stragglers:
   C1. datasette.c: clkguard removal.
   C2. clkguard.c / clkguard.h: DELETE from tree + Xcode build-list.
   (c64acia1.c clkguard handled with A3; c64cpusc.c clkguard handled with A2.)

D. POST-MERGE: build-list reconciliation (add new 3.10 .c units, drop GONE files) + link +
   re-enable WebSocket regression suite (28 pass / 1 skip / 1 xfail) as the acceptance gate.

## Recommended sequencing

1. drivecpu.c FULL: 6510core.c re-merge (A1) + scaffolding (B1). Self-contained (drive-only),
   validates the methodology on the biggest core, delivers the headline 1541-accuracy goal.
2. drive.c (B2) + delete drive-overflow.c (B3). Completes + makes the drive subsystem
   type-coherent (the approved cluster).
3. c64cpusc.c (A2 + scaffolding): mainc64cpu.c + nested 6510dtvcore.c re-merge. The main CPU;
   hardest extraction (nested inline). Includes its clkguard removal.
4. clkguard stragglers: c64acia1.c (A3 aciacore re-merge + clkguard), datasette.c (C1),
   delete clkguard.c/.h (C2).
5. Build-list + link + WebSocket suite (D).

Status when this plan was written: monitor.c committed (00f5e94). drivecpu.c type-migration
(B1 field/type sed) staged on /tmp/dcpu_work only — NOT applied to live; live drivecpu.c is
still untouched RD 3.1. No core re-merge started yet (paused here to reassess per user).
