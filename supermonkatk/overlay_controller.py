import os
import time
import threading

from overlay_hunt import HuntGifOverlay, is_foreground_title_contains
from config import (
    IMGS_DIR, HUNT_GIF_NAME,
    HUNT_OVERLAY_X, HUNT_OVERLAY_Y, HUNT_OVERLAY_SCALE,
    HUNT_POS_PATH, TIBIA_TITLE_PREFIX
)
from states import STATE, state_lock


def start_hunt_overlay():
    gif_path = os.path.join(IMGS_DIR, HUNT_GIF_NAME)
    if not os.path.exists(gif_path):
        print(f"⚠️ No existe {gif_path} (hunt.gif). Overlay deshabilitado.")
        return None

    overlay = HuntGifOverlay(
        gif_path=gif_path,
        x=HUNT_OVERLAY_X,
        y=HUNT_OVERLAY_Y,
        scale=HUNT_OVERLAY_SCALE,
        save_path=HUNT_POS_PATH,
    )
    overlay.start()

    def loop():
        last_visible = None
        last_color = None

        while True:
            with state_lock:
                active = STATE["active"]

            tibia_fg = is_foreground_title_contains(TIBIA_TITLE_PREFIX)

            # Overlay visible SOLO cuando Tibia está al frente (aunque ACTIVE sea False)
            should_be_visible = bool(tibia_fg)
            if should_be_visible != last_visible:
                if should_be_visible:
                    overlay.show()
                else:
                    overlay.hide()
                last_visible = should_be_visible

            # OFF rojo, ON verde gamer chillante
            color = "#39FF14" if active else "red"
            if color != last_color:
                overlay.set_border_color(color)
                last_color = color

            time.sleep(0.12)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return overlay
