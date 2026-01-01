import os
import time
import json
import cv2
import numpy as np
from PIL import Image
import win32gui
import win32ui
import win32con

OBS_TITLE_PREFIX = "Windowed Projector (Source)"
THRESHOLD = 0.92

# Archivos
ROOT = os.path.dirname(os.path.abspath(__file__))
SERENO_TEMPLATE = os.path.join(ROOT, "heart.png")  # Cambiado a heart.png como dijiste
OUT_JSON = os.path.join(ROOT, "coords_sereno.json")


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

    img = Image.frombuffer(
        "RGB",
        (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
        bmpstr,
        "raw",
        "BGRX",
        0,
        1,
    )

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


def locate_center(search_bgr: np.ndarray, template_path: str, threshold: float):
    templ = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if templ is None:
        print(f"Error: No se pudo cargar {template_path}")
        return None

    res = cv2.matchTemplate(search_bgr, templ, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val < threshold:
        return None

    th, tw = templ.shape[:2]
    center_x = max_loc[0] + tw // 2
    center_y = max_loc[1] + th // 2
    return int(center_x), int(center_y)  # ← Coordenada RELATIVA al área cliente


def main():
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        payload = {"center_rel": None, "center_global": None, "ts": time.time()}
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(payload)
        return

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)

    center_rel = locate_center(client_bgr, SERENO_TEMPLATE, THRESHOLD)

    if center_rel is None:
        center_global = None
        center_rel_dict = None
    else:
        cx, cy = center_rel
        center_rel_dict = {"x": cx, "y": cy}
        # Opcional: calcular global si lo necesitas también
        client_origin_x, client_origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
        center_global = {
            "x": client_origin_x + cx,
            "y": client_origin_y + cy
        }

    # Guardar principal: coordenada RELATIVA
    payload = {
        "center_rel": center_rel_dict,      # ← Esto es lo que querías
        "center_global": center_global,     # ← Bonus: también la global
        "found": center_rel is not None,
        "ts": time.time()
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(payload)


if __name__ == "__main__":
    main()