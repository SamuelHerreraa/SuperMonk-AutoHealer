import os

# =========================
# CONFIG EDITABLE (OPCIÓN B)
# =========================
HOTKEY_LOW  = "9"     # harmony 0..4
HOTKEY_HIGH = "0"     # harmony 5

TOGGLE_ACTIVE_KEY = "\\"   # activar / desactivar casteo

PRESS_TIMES = 1
CYCLE_SECONDS = 0.5        # cada 500 ms (2 veces por segundo)
INTER_PRESS_DELAY = 0.0

THRESHOLD = 0.90

OBS_TITLE_SUBSTRING = "Windowed Projector (Source)"

ROI_LEFT_OFFSET = 80
ROI_TOP_OFFSET = 80
ROI_WIDTH = 980
ROI_HEIGHT = 320

TIBIA_TITLE_PREFIX = "Tibia -"
TIBIA_TITLE_SUBSTRING = "Tibia -"

HUNT_GIF_NAME = "hunt.gif"

# Default (si no existe json)
HUNT_OVERLAY_X = 100
HUNT_OVERLAY_Y = 100
HUNT_OVERLAY_SCALE = 1.0

ROOT = os.path.dirname(__file__)
IMGS_DIR = os.path.join(ROOT, "img")
COORDS_PATH = os.path.join(IMGS_DIR, "coords_sereno.json")

# aquí se guarda la posición del overlay
HUNT_POS_PATH = os.path.join(IMGS_DIR, "hunt_overlay_pos.json")
