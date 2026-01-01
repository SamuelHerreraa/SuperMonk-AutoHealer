# main.py
from hotkeys import start_listener
from overlay_controller import start_overlays
from caster_engine import set_dpi_awareness, run_cast_loop
from config import TOGGLE_ACTIVE_HUNT_KEY, TOGGLE_ACTIVE_BOSS_KEY


def main():
    set_dpi_awareness()
    start_listener()
    start_overlays()

    print("✅ Script listo")
    print(f"{TOGGLE_ACTIVE_HUNT_KEY} = activar / desactivar hunt mode")
    print(f"{TOGGLE_ACTIVE_BOSS_KEY} = activar / desactivar boss mode\n")

    run_cast_loop()


if __name__ == "__main__":
    main()