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

# ====================== ENVÍO DE TECLAS ======================
def send_key_f17():
    win32api.keybd_event(0x80, 0, 0, 0)  # VK_F17 = 0x80
    time.sleep(0.03)
    win32api.keybd_event(0x80, 0, win32con.KEYEVENTF_KEYUP, 0)

def send_key_end():
    win32api.keybd_event(0, 0xE04F, win32con.KEYEVENTF_SCANCODE | win32con.KEYEVENTF_EXTENDEDKEY, 0)
    time.sleep(0.05)
    win32api.keybd_event(0, 0xE04F, win32con.KEYEVENTF_SCANCODE | win32con.KEYEVENTF_EXTENDEDKEY | win32con.KEYEVENTF_KEYUP, 0)

def send_spell_key(hotkey):
    if hotkey.startswith("f"):
        if hotkey == "f17":
            send_key_f17()
            return
        # f1 a f12 normales
        vk = getattr(win32con, f'VK_{hotkey.upper()}')
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    else:
        # Letras o números
        win32api.keybd_event(ord(hotkey.upper()), 0, 0, 0)
        time.sleep(0.03)
        win32api.keybd_event(ord(hotkey.upper()), 0, win32con.KEYEVENTF_KEYUP, 0)

# ====================== CONFIG Y ARCHIVOS ======================
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config_ring.json")
HEART_TEMPLATE = os.path.join(ROOT, "heart.png")
MANA_TEMPLATE = os.path.join(ROOT, "mana.png")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"No existe {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CFG = load_config()

# General
OBS_TITLE_PREFIX = CFG["obs_title_prefix"]
THRESHOLD = CFG["template_threshold"]
OFFSET_TO_X0 = CFG["offset_to_x0"]
BAR_LENGTH_PX = CFG["bar_length_px"]
POLL_SECONDS = CFG["poll_seconds"]

# Ring
EQUIP_BELOW = CFG.get("equip_below_percent", 60)
UNEQUIP_ABOVE = CFG.get("unequip_above_percent", 85)
RING_COOLDOWN = CFG.get("cooldown_sec", 0.6)
MIN_MANA_TO_EQUIP = CFG.get("min_mana_percent_to_equip", 30)

# Spells
SPELLS_CFG = CFG.get("spells", {})
SPELLS_ENABLED = SPELLS_CFG.get("enabled", True)
SPELLS_GLOBAL_CD = SPELLS_CFG.get("global_cooldown_sec", 0.5)

HARD_CFG = SPELLS_CFG.get("hard_healing", {})
MID_CFG = SPELLS_CFG.get("mid_healing", {})
LIGHT_CFG = SPELLS_CFG.get("light_healing", {})

# Potions (AÑADIDO: esto faltaba)
POTIONS_CFG = CFG.get("potions", {})
POTIONS_ENABLED = POTIONS_CFG.get("enabled", True)

HARD_POTION_CFG = POTIONS_CFG.get("hard_potion", {})
MID_POTION_CFG = POTIONS_CFG.get("mid_potion", {})
MANA_POTION_CFG = POTIONS_CFG.get("mana_potion", {})

# Estado
_last_ring_ts = 0.0
_last_spell_ts = 0.0
_last_hard_ts = 0.0
_last_mid_ts = 0.0
_last_light_ts = 0.0

hp_x0 = hp_y = mana_x0 = mana_y = None

RING_SLOT_X = 1767
RING_SLOT_Y = 224
ENERGY_RING_COLOR = (145, 255, 248)
RING_TOLERANCE = 20

# ====================== DETECCIÓN ======================
def find_obs_window():
    found = None
    def enum_cb(hwnd, _):
        nonlocal found
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.startswith(OBS_TITLE_PREFIX):
                found = hwnd
    win32gui.EnumWindows(enum_cb, None)
    return found

def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w = max(1, right - left)
    h = max(1, bottom - top)
    dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bitmap)
    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
    bmpinfo = bitmap.GetInfo()
    bmpstr = bitmap.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)
    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, dc)
    return img

def crop_client_area(img_pil, hwnd):
    window_rect = win32gui.GetWindowRect(hwnd)
    client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
    offset_x = client_origin[0] - window_rect[0]
    offset_y = client_origin[1] - window_rect[1]
    client_w, client_h = win32gui.GetClientRect(hwnd)[2], win32gui.GetClientRect(hwnd)[3]
    img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    h, w = img_cv.shape[:2]
    return img_cv[max(0, int(offset_y)):min(h, int(offset_y + client_h)),
                  max(0, int(offset_x)):min(w, int(offset_x + client_w))]

def locate_bars():
    global hp_x0, hp_y, mana_x0, mana_y
    hwnd = find_obs_window()
    if not hwnd: return False
    img = capture_window(hwnd)
    client = crop_client_area(img, hwnd)

    # Heart (HP)
    templ = cv2.imread(HEART_TEMPLATE, cv2.IMREAD_COLOR)
    if templ is None: return False
    res = cv2.matchTemplate(client, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < THRESHOLD: return False
    th, tw = templ.shape[:2]
    hp_x0 = max_loc[0] + tw // 2 + OFFSET_TO_X0
    hp_y = max_loc[1] + th // 2

    # Mana (opcional)
    mana_x0 = mana_y = None
    if MIN_MANA_TO_EQUIP > 0 and os.path.exists(MANA_TEMPLATE):
        templ_mana = cv2.imread(MANA_TEMPLATE, cv2.IMREAD_COLOR)
        if templ_mana is not None:
            res_m = cv2.matchTemplate(client, templ_mana, cv2.TM_CCOEFF_NORMED)
            _, mv_m, _, ml_m = cv2.minMaxLoc(res_m)
            if mv_m >= THRESHOLD:
                tmh, tmw = templ_mana.shape[:2]
                mana_x0 = ml_m[0] + tmw // 2 + OFFSET_TO_X0
                mana_y = ml_m[1] + tmh // 2

    print(f"✅ HP barra: x0={hp_x0}, y={hp_y}")
    if mana_x0: print(f"✅ Mana barra: x0={mana_x0}, y={mana_y}")
    return True

def get_pixel(client_rgb, x, y):
    h, w = client_rgb.shape[:2]
    if 0 <= x < w and 0 <= y < h:
        return client_rgb[y, x]
    return None

def is_ring_equipped(client_rgb):
    h, w = client_rgb.shape[:2]
    if not (0 <= RING_SLOT_X < w and 0 <= RING_SLOT_Y < h):
        return False
    color = client_rgb[RING_SLOT_Y, RING_SLOT_X]
    r,g,b = int(color[0]), int(color[1]), int(color[2])
    er,eg,eb = ENERGY_RING_COLOR
    return all(abs(c - e) <= RING_TOLERANCE for c,e in zip((r,g,b),(er,eg,eb)))

def is_bar_filled(pixel, expected, tol=20):
    if pixel is None: return False
    r,g,b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    er,eg,eb = expected
    return all(abs(c - e) <= tol for c,e in zip((r,g,b),(er,eg,eb)))

# ====================== LOOP ======================
if __name__ == "__main__":
    print("=== SuperMonk Healer: Spells + Ring + Potions ===")
    if not locate_bars():
        print("❌ No se detectaron las barras")
        exit(1)

    print(f"✅ Healing activo | Ring: ≤{EQUIP_BELOW}% / ≥{UNEQUIP_ABOVE}% (mana mín {MIN_MANA_TO_EQUIP}%)")

    # Timestamps para pociones
    _last_potion_ts = 0.0
    _last_hard_potion_ts = 0.0
    _last_mid_potion_ts = 0.0
    _last_mana_potion_ts = 0.0

    try:
        while True:
            hwnd = find_obs_window()
            if not hwnd:
                time.sleep(0.5)
                continue

            img = capture_window(hwnd)
            client_bgr = crop_client_area(img, hwnd)
            client_rgb = cv2.cvtColor(client_bgr, cv2.COLOR_BGR2RGB)

            now = time.time()

            # === 1. HEALING SPELLS (PRIORIDAD MÁXIMA) ===
            spell_used = False
            if SPELLS_ENABLED and (now - _last_spell_ts) >= SPELLS_GLOBAL_CD:
                spells = [
                    (HARD_CFG, _last_hard_ts),
                    (MID_CFG, _last_mid_ts),
                    (LIGHT_CFG, _last_light_ts)
                ]
                for cfg, last_ts in spells:
                    if not cfg.get("enabled", False):
                        continue
                    pct = cfg["hp_percent"]
                    cd = cfg.get("cooldown_sec", 1.0)
                    if (now - last_ts) < cd:
                        continue

                    pixel = get_pixel(client_rgb, int(hp_x0 + BAR_LENGTH_PX * (pct / 100)), hp_y)
                    if not is_bar_filled(pixel, (211, 79, 79)):
                        hotkey = cfg["hotkey"]
                        send_spell_key(hotkey)
                        ts = time.strftime('%H:%M:%S')
                        name = "HARD" if cfg is HARD_CFG else "MID" if cfg is MID_CFG else "LIGHT"
                        print(f"[{ts}] 🩸 {name} HEALING HP≤{pct}% → {hotkey}")
                        if cfg is HARD_CFG: _last_hard_ts = now
                        elif cfg is MID_CFG: _last_mid_ts = now
                        else: _last_light_ts = now
                        _last_spell_ts = now
                        spell_used = True
                        break

            # === 2. ENERGY RING ===
            ring_used = False
            if (now - _last_ring_ts) >= RING_COOLDOWN:
                current_equipped = is_ring_equipped(client_rgb)

                low_pixel = get_pixel(client_rgb, int(hp_x0 + BAR_LENGTH_PX * (EQUIP_BELOW / 100)), hp_y)
                high_pixel = get_pixel(client_rgb, int(hp_x0 + BAR_LENGTH_PX * (UNEQUIP_ABOVE / 100)), hp_y)

                hp_low = not is_bar_filled(low_pixel, (211, 79, 79))
                hp_high = is_bar_filled(high_pixel, (211, 79, 79))

                action = None
                if hp_low and not current_equipped:
                    if MIN_MANA_TO_EQUIP > 0 and mana_x0:
                        mana_pixel = get_pixel(client_rgb, int(mana_x0 + BAR_LENGTH_PX * (MIN_MANA_TO_EQUIP / 100)), mana_y)
                        if not is_bar_filled(mana_pixel, (83, 80, 218), tol=25):
                            ts = time.strftime('%H:%M:%S')
                            print(f"[{ts}] ⚠️ Mana < {MIN_MANA_TO_EQUIP}% → NO EQUIPO RING")
                            time.sleep(POLL_SECONDS)
                            continue
                    send_key_f17()
                    action = f"EQUIPANDO RING (HP ≤ {EQUIP_BELOW}%)"
                    ring_used = True

                elif hp_high and current_equipped:
                    send_key_end()
                    action = f"DESEQUIPANDO RING (HP ≥ {UNEQUIP_ABOVE}%)"
                    ring_used = True

                if action:
                    ts = time.strftime('%H:%M:%S')
                    print(f"[{ts}] ⚡ {action}")
                    _last_ring_ts = now

            # === 3. POTIONS (PRIORIDAD BAJA) ===
            if POTIONS_ENABLED and (now - _last_potion_ts) >= 1.0:
                # Delay extra si hubo acción de ring
                if ring_used:
                    time.sleep(0.6)

                potions = [
                    (HARD_POTION_CFG, _last_hard_potion_ts, "ULTIMATE SPIRIT", "hp_percent"),
                    (MID_POTION_CFG, _last_mid_potion_ts, "GREAT SPIRIT", "hp_percent"),
                    (MANA_POTION_CFG, _last_mana_potion_ts, "MANA", "mana_percent")
                ]

                for cfg, last_ts, name, percent_key in potions:
                    if not cfg.get("enabled", False):
                        continue
                    pct = cfg.get(percent_key, 90 if percent_key == "mana_percent" else 80)
                    cd = cfg.get("cooldown_sec", 1.0)
                    if (now - last_ts) < cd:
                        continue

                    is_mana = percent_key == "mana_percent"
                    x0 = mana_x0 if is_mana else hp_x0
                    y = mana_y if is_mana else hp_y
                    expected = (83, 80, 218) if is_mana else (211, 79, 79)

                    pixel = get_pixel(client_rgb, int(x0 + BAR_LENGTH_PX * (pct / 100.0)), y)
                    if not is_bar_filled(pixel, expected, tol=25):
                        hotkey = cfg["hotkey"]
                        send_spell_key(hotkey)
                        ts = time.strftime('%H:%M:%S')
                        print(f"[{ts}] 🧪 {name} POTION ({'mana' if is_mana else 'hp'}≤{pct}%) → {hotkey}")
                        if name == "ULTIMATE SPIRIT":
                            _last_hard_potion_ts = now
                        elif name == "GREAT SPIRIT":
                            _last_mid_potion_ts = now
                        else:
                            _last_mana_potion_ts = now
                        _last_potion_ts = now
                        break

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print("\n\n¡Detenido! Buena caza, monk.")