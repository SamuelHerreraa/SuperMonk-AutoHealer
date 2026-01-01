import os
import time
import json
import cv2
import numpy as np
from PIL import Image
import win32gui
import win32ui
import win32con
import keyboard

# ============================= CONFIGURACIÓN =============================
OBS_TITLE_PREFIX = "Windowed Projector (Source)"

# Template matching (solo se usa una vez al inicio si no hay JSON)
THRESHOLD = 0.92

# Ventana que DEBE estar en foreground para enviar hotkeys
TIBIA_TITLE_CONTAINS = "Tibia"  # ajusta si tu ventana se llama distinto

# Porcentaje de mana a monitorear
TARGET_MANA_PERCENT = 80

# Color esperado en ese punto cuando la barra está "llena" en esa zona
EXPECTED_COLOR = (83, 80, 218)   # RGB
COLOR_TOLERANCE = 20

# Offsets (igual que HP)
OFFSET_TO_X0 = 9
BAR_LENGTH_PX = 90

# Hotkey a enviar cuando sea DIFERENTE
HOTKEY_ON_DIFF = "f6"
HOTKEY_COOLDOWN_SEC = 0.8

# Loop
POLL_SECONDS = 1

# Archivos
ROOT = os.path.dirname(os.path.abspath(__file__))
MANA_TEMPLATE = os.path.join(ROOT, "mana.png")
COORDS_JSON = os.path.join(ROOT, "coords_mana.json")
# ============================= FIN CONFIGURACIÓN =============================

# Variables globales (se calculan una sola vez)
mana_center_rel = None
x0_rel = None
x1_rel = None
y_bar = None

_last_hotkey_ts = 0.0


def is_tibia_foreground() -> bool:
    """True si la ventana activa contiene TIBIA_TITLE_CONTAINS en el título."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or ""
        return TIBIA_TITLE_CONTAINS.lower() in title.lower()
    except:
        return False


def send_hotkey(key: str):
    """Envía una tecla con keyboard (a la ventana activa)."""
    keyboard.press_and_release(key)


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


def locate_mana_once():
    """Localiza mana.png UNA vez y guarda/lee coords desde JSON."""
    global mana_center_rel, x0_rel, x1_rel, y_bar

    # 1) Intentar JSON
    if os.path.exists(COORDS_JSON):
        try:
            with open(COORDS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("found") and data.get("center_rel"):
                cx = int(data["center_rel"]["x"])
                cy = int(data["center_rel"]["y"])
                print(f"Mana encontrado desde JSON: centro relativo X={cx}, Y={cy}")
                mana_center_rel = (cx, cy)
                x0_rel = cx + OFFSET_TO_X0
                x1_rel = x0_rel + BAR_LENGTH_PX
                y_bar = cy
                print(f"Barra de mana calculada: X0={x0_rel} (1%), X1={x1_rel} (100%), Y={y_bar}")
                return True
        except Exception as e:
            print(f"Error leyendo JSON: {e}")

    # 2) Template matching
    print("No se encontró JSON válido. Buscando mana.png con template matching...")
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print("No se encontró ventana OBS. Asegúrate de tener el Projector abierto.")
        return False

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)

    templ = cv2.imread(MANA_TEMPLATE, cv2.IMREAD_COLOR)
    if templ is None:
        print(f"No se pudo cargar {MANA_TEMPLATE}")
        return False

    res = cv2.matchTemplate(client_bgr, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < THRESHOLD:
        print(f"No se detectó mana.png (score: {max_val:.3f} < {THRESHOLD})")
        return False

    th, tw = templ.shape[:2]
    cx = max_loc[0] + tw // 2
    cy = max_loc[1] + th // 2

    mana_center_rel = (cx, cy)
    x0_rel = cx + OFFSET_TO_X0
    x1_rel = x0_rel + BAR_LENGTH_PX
    y_bar = cy

    print(f"Mana detectado! Centro relativo: X={cx}, Y={cy} (score={max_val:.3f})")
    print(f"Barra de mana: X0={x0_rel} (1%), X1={x1_rel} (100%), Y={y_bar}")

    payload = {"center_rel": {"x": cx, "y": cy}, "found": True, "ts": time.time()}
    with open(COORDS_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return True


def get_pixel_color_at_rel(client_rgb_img, rel_x, rel_y):
    h, w = client_rgb_img.shape[:2]
    if 0 <= rel_x < w and 0 <= rel_y < h:
        return tuple(map(int, client_rgb_img[rel_y, rel_x]))
    return None


def monitor_mana_pixel():
    global _last_hotkey_ts

    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print("ERROR: No se encontró ventana OBS.")
        return

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)
    client_rgb = cv2.cvtColor(client_bgr, cv2.COLOR_BGR2RGB)

    target_x = int(x0_rel + (BAR_LENGTH_PX * (TARGET_MANA_PERCENT / 100.0)))
    color = get_pixel_color_at_rel(client_rgb, target_x, y_bar)

    if color is None:
        print(f"[{time.strftime('%H:%M:%S')}] Posición fuera de rango: X={target_x}, Y={y_bar}")
        return

    diff = any(abs(color[i] - EXPECTED_COLOR[i]) > COLOR_TOLERANCE for i in range(3))

    if not diff:
        print(f"[{time.strftime('%H:%M:%S')}] MANA {TARGET_MANA_PERCENT}% → X={target_x}, Y={y_bar} → Color: {color} → OK")
        return

    # DIFERENTE
    print(f"[{time.strftime('%H:%M:%S')}] MANA {TARGET_MANA_PERCENT}% → X={target_x}, Y={y_bar} → Color: {color} → DIFERENTE ✅")

    # Solo si Tibia está en foreground
    if not is_tibia_foreground():
        print("   ↳ Tibia NO está en primer plano. (No envío hotkey)")
        return

    # Cooldown
    now = time.time()
    if (now - _last_hotkey_ts) < HOTKEY_COOLDOWN_SEC:
        print(f"   ↳ Cooldown activo ({HOTKEY_COOLDOWN_SEC}s). (No envío hotkey)")
        return

    send_hotkey(HOTKEY_ON_DIFF)
    _last_hotkey_ts = now
    print(f"   ↳ Hotkey enviada: {HOTKEY_ON_DIFF}")


if __name__ == "__main__":
    print("Iniciando SuperMonk Mana Monitor...")
    print(f"Buscando mana.png y calculando barra (+9 y +90 píxeles)...\n")

    if not locate_mana_once():
        print("No se pudo localizar mana.png. Verifica el archivo y el projector de OBS.")
        raise SystemExit(1)

    print(f"\nMonitoreando pixel correspondiente al {TARGET_MANA_PERCENT}% de mana cada {POLL_SECONDS}s")
    print(f"Color esperado: {EXPECTED_COLOR} (±{COLOR_TOLERANCE})")
    print(f"Hotkey cuando sea DIFERENTE: {HOTKEY_ON_DIFF} (cooldown {HOTKEY_COOLDOWN_SEC}s)")
    print(f"Solo envía hotkey si Tibia está en foreground y el título contiene: '{TIBIA_TITLE_CONTAINS}'\n")

    try:
        while True:
            monitor_mana_pixel()
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n\nMonitoreo detenido por el usuario.")
