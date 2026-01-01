import os
import time
import json
import cv2
import numpy as np
from PIL import Image
import win32gui
import win32ui
import win32con
import win32api
import keyboard
import ctypes
from ctypes import c_ulong, c_ulonglong, sizeof, c_void_p

# ====================== ENVÍO SEGURO DE TECLAS DE NAVEGACIÓN ======================
ULONG_PTR = c_ulonglong if sizeof(c_void_p) == 8 else c_ulong

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', ctypes.c_ushort),
        ('wScan', ctypes.c_ushort),
        ('dwFlags', ctypes.c_ulong),
        ('time', ctypes.c_ulong),
        ('dwExtraInfo', ULONG_PTR),
    ]

class INPUT_I(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_ulong), ('ii', INPUT_I)]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

NAV_SCAN = {
    "end": 0x4F,
    "home": 0x47,
    "pgup": 0x49,
    "pgdn": 0x51,
    "insert": 0x52,
    "delete": 0x53,
}

FKEY_VK_MAP = {
    "f13": 0x7C,
    "f14": 0x7D,
    "f15": 0x7E,
    "f16": 0x7F,
    "f17": 0x80,
    "f18": 0x81,
    "f19": 0x82,
    "f20": 0x83,
    "f21": 0x84,
    "f22": 0x85,
    "f23": 0x86,
    "f24": 0x87,
}


def send_nav_key(key_name: str):
    """Envía teclas de navegación reales (bloque Ins/Home/PgUp/PgDn/End/Del) usando keybd_event con map code correcto"""
    key = key_name.lower()
    
    # Map codes específicos para el bloque de navegación (no numpad)
    nav_map = {
        "end": 0xE04F,
        "home": 0xE047,
        "pgup": 0xE049,
        "pgdn": 0xE051,
        "insert": 0xE052,
        "delete": 0xE053,
    }
    
    map_code = nav_map.get(key)
    if map_code is None:
        return False

    try:
        # DOWN
        win32api.keybd_event(0, map_code, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY, 0)
        time.sleep(0.05)
        # UP
        win32api.keybd_event(0, map_code, KEYEVENTF_SCANCODE | KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"Error enviando {key_name}: {e}")
        return False

def send_key(key: str):
    key = key.lower().strip()

    # 1️⃣ Teclas de navegación (End, Home, etc.)
    if send_nav_key(key):
        return

    # 2️⃣ F13–F24 (incluye F17)
    if key in FKEY_VK_MAP:
        vk = FKEY_VK_MAP[key]
        try:
            # DOWN
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.03)
            # UP
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception as e:
            print(f"❌ Error enviando {key}: {e}")
        return

    # 3️⃣ Teclas normales (f1–f12, letras, números, etc.)
    try:
        keyboard.press_and_release(key)
    except Exception as e:
        print(f"❌ Error keyboard {key}: {e}")


# ============================= ARCHIVOS =============================
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "ui_state.json")

HEART_TEMPLATE = os.path.join(ROOT, "heart.png")
MANA_TEMPLATE = os.path.join(ROOT, "mana.png")

# ============================= CARGA CONFIG =============================
def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"No existe {CONFIG_PATH}. Crea el config.json junto al script.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CFG = load_config()

# Ordenar rules por hp_percent ASC (más crítico primero)
HP_CFG = CFG["hp"]
HP_CFG["rules"] = sorted(HP_CFG.get("rules", []), key=lambda r: r["hp_percent"])

OBS_TITLE_PREFIX = CFG.get("obs_title_prefix", "Windowed Projector (Source)")
TIBIA_TITLE_PREFIX = CFG.get("tibia_title_prefix", "Tibia -")
THRESHOLD = float(CFG.get("template_threshold", 0.92))

OFFSET_TO_X0 = int(CFG.get("offset_to_x0", 9))
BAR_LENGTH_PX = int(CFG.get("bar_length_px", 90))

POLL_SECONDS = float(CFG.get("poll_seconds", 0.12))

SPELLS_GLOBAL_COOLDOWN = float(CFG.get("spells_global_cooldown_sec", 0.6))

MANA_CFG = CFG.get("mana_potion", {})
STRONG_HP_POTION_CFG = CFG.get("strong_hp_potion", {"enabled": False})
LIGHT_HP_POTION_CFG = CFG.get("light_hp_potion", {"enabled": False})
AUTO_RING_CFG = CFG.get("auto_ring", {"enabled": False})

# ============================= ESTADO EN MEMORIA =============================
state = {
    "hp": {"center_rel": None, "x0_rel": None, "y_bar": None},
    "mana": {"center_rel": None, "x0_rel": None, "y_bar": None}
}

_last_spell_ts = 0.0
_last_potion_ts = 0.0
_last_strong_hp_ts = 0.0
_last_light_hp_ts = 0.0
_last_sent_rule = {r["name"]: 0.0 for r in HP_CFG.get("rules", [])}

_energy_ring_equipped = False
_last_ring_action_ts = 0.0


RING_SLOT_X = 1767
RING_SLOT_Y = 224
ENERGY_RING_COLOR = (145, 255, 248)
RING_COLOR_TOLERANCE = 20

# ============================= UTILIDADES TIMESTAMP =============================
def get_timestamp_millis():
    now = time.time()
    seconds = int(now)
    millis = int((now - seconds) * 1000)
    return time.strftime('%H:%M:%S', time.localtime(seconds)) + f'.{millis:03d}'

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

# ============================= JSON STATE =============================
def load_state():
    if not os.path.exists(STATE_PATH):
        return
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
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
            return False

    return True

# ============================= PIXEL / COLOR =============================
def get_pixel_color_at_rel(client_rgb_img, rel_x, rel_y):
    h, w = client_rgb_img.shape[:2]
    if 0 <= rel_x < w and 0 <= rel_y < h:
        return tuple(map(int, client_rgb_img[rel_y, rel_x]))
    return None

def color_is_different(color_rgb, expected_rgb, tolerance):
    if color_rgb is None:
        return True
    return any(abs(color_rgb[i] - expected_rgb[i]) > tolerance for i in range(3))

def is_energy_ring_equipped(client_rgb_img):
    color = get_pixel_color_at_rel(client_rgb_img, RING_SLOT_X, RING_SLOT_Y)
    return not color_is_different(color, ENERGY_RING_COLOR, RING_COLOR_TOLERANCE)

def get_current_percent(kind: str, client_rgb):
    cfg = HP_CFG if kind == "hp" else MANA_CFG
    x0 = state[kind]["x0_rel"]
    y = state[kind]["y_bar"]
    if x0 is None or y is None:
        return None

    expected = tuple(cfg["expected_color_rgb"])
    tol = int(cfg.get("color_tolerance", 20))

    filled_length = 0
    for dx in range(BAR_LENGTH_PX):
        x = x0 + dx
        color = get_pixel_color_at_rel(client_rgb, x, y)
        if color and not color_is_different(color, expected, tol):
            filled_length = dx + 1
        else:
            break

    pct = (filled_length / BAR_LENGTH_PX) * 100.0
    return max(0.0, min(100.0, pct))

def get_current_hp_percent(client_rgb):
    return get_current_percent("hp", client_rgb)

def get_current_mana_percent(client_rgb):
    if not MANA_CFG.get("enabled", True):
        return None
    return get_current_percent("mana", client_rgb)

def is_mana_below_percent(client_rgb_img, pct: float) -> bool:
    current_mana = get_current_mana_percent(client_rgb_img)
    if current_mana is None:
        return False
    return current_mana < pct

# ============================= EVALUADORES =============================
def try_cast_best_hp_spell(client_rgb):
    global _last_spell_ts
    now = time.time()
    if (now - _last_spell_ts) < SPELLS_GLOBAL_COOLDOWN:
        return False

    current_hp = get_current_hp_percent(client_rgb)
    if current_hp is None:
        return False

    for rule in HP_CFG.get("rules", []):
        name = rule["name"]
        hp_percent = float(rule["hp_percent"])
        hotkey = str(rule["hotkey"])
        per_rule_cd = float(rule.get("cooldown", 0.0))

        if current_hp < hp_percent:
            if (now - _last_sent_rule.get(name, 0.0)) >= per_rule_cd:
                send_key(hotkey)
                _last_spell_ts = now
                _last_sent_rule[name] = now
                ts_str = get_timestamp_millis()
                print(f"[{ts_str}] 🩸 {name} HP={current_hp:.0f}% <{hp_percent:.0f}% → {hotkey}")
                return True  # Solo uno por loop
    return False

def try_use_hp_potions(client_rgb):
    global _last_strong_hp_ts, _last_light_hp_ts
    now = time.time()

    current_hp = get_current_hp_percent(client_rgb)
    if current_hp is None:
        return False

    used_potion = False

    if STRONG_HP_POTION_CFG.get("enabled", False):
        pct = float(STRONG_HP_POTION_CFG.get("target_hp_percent", 75))
        cd = float(STRONG_HP_POTION_CFG.get("potion_cooldown_sec", 1.0))
        hotkey = str(STRONG_HP_POTION_CFG.get("hotkey", "f5"))

        if (now - _last_strong_hp_ts) >= cd and current_hp < pct:
            send_key(hotkey)
            _last_strong_hp_ts = now
            ts_str = get_timestamp_millis()
            print(f"[{ts_str}] ❤️ STRONG HP POTION HP={current_hp:.0f}% <{pct:.0f}% → {hotkey}")
            used_potion = True

    if not used_potion and LIGHT_HP_POTION_CFG.get("enabled", False):
        pct = float(LIGHT_HP_POTION_CFG.get("target_hp_percent", 80))
        cd = float(LIGHT_HP_POTION_CFG.get("potion_cooldown_sec", 1.0))
        hotkey = str(LIGHT_HP_POTION_CFG.get("hotkey", "f4"))

        if (now - _last_light_hp_ts) >= cd and current_hp < pct:
            send_key(hotkey)
            _last_light_hp_ts = now
            ts_str = get_timestamp_millis()
            print(f"[{ts_str}] 💚 LIGHT HP POTION HP={current_hp:.0f}% <{pct:.0f}% → {hotkey}")
            used_potion = True

    return used_potion

def try_use_mana_potion(client_rgb):
    global _last_potion_ts
    if not MANA_CFG.get("enabled", True):
        return False

    now = time.time()
    potion_cd = float(MANA_CFG.get("potion_cooldown_sec", 1.0))
    if (now - _last_potion_ts) < potion_cd:
        return False

    current_mana = get_current_mana_percent(client_rgb)
    if current_mana is None:
        return False

    target_pct = float(MANA_CFG.get("target_mana_percent", 80))
    hotkey = str(MANA_CFG.get("hotkey", "f6"))

    if current_mana < target_pct:
        send_key(hotkey)
        _last_potion_ts = now
        ts_str = get_timestamp_millis()
        print(f"[{ts_str}] 🧪 MANA={current_mana:.0f}% <{target_pct:.0f}% → {hotkey}")
        return True

    return False

def try_auto_energy_ring(client_rgb):
    global _energy_ring_equipped, _last_ring_action_ts

    if not AUTO_RING_CFG.get("enabled", False):
        return False

    now = time.time()
    cooldown = float(AUTO_RING_CFG.get("cooldown_sec", 2.0))
    if (now - _last_ring_action_ts) < cooldown:
        return False

    current_hp = get_current_hp_percent(client_rgb)
    if current_hp is None:
        return False

    equip_below = float(AUTO_RING_CFG.get("equip_below_percent", 50))
    unequip_above = float(AUTO_RING_CFG.get("unequip_above_percent", 80))
    equip_hotkey = str(AUTO_RING_CFG.get("equip_hotkey", "f17"))
    unequip_hotkey = str(AUTO_RING_CFG.get("unequip_hotkey", "end"))

    min_mana_pct = float(AUTO_RING_CFG.get("min_mana_percent_to_equip", 0))
    lock_ms = float(AUTO_RING_CFG.get("lock_inputs_ms_after_ring", 120))
    lock_sec = lock_ms / 1000.0

    current_energy_ring = is_energy_ring_equipped(client_rgb)

    current_mana = get_current_mana_percent(client_rgb) if min_mana_pct > 0 else 100.0
    mana_too_low = (min_mana_pct > 0) and (current_mana is not None) and (current_mana < min_mana_pct)

    if current_hp <= equip_below and not current_energy_ring:
        if mana_too_low:
            return False

        send_key(equip_hotkey)
        _energy_ring_equipped = True
        _last_ring_action_ts = now
        time.sleep(0.015)  # Micro-delay para registro
        ts_str = get_timestamp_millis()
        print(f"[{ts_str}] ⚡ HP={current_hp:.0f}% ≤{equip_below}% → EQUIPANDO ENERGY RING ({equip_hotkey})")
        return "equipped"

    elif current_hp >= unequip_above and current_energy_ring:
        send_key(unequip_hotkey)
        _energy_ring_equipped = False
        _last_ring_action_ts = now
        time.sleep(0.015)  # Micro-delay
        ts_str = get_timestamp_millis()
        print(f"[{ts_str}] ⚡ HP={current_hp:.0f}% ≥{unequip_above}% → DESEQUIPANDO ENERGY RING ({unequip_hotkey})")
        return "unequipped"

    return False

# ============================= LOOP PRINCIPAL =============================
def loop_once():
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        return

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)
    client_rgb = cv2.cvtColor(client_bgr, cv2.COLOR_BGR2RGB)

    # 1️⃣ Ring SIEMPRE primero
    ring_result = try_auto_energy_ring(client_rgb)

    # 2️⃣ Si ring action: sleep breve para evitar choques, luego potions (no spells)
    if ring_result:
        time.sleep(0.1)  # Delay para priorizar ring y evitar choques
        hp_potion_used = try_use_hp_potions(client_rgb)
        if not hp_potion_used:
            try_use_mana_potion(client_rgb)
        return

    # 3️⃣ Normal flow: spells, luego potions
    try_cast_best_hp_spell(client_rgb)
    hp_potion_used = try_use_hp_potions(client_rgb)
    if not hp_potion_used:
        try_use_mana_potion(client_rgb)


if __name__ == "__main__":
    print("=== SuperMonk Auto Healer + Potions + Auto Energy Ring ===")
    print(f"OBS prefix: {OBS_TITLE_PREFIX}")
    print(f"Tibia prefix: {TIBIA_TITLE_PREFIX}")
    print(f"Polling: {POLL_SECONDS}s")

    if not ensure_located():
        print("❌ No pude localizar heart.png y/o mana.png. Verifica templates y el projector.")
        raise SystemExit(1)

    print("✅ Listo. Ring se desequipa con tecla configurable (por defecto: end)")
    print("   → Funciona solo cuando Tibia está en primer plano.\n")

    try:
        while True:
            if tibia_is_foreground():
                loop_once()
            else:
                time.sleep(0.2)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nDetenido por el usuario. ¡Buena caza!")