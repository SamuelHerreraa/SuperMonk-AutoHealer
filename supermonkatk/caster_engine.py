import os
import time
import json
import ctypes
import cv2
import numpy as np

import win32gui
import win32ui

from pynput.keyboard import Controller

from overlay_hunt import is_foreground_title_contains
from config import (
    IMGS_DIR, COORDS_PATH,
    OBS_TITLE_SUBSTRING,
    ROI_LEFT_OFFSET, ROI_TOP_OFFSET, ROI_WIDTH, ROI_HEIGHT,
    THRESHOLD,
    HOTKEY_LOW, HOTKEY_HIGH,
    CYCLE_SECONDS,
    TIBIA_TITLE_PREFIX,
)
from hotkeys import parse_hotkey
from states import STATE, state_lock

kbd = Controller()


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


def get_client_size(hwnd):
    l, t, r, b = win32gui.GetClientRect(hwnd)
    return r - l, b - t


def capture_window_printwindow(hwnd):
    if win32gui.IsIconic(hwnd):
        return None

    w, h = get_client_size(hwnd)
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


def clamp_roi(x1, y1, x2, y2, max_w, max_h):
    x1 = max(0, min(x1, max_w))
    y1 = max(0, min(y1, max_h))
    x2 = max(0, min(x2, max_w))
    y2 = max(0, min(y2, max_h))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def load_templates():
    templates = []
    for i in range(6):
        p = os.path.join(IMGS_DIR, f"harmony{i}.png")
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                templates.append((i, img))
    return templates


def press_key(key_str: str):
    key = parse_hotkey(key_str)
    kbd.press(key)
    kbd.release(key)


def run_cast_loop():
    if not os.path.exists(COORDS_PATH):
        print("❌ coords_sereno.json no existe. Ejecuta sereno_locator.py primero.")
        return

    with open(COORDS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    ser = data["sereno"]
    sx = int(ser["top_left_rel"]["x"])
    sy = int(ser["top_left_rel"]["y"])

    hwnd = find_window_by_title_substring(OBS_TITLE_SUBSTRING)
    if not hwnd:
        print("❌ No se encontró la ventana del OBS.")
        return

    templates = load_templates()
    last_harmony = None
    last_cycle = 0.0

    while True:
        frame = capture_window_printwindow(hwnd)
        if frame is None:
            time.sleep(0.5)
            continue

        H, W = frame.shape[:2]
        roi = clamp_roi(
            sx - ROI_LEFT_OFFSET,
            sy - ROI_TOP_OFFSET,
            sx - ROI_LEFT_OFFSET + ROI_WIDTH,
            sy - ROI_TOP_OFFSET + ROI_HEIGHT,
            W, H,
        )
        if not roi:
            time.sleep(0.5)
            continue

        x1, y1, x2, y2 = roi
        roi_img = frame[y1:y2, x1:x2]

        best_score = -1
        best_level = None

        for level, tmpl in templates:
            res = cv2.matchTemplate(roi_img, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_level = level

        if best_score >= THRESHOLD:
            last_harmony = best_level

        with state_lock:
            active = STATE["active"]

        # ✅ Solo castear si Tibia está en primer plano
        tibia_fg = is_foreground_title_contains(TIBIA_TITLE_PREFIX)
        now = time.time()

        if not tibia_fg:
            # Evita “disparo instantáneo” al regresar a Tibia
            last_cycle = now
            time.sleep(0.1)
            continue

        if active and last_harmony is not None:
            if now - last_cycle >= CYCLE_SECONDS:
                key = HOTKEY_HIGH if last_harmony >= 5 else HOTKEY_LOW
                press_key(key)
                last_cycle = now

        time.sleep(0.1)
