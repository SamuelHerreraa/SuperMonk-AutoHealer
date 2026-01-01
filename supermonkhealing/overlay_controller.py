# overlay_controller.py
import os
import time
import threading
import win32gui
from overlay_heal import HealGifOverlay
from states import STATE, state_lock


def is_tibia_foreground(prefix: str = "Tibia -") -> bool:
    """
    Devuelve True solo si la ventana en primer plano tiene el prefijo 'Tibia -'
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return False
        title = win32gui.GetWindowText(hwnd)
        return title.startswith(prefix)
    except Exception:
        return False


def start_heal_overlay():
    """
    Inicia el overlay y devuelve el objeto overlay + la función para chequear si Tibia está al frente.
    Ya no necesita parámetro, usa prefijo fijo "Tibia -"
    """
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
        x=100,
        y=100,
        scale=1.0,
        save_path=pos_path,
        on_toggle=on_click_toggle
    )
    overlay.start()

    def control_loop():
        last_visible = None
        last_active = None
        while True:
            with state_lock:
                active = STATE["active"]

            tibia_in_front = is_tibia_foreground()

            # === VISIBILIDAD DEL OVERLAY ===
            if tibia_in_front != last_visible:
                if tibia_in_front:
                    overlay.show()
                else:
                    overlay.hide()
                last_visible = tibia_in_front

            # === COLOR DEL BORDE ===
            if active != last_active:
                overlay.set_active(active)
                last_active = active

            time.sleep(0.12)

    thread = threading.Thread(target=control_loop, daemon=True)
    thread.start()

    return overlay, is_tibia_foreground  # Devuelve también la función para usarla en main.py