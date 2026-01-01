import os
import time
import json
import cv2
import numpy as np
from PIL import Image
import win32gui
import win32ui
import win32con
import keyboard  # pip install keyboard

# ============================= ARCHIVOS =============================
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "ui_state.json")  # coords guardadas aquí (1 solo json)

HEART_TEMPLATE = os.path.join(ROOT, "heart.png")
MANA_TEMPLATE = os.path.join(ROOT, "mana.png")

# ============================= CARGA CONFIG =============================
def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"No existe {CONFIG_PATH}. Crea el config.json junto al script.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CFG = load_config()

OBS_TITLE_PREFIX = CFG.get("obs_title_prefix", "Windowed Projector (Source)")
TIBIA_TITLE_PREFIX = CFG.get("tibia_title_prefix", "Tibia")
THRESHOLD = float(CFG.get("template_threshold", 0.92))

OFFSET_TO_X0 = int(CFG.get("offset_to_x0", 9))
BAR_LENGTH_PX = int(CFG.get("bar_length_px", 90))

POLL_SECONDS = float(CFG.get("poll_seconds", 0.12))

SPELLS_GLOBAL_COOLDOWN = float(CFG.get("spells_global_cooldown_sec", 0.6))  # 600ms
HP_CFG = CFG["hp"]
MANA_CFG = CFG.get("mana_potion", {})

# ============================= ESTADO EN MEMORIA =============================
state = {
    "hp": {
        "center_rel": None,  # (cx, cy)
        "x0_rel": None,
        "y_bar": None,
    },
    "mana": {
        "center_rel": None,
        "x0_rel": None,
        "y_bar": None,
    }
}

_last_spell_ts = 0.0
_last_potion_ts = 0.0
_last_sent_rule = {r["name"]: 0.0 for r in HP_CFG.get("rules", [])}

# ============================= UTILIDADES VENTANAS =============================
def find_window_by_prefix(prefix: str):
    found = None
    def cb(hwnd, _):
        nonlocal found
        if not found and win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if title.startswith(prefix):
                found = hwnd
    win32gui.EnumWindows(cb, None)
    return found

def get_foreground_title() -> str:
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetWindowText(hwnd) or ""

def tibia_is_foreground() -> bool:
    title = get_foreground_title()
    return title.startswith(TIBIA_TITLE_PREFIX) or (TIBIA_TITLE_PREFIX.lower() in title.lower())

# ============================= CAPTURA OBS =============================
def capture_window_image(hwnd) -> Image.Image:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w = max(1, right - left)
    h = max(1, bottom - top)

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bitmap)

    try:
        res = win32gui.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
        if res != 1:
            save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
    except:
        save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

    bmpinfo = bitmap.GetInfo()
    bmpstr = bitmap.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)

    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    return img

def get_client_offset_and_size(hwnd):
    window_rect = win32gui.GetWindowRect(hwnd)
    client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
    offset_x = client_origin[0] - window_rect[0]
    offset_y = client_origin[1] - window_rect[1]
    client_w = win32gui.GetClientRect(hwnd)[2]
    client_h = win32gui.GetClientRect(hwnd)[3]
    return offset_x, offset_y, client_w, client_h

def pil_to_cv(img_pil: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def crop_client_area(win_img_pil: Image.Image, hwnd) -> np.ndarray:
    offset_x, offset_y, client_w, client_h = get_client_offset_and_size(hwnd)
    win_cv = pil_to_cv(win_img_pil)
    h, w = win_cv.shape[:2]
    x1 = max(0, int(offset_x))
    y1 = max(0, int(offset_y))
    x2 = min(w, int(offset_x + client_w))
    y2 = min(h, int(offset_y + client_h))
    return win_cv[y1:y2, x1:x2]

# ============================= JSON (1 SOLO) =============================
def load_state():
    if not os.path.exists(STATE_PATH):
        return
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # esperamos data["hp"]["center_rel"] etc
        if isinstance(data, dict):
            for k in ("hp", "mana"):
                if k in data and isinstance(data[k], dict):
                    cr = data[k].get("center_rel")
                    if cr and "x" in cr and "y" in cr:
                        cx, cy = int(cr["x"]), int(cr["y"])
                        state[k]["center_rel"] = (cx, cy)
                        state[k]["x0_rel"] = cx + OFFSET_TO_X0
                        state[k]["y_bar"] = cy
    except Exception as e:
        print(f"⚠️ No pude leer {STATE_PATH}: {e}")

def save_state():
    payload = {"ts": time.time(), "hp": {}, "mana": {}}
    for k in ("hp", "mana"):
        c = state[k]["center_rel"]
        if c:
            payload[k]["center_rel"] = {"x": int(c[0]), "y": int(c[1])}
            payload[k]["found"] = True
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"⚠️ No pude guardar {STATE_PATH}: {e}")

# ============================= LOCATORS =============================
def locate_template_once(kind: str, template_path: str):
    """
    kind: "hp" o "mana"
    Busca el template en el client area del OBS projector y guarda center_rel.
    """
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print("❌ No se encontró ventana OBS projector.")
        return False

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)

    templ = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if templ is None:
        print(f"❌ No se pudo cargar template: {template_path}")
        return False

    res = cv2.matchTemplate(client_bgr, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < THRESHOLD:
        print(f"❌ No se detectó {os.path.basename(template_path)} (score {max_val:.3f} < {THRESHOLD})")
        return False

    th, tw = templ.shape[:2]
    cx = max_loc[0] + tw // 2
    cy = max_loc[1] + th // 2

    state[kind]["center_rel"] = (cx, cy)
    state[kind]["x0_rel"] = cx + OFFSET_TO_X0
    state[kind]["y_bar"] = cy

    print(f"✅ {kind.upper()} detectado: center_rel=({cx},{cy}) score={max_val:.3f}")
    print(f"   ↳ Barra {kind}: x0={state[kind]['x0_rel']}  y={state[kind]['y_bar']}")
    save_state()
    return True

def ensure_located():
    load_state()

    if not state["hp"]["center_rel"]:
        print("🔎 Buscando heart.png...")
        if not locate_template_once("hp", HEART_TEMPLATE):
            return False

    if MANA_CFG.get("enabled", True) and not state["mana"]["center_rel"]:
        print("🔎 Buscando mana.png...")
        if not locate_template_once("mana", MANA_TEMPLATE):
            # no es fatal si no quieres mana, pero si está enabled sí lo tratamos como necesario
            return False

    return True

# ============================= PIXEL / COLOR =============================
def get_pixel_color_at_rel(client_rgb_img, rel_x, rel_y):
    h, w = client_rgb_img.shape[:2]
    if 0 <= rel_x < w and 0 <= rel_y < h:
        return tuple(map(int, client_rgb_img[rel_y, rel_x]))
    return None

def color_is_different(color_rgb, expected_rgb, tolerance):
    return any(abs(color_rgb[i] - expected_rgb[i]) > tolerance for i in range(3))

# ============================= INPUT =============================
def send_key(key: str):
    keyboard.press_and_release(key)

# ============================= EVALUADORES =============================
def try_cast_best_hp_spell(client_rgb):
    """
    Retorna True si lanzó una spell de HP.
    Respeta:
      - prioridad por reglas
      - cooldown por regla (si lo usas)
      - cooldown global entre spells: SPELLS_GLOBAL_COOLDOWN
    """
    global _last_spell_ts

    now = time.time()

    # Cooldown global de spells (entre F1/F2/F3)
    if (now - _last_spell_ts) < SPELLS_GLOBAL_COOLDOWN:
        return False

    expected = tuple(HP_CFG["expected_color_rgb"])
    tol = int(HP_CFG.get("color_tolerance", 20))

    x0 = state["hp"]["x0_rel"]
    y = state["hp"]["y_bar"]
    if x0 is None or y is None:
        return False

    for rule in HP_CFG.get("rules", []):  # ya viene ordenado urgente -> leve
        name = rule["name"]
        hp_percent = float(rule["hp_percent"])
        hotkey = str(rule["hotkey"])
        per_rule_cd = float(rule.get("cooldown", 0.0))

        target_x = int(x0 + (BAR_LENGTH_PX * (hp_percent / 100.0)))
        color = get_pixel_color_at_rel(client_rgb, target_x, y)
        if color is None:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ HP fuera de rango: {name} x={target_x} y={y}")
            return False

        diff = color_is_different(color, expected, tol)
        if diff:
            # cooldown por regla (opcional)
            if (now - _last_sent_rule.get(name, 0.0)) < per_rule_cd:
                return False

            send_key(hotkey)
            _last_spell_ts = now
            _last_sent_rule[name] = now
            print(f"[{time.strftime('%H:%M:%S')}] 🩸 {name} HP<{hp_percent:.0f}% → {hotkey} (spellCD {SPELLS_GLOBAL_COOLDOWN}s)")
            return True

    return False

def try_use_mana_potion(client_rgb):
    """
    Potion NO comparte cooldown con spells.
    Solo respeta potion_cooldown_sec contra sí misma.
    """
    global _last_potion_ts

    if not MANA_CFG.get("enabled", True):
        return False

    now = time.time()
    potion_cd = float(MANA_CFG.get("potion_cooldown_sec", 1.0))

    if (now - _last_potion_ts) < potion_cd:
        return False

    expected = tuple(MANA_CFG["expected_color_rgb"])
    tol = int(MANA_CFG.get("color_tolerance", 20))
    target_pct = float(MANA_CFG.get("target_mana_percent", 80))
    hotkey = str(MANA_CFG.get("hotkey", "f6"))

    x0 = state["mana"]["x0_rel"]
    y = state["mana"]["y_bar"]
    if x0 is None or y is None:
        return False

    target_x = int(x0 + (BAR_LENGTH_PX * (target_pct / 100.0)))
    color = get_pixel_color_at_rel(client_rgb, target_x, y)
    if color is None:
        print(f"[{time.strftime('%H:%M:%S')}] ⚠️ MANA fuera de rango: x={target_x} y={y}")
        return False

    diff = color_is_different(color, expected, tol)
    if diff:
        send_key(hotkey)
        _last_potion_ts = now
        print(f"[{time.strftime('%H:%M:%S')}] 🧪 MANA<{target_pct:.0f}% → POTION {hotkey} (potionCD {potion_cd}s)")
        return True

    return False

# ============================= LOOP PRINCIPAL =============================
def loop_once():
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print("❌ ERROR: No se encontró ventana OBS.")
        return

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)
    client_rgb = cv2.cvtColor(client_bgr, cv2.COLOR_BGR2RGB)

    # 1) HP primero (máximo 1 spell por ciclo)
    casted = try_cast_best_hp_spell(client_rgb)

    # 2) Luego mana potion (puede salir aunque haya salido spell)
    potted = try_use_mana_potion(client_rgb)

    # (Opcional) micro-pausa si te preocupa que Windows “pierda” una tecla por pegadas
    # if casted and potted:
    #     time.sleep(0.01)

if __name__ == "__main__":
    print("=== SuperMonk HP + Mana Potion (1 script / 1 JSON) ===")
    print(f"OBS prefix: {OBS_TITLE_PREFIX}")
    print(f"Tibia prefix: {TIBIA_TITLE_PREFIX}")
    print(f"Polling: {POLL_SECONDS}s | Spells global CD: {SPELLS_GLOBAL_COOLDOWN}s | Potion CD: {MANA_CFG.get('potion_cooldown_sec', 1.0)}s")

    if not ensure_located():
        print("❌ No pude localizar heart.png y/o mana.png. Verifica templates y el projector.")
        raise SystemExit(1)

    print("✅ Listo. Solo enviará teclas si Tibia está en foreground.\n")

    try:
        while True:
            if tibia_is_foreground():
                loop_once()
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.")
