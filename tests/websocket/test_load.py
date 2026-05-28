"""Top-level load endpoint tests: PRG, D64."""

import time
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def test_load_prg_places_bytes_at_load_address(fresh_cpu):
    """`load` of known_state.prg should put the BASIC SYS line at $0801."""
    rd = fresh_cpu
    rd.call("load", {"path": str(FIXTURE_DIR / "known_state.prg")})
    time.sleep(0.2)
    # $0801 is BASIC pointer; first bytes are SYS-line tokens, not zero.
    head = rd.read_memory(0x0801, 16)
    assert any(b != 0 for b in head), \
        f"After load, memory at $0801 is empty: {head.hex()}"


def test_load_prg_then_makejmp_and_run(fresh_cpu):
    """End-to-end: load + makejmp + cont reaches park with sentinels in place."""
    rd = fresh_cpu
    rd.call("load", {"path": str(FIXTURE_DIR / "known_state.prg")})
    time.sleep(0.2)
    rd.call(f"{rd.platform}/cpu/makejmp", {"address": 0x0810})
    rd.cont()
    time.sleep(0.05)
    rd.pause()
    sentinels = rd.read_memory(0xC000, 4)
    assert sentinels == bytes([0xAA, 0xBB, 0xCC, 0xDD]), \
        f"E2E run produced wrong sentinels: {sentinels.hex()}"


@pytest.mark.skip(
    reason="Phase 4 bug: RD 3.1 closes the WebSocket with no close frame when "
           "load is given a nonexistent path — the bridge crashes instead of "
           "returning an error response. Baseline finding; fix needed before Phase 4."
)
def test_load_nonexistent_file_does_not_crash(fresh_cpu):
    """Loading a missing file should return an error response, not crash the bridge."""
    rd = fresh_cpu
    resp, _ = rd.call("load", {"path": "/nonexistent/file.prg"})
    # Should be a 4xx response, but the connection must survive.
    assert "status" in resp, f"load of nonexistent file returned no status: {resp}"
    # Verify we can still talk to RD.
    status = rd.cpu_status()
    assert status["status"] == 200, "WebSocket dead after bad load"
