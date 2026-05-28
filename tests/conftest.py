"""Shared pytest fixtures for the RetroDebugger WebSocket regression suite.

Assumes a RetroDebugger instance is running with the WebSocket server enabled
on ws://127.0.0.1:3563/stream. See plan's Phase 0.5 prerequisites.
"""

import sys
import time
from pathlib import Path

import pytest

# Make `tests/retrodebugger.py` importable from `tests/websocket/test_*.py`.
sys.path.insert(0, str(Path(__file__).parent))
from retrodebugger import RetroDebugger  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def rd():
    """One WebSocket connection shared across the session."""
    client = RetroDebugger()
    yield client
    client.close()


@pytest.fixture
def fresh_cpu(rd):
    """Hard-reset before each test; settle KERNAL."""
    rd.reset(hard=True)
    time.sleep(0.5)
    return rd


@pytest.fixture
def loaded_fixture(fresh_cpu):
    """Reset, load known_state.prg, jump to $0810, run briefly, pause at park loop."""
    rd = fresh_cpu
    rd.call("load", {"path": str(FIXTURE_DIR / "known_state.prg")})
    time.sleep(0.2)
    rd.call(f"{rd.platform}/cpu/makejmp", {"address": 0x0810})
    rd.cont()
    time.sleep(0.05)
    rd.pause()
    return rd
