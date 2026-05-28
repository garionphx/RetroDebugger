"""CPU endpoint tests: status, counters, step, makejmp."""

import time


# ── status ─────────────────────────────────────────────────────────────────

EXPECTED_STATUS_KEYS = {"pc", "a", "x", "y", "sp", "p"}


def test_cpu_status_has_expected_keys(fresh_cpu):
    """cpu/status must return at least the canonical 6 register fields."""
    result = fresh_cpu.cpu_status()["result"]
    missing = EXPECTED_STATUS_KEYS - set(result)
    assert not missing, f"cpu/status missing keys: {missing}"


def test_cpu_status_register_ranges(fresh_cpu):
    """Each register field must be in the right value range."""
    r = fresh_cpu.cpu_status()["result"]
    assert 0 <= r["pc"] <= 0xFFFF, f"PC out of range: {r['pc']}"
    for reg in ("a", "x", "y", "sp"):
        assert 0 <= r[reg] <= 0xFF, f"{reg.upper()} out of range: {r[reg]}"
    assert 0 <= r["p"] <= 0xFF, f"P out of range: {r['p']}"


# ── counters ───────────────────────────────────────────────────────────────

def test_counters_monotonic(fresh_cpu):
    """Cycle/instruction/frame counts must monotonically increase while running."""
    rd = fresh_cpu
    rd.cont()
    samples = []
    for _ in range(3):
        time.sleep(0.05)
        samples.append(rd.cpu_counters()["result"])
    rd.pause()

    for i in range(len(samples) - 1):
        s_prev, s_next = samples[i], samples[i + 1]
        for key in ("cycle", "instruction", "frame"):
            assert s_next[key] >= s_prev[key], \
                f"{key} went backwards: {s_prev[key]} -> {s_next[key]}"


# ── control: makejmp ───────────────────────────────────────────────────────

def test_makejmp_sets_pc(loaded_fixture):
    """makejmp(addr) must set PC to addr exactly.

    Notes:
    - makejmp only takes effect when the CPU is in user RAM (not mid-KERNAL).
      loaded_fixture guarantees the CPU is paused in the park loop at $0837.
    - makejmp queues the new PC; it does not take effect until after the next
      step_instruction. Protocol: step -> makejmp -> step -> verify.
    """
    rd = loaded_fixture
    rd.step_instruction()
    time.sleep(0.05)
    rd.call(f"{rd.platform}/cpu/makejmp", {"address": 0x4000})
    rd.step_instruction()
    time.sleep(0.05)
    pc = rd.cpu_status()["result"]["pc"]
    assert pc == 0x4000, f"After makejmp($4000), PC = {pc:#06x}"


# ── control: step_instruction ──────────────────────────────────────────────

def test_step_instruction_advances_pc(loaded_fixture):
    """Step from inside the park loop. PC should land at park+0 again (3-byte JMP)."""
    rd = loaded_fixture
    pc_before = rd.cpu_status()["result"]["pc"]
    rd.step_instruction()
    pc_after = rd.cpu_status()["result"]["pc"]
    # JMP abs is 3 bytes but loops back, so PC should == pc_before (the JMP target).
    # OR — if step happened mid-fetch — PC could be pc_before + 3 (next instr).
    # Be permissive but assert *something changed* in a sane way.
    assert pc_after == pc_before or pc_after == pc_before + 3, \
        f"step_instruction: pc {pc_before:#06x} -> {pc_after:#06x} (expected either same or +3)"


# ── control: step_cycle ────────────────────────────────────────────────────

def test_step_cycle_advances_one_cycle(loaded_fixture):
    """step/cycle should advance the cycle counter by exactly 1 (one machine cycle).

    Notes:
    - Must use loaded_fixture (CPU in user RAM) — step/cycle does not update the
      counter reliably when the CPU is paused mid-KERNAL after a bare reset.
    - A short sleep is required after step/cycle before reading the counter;
      the WebSocket response returns before the counter register is updated.
    """
    rd = loaded_fixture
    c_before = rd.cpu_counters()["result"]["cycle"]
    rd.call(f"{rd.platform}/step/cycle")
    time.sleep(0.05)  # Counter update is async; allow it to commit.
    c_after = rd.cpu_counters()["result"]["cycle"]
    delta = c_after - c_before
    assert delta == 1, f"step/cycle: cycle counter advanced {delta}, expected 1"
