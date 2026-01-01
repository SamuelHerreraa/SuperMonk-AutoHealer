from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from config import TOGGLE_ACTIVE_KEY
from states import STATE, state_lock


def parse_hotkey(s: str):
    s = s.strip().lower()

    # f1..f24
    if s.startswith("f") and s[1:].isdigit():
        return getattr(Key, s)

    # single character like: \ 1 q etc
    if len(s) == 1:
        return KeyCode.from_char(s)

    raise ValueError(f"Hotkey inválida: {s}")


TOGGLE_ACTIVE = parse_hotkey(TOGGLE_ACTIVE_KEY)


def _on_key_press(k):
    if k == TOGGLE_ACTIVE:
        with state_lock:
            STATE["active"] = not STATE["active"]
            print(f"🎛️ ACTIVE = {STATE['active']}")


def start_listener():
    listener = keyboard.Listener(on_press=_on_key_press)
    listener.daemon = True
    listener.start()
