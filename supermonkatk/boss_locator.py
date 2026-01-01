# boss_locator.py
import os
import cv2
import json
import time
import numpy as np
import win32gui
import win32ui
import win32con
from PIL import Image

# ========================
# CONFIGURACIÓN
# ========================
OBS_TITLE_PREFIX = "Windowed Projector (Source)"

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, "img")
TEMPLATE_PATH = os.path.join(IMG_DIR, "exorigranpug.png")
OUT_JSON = os.path.join(IMG_DIR, "coords_boss.json")

THRESHOLD = 0.88  # Puedes bajar a 0.85 si es muy estricto


# ========================
# FUNCIONES DE CAPTURA (idénticas a sereno_locator)
# ========================
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


def crop_client_from_window_capture(hwnd, win_img_pil: Image.Image) -> np.ndarray:
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


# ========================
# LOCALIZADOR DEL BOSS
# ========================
def main():
    print("🔍 Buscando ventana OBS...")
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print(f"❌ No se encontró OBS con título: '{OBS_TITLE_PREFIX}'")
        print("   Abre Tibia en OBS → Windowed Projector (Source)")
        return

    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ No se encontró la plantilla: {TEMPLATE_PATH}")
        return

    print("✅ Ventana OBS encontrada.")
    print("✅ Plantilla cargada:", os.path.basename(TEMPLATE_PATH))
    print(f"   Umbral de detección: {THRESHOLD}")
    print("\nCapturando y buscando el icono del boss...\n")

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_from_window_capture(hwnd, win_img)

    template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_COLOR)
    if template is None:
        print("❌ Error al leer la plantilla.")
        return

    res = cv2.matchTemplate(client_bgr, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val < THRESHOLD:
        print(f"❌ No se detectó el boss.")
        print(f"   Mejor coincidencia: {max_val:.3f} (necesitas ≥ {THRESHOLD})")
        print("   → Intenta seleccionar al boss en Tibia y vuelve a ejecutar.")
        return

    h, w = template.shape[:2]
    x1 = max_loc[0]
    y1 = max_loc[1]
    x2 = x1 + w
    y2 = y1 + h

    print(f"✅ ¡BOSS DETECTADO!")
    print(f"   Confianza: {max_val:.3f}")
    print(f"   Coordenadas encontradas (relativas al cliente OBS):")
    print(f"       x1: {x1}")
    print(f"       y1: {y1}")
    print(f"       x2: {x2}")
    print(f"       y2: {y2}")

    # Guardar en JSON
    payload = {
        "timestamp": time.time(),
        "boss_detected": True,
        "confidence": float(max_val),
        "template": "exorigranpug.png",
        "roi": {
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2)
        }
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Coordenadas guardadas en: {OUT_JSON}")

    # Opcional: guardar ROI actual para verificar visualmente
    roi_actual = client_bgr[y1:y2, x1:x2]
    debug_path = os.path.join(IMG_DIR, "debug_boss_actual.jpg")
    cv2.imwrite(debug_path, roi_actual)
    print(f"   → Captura actual guardada en: {debug_path}")


if __name__ == "__main__":
    main()