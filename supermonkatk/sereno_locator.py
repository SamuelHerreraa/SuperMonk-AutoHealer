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

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, "img")
OUT_JSON = os.path.join(IMG_DIR, "coords_sereno.json")

THRESHOLD = 0.92  # ajusta si hace falta


def find_window_by_prefix(prefix: str):
    found = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if title.startswith(prefix):
                found.append(hwnd)

    win32gui.EnumWindows(enum_cb, None)
    return found[0] if found else None


def capture_window_image(hwnd) -> Image.Image:
    """Captura la ventana (aunque esté detrás) usando PrintWindow. Devuelve PIL.Image RGB."""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w = max(1, right - left)
    h = max(1, bottom - top)

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bitmap)

    # Intento 1: PrintWindow
    try:
        res = win32gui.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
        if res != 1:
            # Fallback: BitBlt (puede salir negro si está tapada)
            save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
    except Exception:
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

    # cleanup
    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img


def get_obs_client_geometry(hwnd):
    """window_rect (L,T,R,B), client_origin_screen (x,y), client_size (w,h)"""
    wL, wT, wR, wB = win32gui.GetWindowRect(hwnd)

    cL, cT, cR, cB = win32gui.GetClientRect(hwnd)
    cw = max(1, cR - cL)
    ch = max(1, cB - cT)

    cx, cy = win32gui.ClientToScreen(hwnd, (0, 0))
    return (wL, wT, wR, wB), (cx, cy), (cw, ch)


def pil_to_cv(img_pil: Image.Image) -> np.ndarray:
    """PIL RGB -> cv2 BGR"""
    rgb = np.array(img_pil)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def crop_client_from_window_capture(hwnd, win_img_pil: Image.Image) -> np.ndarray:
    """
    Recorta SOLO el área client (donde se ve el video del projector) desde la captura completa del window.
    Devuelve cv2 BGR.
    """
    (wL, wT, wR, wB), (cX, cY), (cW, cH) = get_obs_client_geometry(hwnd)

    # Offset del client dentro del bitmap del window
    offx = cX - wL
    offy = cY - wT

    win_cv = pil_to_cv(win_img_pil)
    h, w = win_cv.shape[:2]

    x1 = max(0, int(offx))
    y1 = max(0, int(offy))
    x2 = min(w, int(offx + cW))
    y2 = min(h, int(offy + cH))

    return win_cv[y1:y2, x1:x2].copy()


def locate_template(search_bgr: np.ndarray, template_path: str, threshold: float):
    templ = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if templ is None:
        return {"found": False, "error": f"No pude leer template: {template_path}"}

    res = cv2.matchTemplate(search_bgr, templ, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val < threshold:
        return {"found": False, "score": float(max_val), "error": "No match above threshold"}

    th, tw = templ.shape[:2]
    top_left = {"x": int(max_loc[0]), "y": int(max_loc[1])}
    center = {"x": int(max_loc[0] + tw // 2), "y": int(max_loc[1] + th // 2)}
    size = {"w": int(tw), "h": int(th)}

    return {"found": True, "score": float(max_val), "top_left_rel": top_left, "center_rel": center, "size": size}


def main():
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print({"found": False, "error": f"No encontré ventana OBS: '{OBS_TITLE_PREFIX}'", "ts": time.time()})
        return

    sereno_path = os.path.join(IMG_DIR, "sereno.png")

    # Capturamos ventana OBS y recortamos el client
    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_from_window_capture(hwnd, win_img)

    match = locate_template(client_bgr, sereno_path, THRESHOLD)
    payload = {
        "ts": time.time(),
        "found": match.get("found", False),
        "score": match.get("score", None),
        "error": match.get("error", None),
        "obs_window": {
            "title_substring": OBS_TITLE_PREFIX,
            "rect_global": None,
        },
        "sereno": None,
    }

    # Guardar también el rect del OBS (por debug)
    wL, wT, wR, wB = win32gui.GetWindowRect(hwnd)
    payload["obs_window"]["rect_global"] = {
        "left": int(wL),
        "top": int(wT),
        "width": int(wR - wL),
        "height": int(wB - wT),
    }

    if match.get("found"):
        # Convertimos coords RELATIVAS al client -> a coords GLOBALES
        _, (cX, cY), _ = get_obs_client_geometry(hwnd)
        top_left_global = {
            "x": int(cX + match["top_left_rel"]["x"]),
            "y": int(cY + match["top_left_rel"]["y"]),
        }
        center_global = {
            "x": int(cX + match["center_rel"]["x"]),
            "y": int(cY + match["center_rel"]["y"]),
        }

        payload["sereno"] = {
            "template": "sereno.png",
            "top_left_rel": match["top_left_rel"],
            "top_left_global": top_left_global,
            "center_rel": match["center_rel"],
            "center_global": center_global,
            "size": match["size"],
        }

        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    print(payload)


if __name__ == "__main__":
    main()
