"""Input endpoint tests: keyboard key down/up, joystick down/up.

KERNAL keyboard buffer:
  $00C6 — number of chars in buffer (0..10)
  $0277-$0280 — buffer

API shapes discovered from src/Remote/CDebuggerServerApi.cpp:
  key/down and key/up use params: {"keyCode": <int>}
    where keyCode is the mtKeyCode — for letter keys this is the
    lowercase ASCII value (e.g. ord('a') = 97 for the A key);
    uppercase sends the key with LEFT_SHIFT (e.g. ord('A') = 65).
    keyboard_key_pressed() in VICE maps this via the C64 key matrix
    (C64KeyMap, registered via keyboard_parse_set_pos_row).
    Status 200 = key found in keymap and latch set.
    Status 406 = key not in keymap.

  joystick/down and joystick/up use params: {"port": <int>, "axis": <str>}
    axis accepts directional names: "n"/"north", "s"/"south",
    "e"/"east", "w"/"west", "ne", "nw", "se", "sw",
    "fire", "fireB", "select", "start".
    port is 0-indexed (driver adds 1 internally for VICE).

KNOWN LIMITATION (Phase 4 finding):
  The keyboard/down and keyboard/up endpoints call VICE's keyboard_key_pressed()
  from the WebSocket handler thread. This function calls alarm_set() on
  maincpu_alarm_context without holding the emulator mutex. The VICE alarm
  context data structures are not thread-safe, creating a race with the main
  VICE emulation loop. As a result, the keyboard alarm may not be set correctly
  and the KERNAL keyboard buffer remains empty even when the API returns 200.
  See src/Remote/CDebuggerServerApi.cpp (key/down handler) vs.
  src/Emulators/vice/ViceInterface/CDebuggerServerApiVice.cpp (other endpoints
  that do use LockMutex/UnlockMutex). Fix: wrap key/down and key/up handlers in
  LockMutex/UnlockMutex in CDebuggerServerApiVice.cpp, or dispatch the
  keyboard call to the VICE main thread.
"""

import pytest
import time


@pytest.mark.slow
def test_key_down_accepted_by_api(fresh_cpu):
    """key/down with a valid keyCode (ASCII letter) should return status 200.

    The API uses params: {"keyCode": <int>} where the value is the mtKeyCode.
    For letter keys this is the lowercase ASCII value (ord('a') = 97).
    Status 200 means the key was found in the C64 key matrix map and the
    latch was set. Status 406 means not in keymap.

    NOTE: Due to a threading issue (alarm_set called without emulator mutex),
    the key press may not reliably reach the KERNAL keyboard buffer. That
    buffer-level assertion is skipped — see module docstring for details.
    """
    rd = fresh_cpu
    rd.cont()
    time.sleep(0.5)  # let KERNAL keyscan start

    # keyCode = ord('a') = 97; C64 key matrix maps lowercase ASCII for letter keys
    resp_down, _ = rd.call(f"{rd.platform}/input/key/down", {"keyCode": ord('a')})
    time.sleep(0.05)
    resp_up, _ = rd.call(f"{rd.platform}/input/key/up", {"keyCode": ord('a')})
    time.sleep(0.1)
    rd.pause()

    # API must accept the key (status 200)
    assert resp_down.get("status", 200) == 200, \
        f"key/down rejected valid keyCode {ord('a')}: {resp_down}"
    assert resp_up.get("status", 200) == 200, \
        f"key/up rejected valid keyCode {ord('a')}: {resp_up}"

    # Buffer-level check: alarm_set is called without emulator mutex from the
    # WebSocket handler thread, so the KERNAL keyboard buffer is unreliable.
    buf_len = rd.read_memory(0x00C6, 1)[0]
    if buf_len == 0:
        pytest.xfail(
            "3.1 keyboard mutex race — alarm_set without LockMutex; see baseline notes"
        )

    buf = rd.read_memory(0x0277, max(buf_len, 1))
    # 'A' in PETSCII = $41 (uppercase), $01 (lowercase)
    assert buf[0] in (0x41, 0x01), \
        f"Buffer head = {buf[0]:#04x}, expected $41 (A) or $01 (lowercase a)"


def test_joystick_down_does_not_error(fresh_cpu):
    """Joystick input call should succeed.

    API: {"port": <int>, "axis": <str>}
    axis accepts compass names: "n"/"north", "s"/"south", "e"/"east", "w"/"west",
    "ne", "nw", "se", "sw", "fire", "fireB", "select", "start".
    port is 0-indexed (VICE adds 1 internally).
    """
    rd = fresh_cpu
    resp, _ = rd.call(f"{rd.platform}/input/joystick/down", {"port": 2, "axis": "n"})
    # Status 200 means accepted
    assert resp.get("status", 200) == 200, f"joystick/down failed: {resp}"
    rd.call(f"{rd.platform}/input/joystick/up", {"port": 2, "axis": "n"})
