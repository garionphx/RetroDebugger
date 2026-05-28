"""Lifecycle endpoint tests: reset, pause, continue, warp."""

import time


def test_hard_reset_returns_to_kernal(fresh_cpu):
    """After hard reset, KERNAL is running — PC should be in the $E000-$FFFF range."""
    status = fresh_cpu.cpu_status()["result"]
    pc = status["pc"]
    assert 0xE000 <= pc <= 0xFFFF, f"PC after reset = {pc:#06x}, expected KERNAL range"


def test_pause_then_continue_changes_running_state(fresh_cpu):
    """Cycle counter should be ~static while paused, advancing after continue."""
    rd = fresh_cpu
    rd.pause()
    time.sleep(0.05)
    c1 = rd.cpu_counters()["result"]["cycle"]
    time.sleep(0.05)
    c2 = rd.cpu_counters()["result"]["cycle"]
    # Paused -> cycle should not advance (or advance only minimally from internal ticks)
    delta_paused = c2 - c1
    assert delta_paused < 1000, f"Cycles advanced {delta_paused} while paused"

    rd.cont()
    time.sleep(0.05)
    c3 = rd.cpu_counters()["result"]["cycle"]
    delta_running = c3 - c2
    assert delta_running > 10000, f"Cycles advanced only {delta_running} while running"


def test_warp_on_increases_cycle_rate(fresh_cpu):
    """Enabling warp should measurably increase the cycle rate over wall time."""
    rd = fresh_cpu

    # Baseline rate without warp
    rd.call(f"{rd.platform}/warp/set", {"warp": False})
    rd.cont()
    c_start = rd.cpu_counters()["result"]["cycle"]
    time.sleep(0.5)
    c_end = rd.cpu_counters()["result"]["cycle"]
    rd.pause()
    rate_normal = (c_end - c_start) / 0.5

    # Warp rate
    rd.call(f"{rd.platform}/warp/set", {"warp": True})
    rd.cont()
    c_start = rd.cpu_counters()["result"]["cycle"]
    time.sleep(0.5)
    c_end = rd.cpu_counters()["result"]["cycle"]
    rd.pause()
    rate_warp = (c_end - c_start) / 0.5

    # Clean up
    rd.call(f"{rd.platform}/warp/set", {"warp": False})

    # Expect at least 1.5x — generous because warp ratio on macOS varies
    assert rate_warp > rate_normal * 1.5, \
        f"Warp rate {rate_warp:.0f} not >> normal rate {rate_normal:.0f}"


def test_soft_reset_does_not_crash(fresh_cpu):
    """Soft reset should succeed and CPU should be in KERNAL after."""
    fresh_cpu.reset(hard=False)
    time.sleep(0.5)
    status = fresh_cpu.cpu_status()["result"]
    pc = status["pc"]
    assert 0xE000 <= pc <= 0xFFFF, f"PC after soft reset = {pc:#06x}, not in KERNAL"
