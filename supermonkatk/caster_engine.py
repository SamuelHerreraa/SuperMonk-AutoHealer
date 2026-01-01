# caster_engine.py - VERSIÓN FINAL LIMPIA Y PERFECTA (solo prints de modo activo/desactivo)
import os
import time
import json
import ctypes
import cv2
import numpy as np
import win32gui
import win32ui
import win32con
from PIL import Image

from pynput.keyboard import Controller
from overlay_hunt import is_foreground_title_contains
from config import (
    IMGS_DIR, COORDS_PATH, OBS_TITLE_SUBSTRING,
    ROI_LEFT_OFFSET, ROI_TOP_OFFSET, ROI_WIDTH, ROI_HEIGHT,
    THRESHOLD, HOTKEY_LOW, HOTKEY_HIGH, HOTKEY_BOSS_PRI, HOTKEY_BOSS_HIGH,
    CYCLE_SECONDS, TIBIA_TITLE_PREFIX,
)
from hotkeys import parse_hotkey
from states import STATE, state_lock

kbd = Controller()

# ========================
# CAPTURA SIMPLE (para harmony - tu método original perfecto)
# ========================
def set_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def find_window_by_title_substring(substring: str):
    found = []
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if substring.lower() in title.lower():
                found.append(hwnd)
    win32gui.EnumWindows(enum_cb, None)
    return found[0] if found else None

def capture_window_simple(hwnd):
    if win32gui.IsIconic(hwnd):
        return None
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(bmp)
    result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
    bmpinfo = bmp.GetInfo()
    bmpstr = bmp.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8)
    img.shape = (bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4)
    win32gui.DeleteObject(bmp.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    if result != 1:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

# ========================
# CAPTURA PRECISA (para boss - igual que boss_locator.py)
# ========================
def capture_window_precise(hwnd) -> Image.Image:
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
    except Exception:
        save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

    bmpinfo = bitmap.GetInfo()
    bmpstr = bitmap.GetBitmapBits(True)

    img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)

    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img

def get_obs_client_geometry(hwnd):
    wL, wT, wR, wB = win32gui.GetWindowRect(hwnd)
    cL, cT, cR, cB = win32gui.GetClientRect(hwnd)
    cw = max(1, cR - cL)
    ch = max(1, cB - cT)
    cx, cy = win32gui.ClientToScreen(hwnd, (0, 0))
    return (wL, wT, wR, wB), (cx, cy), (cw, ch)

def crop_client_from_precise_capture(hwnd, win_img_pil: Image.Image) -> np.ndarray:
    (wL, wT, wR, wB), (cX, cY), (cW, cH) = get_obs_client_geometry(hwnd)
    offx = cX - wL
    offy = cY - wT

    win_cv = cv2.cvtColor(np.array(win_img_pil), cv2.COLOR_RGB2BGR)
    h, w = win_cv.shape[:2]

    x1 = max(0, int(offx))
    y1 = max(0, int(offy))
    x2 = min(w, int(offx + cW))
    y2 = min(h, int(offy + cH))

    return win_cv[y1:y2, x1:x2].copy()

def clamp_roi(x1, y1, x2, y2, max_w, max_h):
    x1 = max(0, min(x1, max_w))
    y1 = max(0, min(y1, max_h))
    x2 = max(0, min(x2, max_w))
    y2 = max(0, min(y2, max_h))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2

# ========================
# TEMPLATES Y COORDS
# ========================
def load_templates():
    templates = []
    for i in range(6):
        p = os.path.join(IMGS_DIR, f"harmony{i}.png")
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                templates.append((i, img))
    return templates

def load_boss_template():
    p = os.path.join(IMGS_DIR, "exorigranpug.png")
    if os.path.exists(p):
        return cv2.imread(p, cv2.IMREAD_COLOR)
    print("❌ No se encontró exorigranpug.png")
    return None

def load_boss_coords():
    json_path = os.path.join(IMGS_DIR, "coords_boss.json")
    if not os.path.exists(json_path):
        print("❌ No se encontró coords_boss.json → Ejecuta boss_locator.py")
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        roi = data["roi"]
        return roi["x1"], roi["y1"], roi["x2"], roi["y2"]
    except Exception as e:
        print(f"❌ Error leyendo coords_boss.json: {e}")
        return None

def press_key(key_str: str):
    key = parse_hotkey(key_str)
    kbd.press(key)
    kbd.release(key)

# ========================
# LOOP PRINCIPAL
# ========================
def run_cast_loop():
    set_dpi_awareness()

    if not os.path.exists(COORDS_PATH):
        print("❌ coords_sereno.json no existe.")
        return

    with open(COORDS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    ser = data["sereno"]
    sx = int(ser["top_left_rel"]["x"])
    sy = int(ser["top_left_rel"]["y"])

    hwnd = find_window_by_title_substring(OBS_TITLE_SUBSTRING)
    if not hwnd:
        print("❌ No se encontró OBS Projector.")
        return

    templates = load_templates()
    boss_template = load_boss_template()
    boss_coords = load_boss_coords()
    if boss_coords is None:
        boss_coords = (0, 0, 1, 1)  # inválido

    last_harmony = None
    last_cycle = 0.0

    # Variables para mostrar cambio de modo una sola vez
    last_hunt_state = None
    last_boss_state = None

    print("✅ Caster iniciado - Listo para cazar.")

    while True:
        # Captura simple para harmony
        frame_harmony = capture_window_simple(hwnd)
        # Captura precisa para boss
        win_img_pil = capture_window_precise(hwnd)
        frame_boss = crop_client_from_precise_capture(hwnd, win_img_pil)

        if frame_harmony is None or frame_boss.size == 0:
            time.sleep(0.5)
            continue

        # === DETECCIÓN DE HARMONY ===
        H_h, W_h = frame_harmony.shape[:2]
        roi_harmony = clamp_roi(
            sx - ROI_LEFT_OFFSET,
            sy - ROI_TOP_OFFSET,
            sx - ROI_LEFT_OFFSET + ROI_WIDTH,
            sy - ROI_TOP_OFFSET + ROI_HEIGHT,
            W_h, H_h,
        )
        if roi_harmony:
            x1_h, y1_h, x2_h, y2_h = roi_harmony
            roi_img_harmony = frame_harmony[y1_h:y2_h, x1_h:x2_h]
            best_score = -1
            best_level = None
            for level, tmpl in templates:
                res = cv2.matchTemplate(roi_img_harmony, tmpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val > best_score:
                    best_score = max_val
                    best_level = level
            if best_score >= THRESHOLD:
                last_harmony = best_level

        # === DETECCIÓN DEL BOSS ===
        boss_detected = False
        if boss_template is not None and boss_coords:
            x1_b, y1_b, x2_b, y2_b = boss_coords
            boss_roi = clamp_roi(x1_b, y1_b, x2_b, y2_b, frame_boss.shape[1], frame_boss.shape[0])
            if boss_roi:
                roi_boss = frame_boss[y1_b:y2_b, x1_b:x2_b]
                res = cv2.matchTemplate(roi_boss, boss_template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= THRESHOLD:
                    boss_detected = True

        # === ESTADOS Y PRINTS DE MODO (solo al cambiar) ===
        with state_lock:
            active_hunt = STATE["active_hunt"]
            active_boss = STATE["active_boss"]

        # Mostrar cambio de modo una sola vez
        if active_hunt != last_hunt_state:
            if active_hunt:
                print("🎯 HUNT MODE = Activado")
            else:
                print("🎯 HUNT MODE = Desactivado")
            last_hunt_state = active_hunt

        if active_boss != last_boss_state:
            if active_boss:
                print("👹 BOSS MODE = Activado")
            else:
                print("👹 BOSS MODE = Desactivado")
            last_boss_state = active_boss

        tibia_fg = is_foreground_title_contains(TIBIA_TITLE_PREFIX) or is_foreground_title_contains(OBS_TITLE_SUBSTRING)
        now = time.time()

        if not tibia_fg:
            last_cycle = now
            time.sleep(0.1)
            continue

        if not (active_hunt or active_boss):
            time.sleep(0.1)
            continue

        if now - last_cycle < CYCLE_SECONDS:
            time.sleep(0.1)
            continue

        # === LÓGICA DE CASTEO (sin prints) ===
        if active_boss:
            if boss_detected:
                press_key(HOTKEY_BOSS_PRI)  # "1"
            elif last_harmony is not None:
                if last_harmony >= 5:
                    press_key(HOTKEY_BOSS_HIGH)  # "2"
                else:
                    press_key(HOTKEY_LOW)  # "f9"
            else:
                press_key(HOTKEY_LOW)

        elif active_hunt and last_harmony is not None:
            if last_harmony >= 5:
                press_key(HOTKEY_HIGH)
            else:
                press_key(HOTKEY_LOW)

        last_cycle = now
        time.sleep(0.1)