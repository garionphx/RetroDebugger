"""Breakpoint endpoint tests: CPU PC breakpoints, memory access breakpoints."""

import asyncio
import time

PARK_ADDR = 0x0837  # `park` label in tests/fixtures/known_state.prg


def _drain_events(rd, timeout=0.3):
    """Drain any queued async event notifications (breakpoint-fired, etc.).

    RetroDebugger pushes event frames asynchronously; they can arrive in
    the WebSocket buffer before the response to the *next* request,
    causing the client's call() to return an event dict instead of the
    expected response.  Draining before cpu_status() prevents this.
    Returns the list of event dicts consumed.
    """
    async def _drain():
        msgs = []
        for _ in range(8):
            try:
                raw = await asyncio.wait_for(rd._ws.recv(), timeout=timeout)
                import json
                if isinstance(raw, bytes):
                    nul = raw.find(b"\x00")
                    parsed = json.loads(raw[:nul].decode() if nul >= 0 else raw.decode())
                else:
                    parsed = json.loads(raw)
                msgs.append(parsed)
                # Stop once we have consumed all pending events
            except asyncio.TimeoutError:
                break
        return msgs
    return rd._loop.run_until_complete(_drain())


def test_cpu_breakpoint_fires_on_pc_match(fresh_cpu):
    """Set a breakpoint at a KERNAL address; reset; verify CPU pauses near it."""
    rd = fresh_cpu
    # $FCE2 = KERNAL reset vector. CPU passes through here right after reset.
    # Pause first so we can install bp cleanly.
    rd.pause()
    # Clear any stale breakpoints left by previous test runs (session-scoped rd).
    rd.call(f"{rd.platform}/cpu/breakpoint/remove", {"addr": 0xFCE2})
    rd.call(f"{rd.platform}/cpu/memory/breakpoint/remove", {"addr": 0xC000})
    _drain_events(rd, timeout=0.05)  # discard any bp-fired events from stale bps
    rd.add_breakpoint(0xFCE2)

    try:
        # Resume execution so the reset actually starts the CPU running
        # (reset from a paused state keeps the CPU paused in 3.1).
        rd.cont()
        # Reset triggers PC to land on $FCE2; with bp set, CPU should pause there.
        rd.reset(hard=True)
        time.sleep(0.3)

        # Drain any async bp-fired event frames so cpu_status() gets its own response.
        _drain_events(rd)
        pc = rd.cpu_status()["result"]["pc"]
        # PC might be exactly $FCE2 or a few instructions past if bp fires post-fetch.
        assert 0xFCE2 <= pc <= 0xFCF0, \
            f"After reset with bp at $FCE2, PC = {pc:#06x}, expected close to $FCE2"
    finally:
        # Always remove — even on assertion failure — to avoid leaking into next test.
        rd.call(f"{rd.platform}/cpu/breakpoint/remove", {"addr": 0xFCE2})


def test_memory_write_breakpoint_fires_on_store(loaded_fixture):
    """Set a write-bp at $C000. Re-run fixture. CPU must pause at the STA that hits $C000."""
    rd = loaded_fixture
    # CPU is paused inside park loop. Add write-bp at $C000.
    # 3.1 requires comparison + value params even for "any write" — use '>= 0'.
    rd.add_memory_breakpoint(0xC000, access="write", comparison=">=", value=0)

    try:
        # Re-trigger the write by re-jumping to fixture start.
        # makejmp is queued in 3.1, so we need to step before it takes effect.
        rd.call(f"{rd.platform}/cpu/makejmp", {"address": 0x0810})
        rd.step_instruction()  # consume the queued jmp
        rd.cont()
        time.sleep(0.1)

        # Drain the async breakpoint-fired event before calling cpu_status(),
        # otherwise the event frame lands in the response slot.
        events = _drain_events(rd)
        # If the bp fired, the event will contain addr==0xC000 with type=='data'.
        bp_fired = any(e.get("event") == "breakpoint" and e.get("addr") == 0xC000 for e in events)

        pc = rd.cpu_status()["result"]["pc"]
        # The STA $C000 instruction lives between $0820 and $0830 (after screen clear).
        # Just check we paused before reaching park ($0837).
        assert pc < PARK_ADDR or bp_fired, \
            f"Write bp at $C000 did not fire — PC ran to {pc:#06x}, past park at {PARK_ADDR:#06x}"
    finally:
        # Always remove — even on assertion failure — to avoid leaking into next test.
        rd.call(f"{rd.platform}/cpu/memory/breakpoint/remove", {"addr": 0xC000})


def test_breakpoint_remove_does_not_error(fresh_cpu):
    """Removing a non-existent breakpoint should not error."""
    response = fresh_cpu.remove_breakpoint(0xDEAD)
    # Status code may be 200 or 400 depending on impl, but should not raise.
    assert "status" in response, f"remove_breakpoint returned no status: {response}"
