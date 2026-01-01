# hotkeys.py
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from config import TOGGLE_ACTIVE_HUNT_KEY, TOGGLE_ACTIVE_BOSS_KEY
from states import STATE, state_lock


def parse_hotkey(s: str):
    """
    Convierte una string de hotkey en un objeto Key o KeyCode de pynput.
    Soporta:
    - f1 a f24
    - Caracteres simples (letras, números, símbolos como \, /, -, *, 9, etc.)
    - Algunas teclas especiales por nombre
    """
    s = s.strip().lower()

    # f1..f24
    if s.startswith("f") and s[1:].isdigit():
        num = int(s[1:])
        if 1 <= num <= 24:
            return getattr(Key, f"f{num}")

    # Caracteres simples (esto incluye \, 9, /, -, *, etc.)
    if len(s) == 1:
        return KeyCode.from_char(s)

    # Teclas especiales por nombre
    special_map = {
        "escape": Key.esc,
        "enter": Key.enter,
        "space": Key.space,
        "backspace": Key.backspace,
        "tab": Key.tab,
        # Agrega más si las necesitas en el futuro
    }
    if s in special_map:
        return special_map[s]

    raise ValueError(f"Hotkey inválida: {s}")


def start_listener():
    """
    Inicia el listener global de teclas.
    Las hotkeys se parsean aquí (evita errores al importar el módulo).
    """
    # Parseamos las hotkeys dentro de la función para evitar errores al cargar el módulo
    toggle_hunt = parse_hotkey(TOGGLE_ACTIVE_HUNT_KEY)
    toggle_boss = parse_hotkey(TOGGLE_ACTIVE_BOSS_KEY)

    def _on_key_press(k):
        if k == toggle_hunt:
            with state_lock:
                STATE["active_hunt"] = not STATE["active_hunt"]
                print(f"🎛️ HUNT MODE = {STATE['active_hunt']}")

        elif k == toggle_boss:
            with state_lock:
                STATE["active_boss"] = not STATE["active_boss"]
                print(f"🎛️ BOSS MODE = {STATE['active_boss']}")

    listener = keyboard.Listener(on_press=_on_key_press)
    listener.daemon = True
    listener.start()