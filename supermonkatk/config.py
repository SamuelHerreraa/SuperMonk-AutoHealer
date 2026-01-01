# config.py
import os

# =========================
# CONFIG EDITABLE
# =========================
HOTKEY_LOW  = "f9"                   # Builder normal
HOTKEY_HIGH = "f11"                 # Burst AoE hunt

HOTKEY_BOSS_PRI = "1"               # Numpad / → como carácter literal
HOTKEY_BOSS_HIGH = "2"           # Numpad - → como carácter literal
TOGGLE_ACTIVE_BOSS_KEY = "*"        # Numpad * → como carácter literal

TOGGLE_ACTIVE_HUNT_KEY = "\\"       # Modo hunt normal

PRESS_TIMES = 1
CYCLE_SECONDS = 0.5        # cada 500 ms (2 veces por segundo)
INTER_PRESS_DELAY = 0.0

THRESHOLD = 0.90

OBS_TITLE_SUBSTRING = "Windowed Projector (Source)"

ROI_LEFT_OFFSET = 80
ROI_TOP_OFFSET = 80
ROI_WIDTH = 980
ROI_HEIGHT = 320

# ROI fija para boss image (relativa a OBS client)
BOSS_ROI_X1 = 1456
BOSS_ROI_Y1 = 699
BOSS_ROI_X2 = 1497
BOSS_ROI_Y2 = 737
BOSS_IMG_NAME = "exorigranpug.png"

THRESHOLD = 0.88  # Más estable que 0.90

TIBIA_TITLE_PREFIX = "Tibia -"
TIBIA_TITLE_SUBSTRING = "Tibia -"

HUNT_GIF_NAME = "hunt.gif"
BOSS_GIF_NAME = "boss.gif"

# Default (si no existe json)
HUNT_OVERLAY_X = 100
HUNT_OVERLAY_Y = 100
HUNT_OVERLAY_SCALE = 1.0

BOSS_OVERLAY_X = 200  # Posición inicial diferente para no solaparse
BOSS_OVERLAY_Y = 100
BOSS_OVERLAY_SCALE = 1.0

ROOT = os.path.dirname(__file__)
IMGS_DIR = os.path.join(ROOT, "img")
COORDS_PATH = os.path.join(IMGS_DIR, "coords_sereno.json")

# aquí se guarda la posición de los overlays
HUNT_POS_PATH = os.path.join(IMGS_DIR, "hunt_overlay_pos.json")
BOSS_POS_PATH = os.path.join(IMGS_DIR, "boss_overlay_pos.json")