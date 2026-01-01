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

# ============================= CONFIGURACIÓN =============================
# Ventana del OBS projector (para leer la imagen)
OBS_TITLE_PREFIX = "Windowed Projector (Source)"

# Tibia debe estar al frente para mandar hotkeys
TIBIA_TITLE_PREFIX = "Tibia"   # cambia si tu título difiere (ej: "Tibia - ")

# Template matching (solo 1 vez al inicio)
THRESHOLD = 0.92

# Color esperado cuando la barra está "llena" en esa zona (vida arriba de ese %)
EXPECTED_COLOR = (211, 79, 79)   # RGB
COLOR_TOLERANCE = 20

# Offsets (tu lógica)
OFFSET_TO_X0 = 9
BAR_LENGTH_PX = 90

# Archivos
ROOT = os.path.dirname(os.path.abspath(__file__))
HEART_TEMPLATE = os.path.join(ROOT, "heart.png")
COORDS_JSON = os.path.join(ROOT, "coords_sereno.json")

# ------------- PRIORIDADES DE HEALING -------------
# Orden: de MÁS urgente a MENOS urgente (HP más bajo primero)
# Si el pixel en ese % es DIFERENTE → HP está por debajo de ese % → manda hotkey.
HEAL_RULES = [
    {"name": "EMERGENCY", "hp_percent": 80, "hotkey": "f3", "cooldown": 0.8},
    {"name": "MID",       "hp_percent": 88, "hotkey": "f2", "cooldown": 0.8},
    {"name": "LIGHT",     "hp_percent": 95, "hotkey": "f1", "cooldown": 0.8},
]

# Cada cuánto revisa (segundos). Puedes bajarlo a 0.10-0.20 si quieres más rápido.
POLL_SECONDS = 0.15
# ============================= FIN CONFIGURACIÓN =============================

# Variables globales calculadas 1 vez
heart_center_rel = None
x0_rel = None
x1_rel = None
y_bar = None

# Cooldowns por regla
_last_sent = {r["name"]: 0.0 for r in HEAL_RULES}


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


def locate_heart_once():
    """Corre una vez: obtiene centro del heart y calcula línea de barra."""
    global heart_center_rel, x0_rel, x1_rel, y_bar

    if os.path.exists(COORDS_JSON):
        try:
            with open(COORDS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("found") and data.get("center_rel"):
                cx = int(data["center_rel"]["x"])
                cy = int(data["center_rel"]["y"])
                print(f"Heart encontrado desde JSON: centro relativo X={cx}, Y={cy}")
                heart_center_rel = (cx, cy)
                x0_rel = cx + OFFSET_TO_X0
                x1_rel = x0_rel + BAR_LENGTH_PX
                y_bar = cy
                print(f"Barra de vida calculada: X0={x0_rel} (1%), X1={x1_rel} (100%), Y={y_bar}")
                return True
        except Exception as e:
            print(f"Error leyendo JSON: {e}")

    print("No se encontró JSON válido. Buscando heart.png con template matching...")
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print("No se encontró ventana OBS. Asegúrate de tener el Projector abierto.")
        return False

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)

    templ = cv2.imread(HEART_TEMPLATE, cv2.IMREAD_COLOR)
    if templ is None:
        print(f"No se pudo cargar {HEART_TEMPLATE}")
        return False

    res = cv2.matchTemplate(client_bgr, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < THRESHOLD:
        print(f"No se detectó heart.png (score: {max_val:.3f} < {THRESHOLD})")
        return False

    th, tw = templ.shape[:2]
    cx = max_loc[0] + tw // 2
    cy = max_loc[1] + th // 2

    heart_center_rel = (cx, cy)
    x0_rel = cx + OFFSET_TO_X0
    x1_rel = x0_rel + BAR_LENGTH_PX
    y_bar = cy

    print(f"Heart detectado! Centro relativo: X={cx}, Y={cy}")
    print(f"Barra de vida: X0={x0_rel} (1%), X1={x1_rel} (100%), Y={y_bar}")

    payload = {"center_rel": {"x": cx, "y": cy}, "found": True, "ts": time.time()}
    with open(COORDS_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return True


def get_pixel_color_at_rel(client_rgb_img, rel_x, rel_y):
    h, w = client_rgb_img.shape[:2]
    if 0 <= rel_x < w and 0 <= rel_y < h:
        return tuple(map(int, client_rgb_img[rel_y, rel_x]))
    return None


def color_is_different(color_rgb):
    # True si se sale de tolerancia contra EXPECTED_COLOR
    return any(abs(color_rgb[i] - EXPECTED_COLOR[i]) > COLOR_TOLERANCE for i in range(3))


def send_hotkey_once(key: str):
    """
    Envía una tecla usando keyboard (al foreground).
    OJO: La ventana activa recibe la tecla.
    """
    keyboard.press_and_release(key)


def heal_loop_once():
    """
    Captura 1 frame del OBS projector, evalúa reglas en orden de prioridad,
    y manda 1 hotkey máximo por ciclo (la más urgente que aplique).
    """
    hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
    if not hwnd:
        print("ERROR: No se encontró ventana OBS.")
        return

    win_img = capture_window_image(hwnd)
    client_bgr = crop_client_area(win_img, hwnd)
    client_rgb = cv2.cvtColor(client_bgr, cv2.COLOR_BGR2RGB)

    now = time.time()

    # Checar en orden (urgente → leve)
    for rule in HEAL_RULES:
        hp = float(rule["hp_percent"])
        hotkey = rule["hotkey"]
        cooldown = float(rule["cooldown"])
        name = rule["name"]

        target_x = int(x0_rel + (BAR_LENGTH_PX * (hp / 100.0)))
        color = get_pixel_color_at_rel(client_rgb, target_x, y_bar)

        if color is None:
            # Si se sale del área, salimos (algo raro con coords)
            print(f"[{time.strftime('%H:%M:%S')}] Fuera de rango: {name} → X={target_x}, Y={y_bar}")
            return

        diff = color_is_different(color)
        ok_text = "DIFERENTE ✅" if diff else "OK"

        # Si aplica heal (HP por debajo de ese %)
        if diff:
            # cooldown por regla
            if (now - _last_sent[name]) >= cooldown:
                send_hotkey_once(hotkey)
                _last_sent[name] = now
                print(f"[{time.strftime('%H:%M:%S')}] {name} | HP<{hp:.0f}% → X={target_x}, Y={y_bar} → Color:{color} → {ok_text}")
                print(f"   ↳ Hotkey enviada: {hotkey}")
            else:
                # En cooldown, igual mostramos debug si quieres
                print(f"[{time.strftime('%H:%M:%S')}] {name} | HP<{hp:.0f}% → X={target_x}, Y={y_bar} → Color:{color} → {ok_text} (cooldown)")
            # IMPORTANTE: solo 1 acción por ciclo (la más urgente encontrada)
            return

    # Si ninguna regla disparó, está OK en todas
    # (Opcional) imprime solo si quieres spam de logs:
    # print(f"[{time.strftime('%H:%M:%S')}] Todo OK (no heal).")
    return


if __name__ == "__main__":
    print("Iniciando SuperMonk Healing Monitor...")
    print(f"Buscando heart.png y calculando barra de vida (+{OFFSET_TO_X0} y +{BAR_LENGTH_PX} píxeles)...")

    if not locate_heart_once():
        print("No se pudo localizar el corazón. Ejecuta el locator primero o verifica heart.png")
        raise SystemExit(1)

    print("\nPrioridades activas:")
    for r in HEAL_RULES:
        print(f" - {r['name']}: dispara si HP < {r['hp_percent']}% | hotkey={r['hotkey']} | cooldown={r['cooldown']}s")

    print(f"\nColor esperado: {EXPECTED_COLOR} (±{COLOR_TOLERANCE})")
    print(f"Solo enviará hotkeys si Tibia está en foreground (titulo contiene/empieza con: '{TIBIA_TITLE_PREFIX}')")
    print(f"Polling: cada {POLL_SECONDS}s\n")

    try:
        while True:
            if tibia_is_foreground():
                heal_loop_once()
            # si Tibia NO está al frente, no hace nada (pausa el healing)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n\nMonitoreo detenido por el usuario.")
