# overlay_controller.py
import os
import time
import threading

from overlay_hunt import GifOverlay, is_foreground_title_contains  # Usamos la clase base
from config import (
    IMGS_DIR, HUNT_GIF_NAME, BOSS_GIF_NAME,
    HUNT_OVERLAY_X, HUNT_OVERLAY_Y, HUNT_OVERLAY_SCALE,
    BOSS_OVERLAY_X, BOSS_OVERLAY_Y, BOSS_OVERLAY_SCALE,
    HUNT_POS_PATH, BOSS_POS_PATH, TIBIA_TITLE_PREFIX
)
from states import STATE, state_lock


def start_overlays():
    # Hunt overlay
    hunt_gif_path = os.path.join(IMGS_DIR, HUNT_GIF_NAME)
    hunt_overlay = None
    if os.path.exists(hunt_gif_path):
        hunt_overlay = GifOverlay(
            gif_path=hunt_gif_path,
            x=HUNT_OVERLAY_X,
            y=HUNT_OVERLAY_Y,
            scale=HUNT_OVERLAY_SCALE,
            save_path=HUNT_POS_PATH,
        )
        hunt_overlay.start()
    else:
        print(f"⚠️ No existe {hunt_gif_path} (hunt.gif). Hunt overlay deshabilitado.")

    # Boss overlay
    boss_gif_path = os.path.join(IMGS_DIR, BOSS_GIF_NAME)
    boss_overlay = None
    if os.path.exists(boss_gif_path):
        boss_overlay = GifOverlay(
            gif_path=boss_gif_path,
            x=BOSS_OVERLAY_X,
            y=BOSS_OVERLAY_Y,
            scale=BOSS_OVERLAY_SCALE,
            save_path=BOSS_POS_PATH,
        )
        boss_overlay.start()
    else:
        print(f"⚠️ No existe {boss_gif_path} (boss.gif). Boss overlay deshabilitado.")

    def loop():
        last_visible = None
        last_hunt_color = None
        last_boss_color = None

        while True:
            with state_lock:
                active_hunt = STATE["active_hunt"]
                active_boss = STATE["active_boss"]

            tibia_fg = is_foreground_title_contains(TIBIA_TITLE_PREFIX)

            # Overlays visibles SOLO cuando Tibia está al frente
            should_be_visible = bool(tibia_fg)
            if should_be_visible != last_visible:
                if hunt_overlay:
                    if should_be_visible:
                        hunt_overlay.show()
                    else:
                        hunt_overlay.hide()
                if boss_overlay:
                    if should_be_visible:
                        boss_overlay.show()
                    else:
                        boss_overlay.hide()
                last_visible = should_be_visible

            # Colores: verde si activo, rojo si inactivo
            hunt_color = "#39FF14" if active_hunt else "red"
            if hunt_color != last_hunt_color and hunt_overlay:
                hunt_overlay.set_border_color(hunt_color)
                last_hunt_color = hunt_color

            boss_color = "#39FF14" if active_boss else "red"
            if boss_color != last_boss_color and boss_overlay:
                boss_overlay.set_border_color(boss_color)
                last_boss_color = boss_color

            time.sleep(0.12)

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    return hunt_overlay, boss_overlay