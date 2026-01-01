# overlay_controller.py
import os
import time
import threading
from overlay_heal import HealGifOverlay
from states import STATE, state_lock

def is_foreground_title_contains(substring: str) -> bool:
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or ""
        return substring.lower() in title.lower()
    except Exception:
        return False

def start_heal_overlay(tibia_prefix: str):
    img_dir = os.path.join(os.path.dirname(__file__), "img")
    gif_path = os.path.join(img_dir, "heal.gif")
    pos_path = os.path.join(img_dir, "heal_overlay_pos.json")

    if not os.path.exists(gif_path):
        print(f"⚠️ No existe {gif_path}. Overlay deshabilitado.")
        return None

    def on_click_toggle():
        with state_lock:
            STATE["active"] = not STATE["active"]
            print(f"🎛️ HEALER ACTIVE = {STATE['active']} (click en overlay)")

    overlay = HealGifOverlay(
        gif_path=gif_path,
        x=100, y=100,
        scale=1.0,
        save_path=pos_path,
        on_toggle=on_click_toggle
    )
    overlay.start()

    def loop():
        last_visible = None
        last_active = None
        while True:
            with state_lock:
                active = STATE["active"]

            tibia_fg = is_foreground_title_contains(tibia_prefix)

            # Visible solo cuando Tibia está al frente
            should_visible = tibia_fg
            if should_visible != last_visible:
                if should_visible:
                    overlay.show()
                else:
                    overlay.hide()
                last_visible = should_visible

            # Color borde
            overlay.set_active(active)
            last_active = active

            time.sleep(0.12)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return overlay