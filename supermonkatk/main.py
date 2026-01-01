from hotkeys import start_listener
from overlay_controller import start_hunt_overlay
from caster_engine import set_dpi_awareness, run_cast_loop
from config import TOGGLE_ACTIVE_KEY


def main():
    set_dpi_awareness()
    start_listener()
    start_hunt_overlay()

    print("✅ Script listo")
    print(f"{TOGGLE_ACTIVE_KEY} = activar / desactivar casteo\n")

    run_cast_loop()


if __name__ == "__main__":
    main()
