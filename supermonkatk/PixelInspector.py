import time
import tkinter as tk
from tkinter import ttk

import win32gui
import win32ui
import win32con

from PIL import Image


OBS_TITLE_PREFIX = "Windowed Projector (Source)"


def find_window_by_prefix(prefix: str):
    """Encuentra la primera ventana cuyo título empieza con prefix."""
    found = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if title.startswith(prefix):
                found.append(hwnd)

    win32gui.EnumWindows(enum_cb, None)
    return found[0] if found else None


def get_cursor_pos():
    return win32gui.GetCursorPos()  # (x, y)


def get_screen_pixel_rgb(x, y):
    """Color desde pantalla (lo que esté arriba)."""
    hdc = win32gui.GetDC(0)
    try:
        color = win32gui.GetPixel(hdc, x, y)  # 0x00bbggrr
        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF
        return (r, g, b)
    finally:
        win32gui.ReleaseDC(0, hdc)


def capture_window_image(hwnd):
    """
    Captura la ventana sin traerla al frente usando PrintWindow.
    Devuelve una PIL.Image (RGB) de TODO el rect del window (incluye bordes).
    """
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w = max(1, right - left)
    h = max(1, bottom - top)

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bitmap)

    # PrintWindow (funciona aun si está detrás, normalmente)
    # Nota: algunas ventanas pueden fallar según GPU/overlay; OBS projector suele funcionar bien.
    try:
        # 0 = comportamiento normal; si quieres probar render full content en Win8+ usa 2
        result = win32gui.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
        if result != 1:
            # fallback: BitBlt (puede fallar si está completamente oculta)
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
        1
    )

    # cleanup
    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img


def get_obs_client_geometry(hwnd):
    """
    Regresa:
      - window_rect (L,T,R,B) del window
      - client_origin_screen (cx, cy) de la esquina superior izquierda del cliente en coordenadas pantalla
      - client_size (cw, ch)
    """
    wL, wT, wR, wB = win32gui.GetWindowRect(hwnd)

    cL, cT, cR, cB = win32gui.GetClientRect(hwnd)  # relativo a cliente
    cw = max(1, cR - cL)
    ch = max(1, cB - cT)

    # Convertir (0,0) del cliente a coordenadas pantalla
    cx, cy = win32gui.ClientToScreen(hwnd, (0, 0))

    return (wL, wT, wR, wB), (cx, cy), (cw, ch)


def rgb_to_hex(rgb):
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SuperMonk - Pixel Inspector (OBS)")
        self.geometry("460x220")
        self.resizable(False, False)

        self.obs_hwnd = None
        self.last_obs_capture_time = 0.0
        self.obs_img = None

        # UI
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Buscando ventana OBS...")
        ttk.Label(frm, textvariable=self.status_var).pack(anchor="w")

        sep = ttk.Separator(frm)
        sep.pack(fill="x", pady=8)

        self.global_pos_var = tk.StringVar(value="Global: X=0, Y=0")
        self.rel_pos_var = tk.StringVar(value="OBS Rel: X=?, Y=?")
        ttk.Label(frm, textvariable=self.global_pos_var).pack(anchor="w")
        ttk.Label(frm, textvariable=self.rel_pos_var).pack(anchor="w", pady=(0, 8))

        colors_row = ttk.Frame(frm)
        colors_row.pack(fill="x")

        # Global color
        gbox = ttk.Frame(colors_row)
        gbox.pack(side="left", expand=True, fill="x", padx=(0, 10))

        ttk.Label(gbox, text="Color Global (pantalla):").pack(anchor="w")
        self.g_hex = tk.StringVar(value="N/A")
        self.g_swatch = tk.Canvas(gbox, width=60, height=30, highlightthickness=1, highlightbackground="#666")
        self.g_swatch.pack(anchor="w", pady=4)
        ttk.Label(gbox, textvariable=self.g_hex).pack(anchor="w")

        # OBS color
        obox = ttk.Frame(colors_row)
        obox.pack(side="left", expand=True, fill="x")

        ttk.Label(obox, text="Color OBS (ventana):").pack(anchor="w")
        self.o_hex = tk.StringVar(value="N/A")
        self.o_swatch = tk.Canvas(obox, width=60, height=30, highlightthickness=1, highlightbackground="#666")
        self.o_swatch.pack(anchor="w", pady=4)
        ttk.Label(obox, textvariable=self.o_hex).pack(anchor="w")

        note = ttk.Label(frm, text="Nota: OBS NO se traerá al frente. Si OBS no existe o cambia el título, marcará N/A.")
        note.pack(anchor="w", pady=(10, 0))

        # Start loop
        self.after(50, self.tick)

    def ensure_obs_hwnd(self):
        if self.obs_hwnd and win32gui.IsWindow(self.obs_hwnd):
            return True
        self.obs_hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
        return self.obs_hwnd is not None

    def update_swatches(self, global_rgb=None, obs_rgb=None):
        if global_rgb:
            hx = rgb_to_hex(global_rgb)
            self.g_hex.set(hx)
            self.g_swatch.delete("all")
            self.g_swatch.create_rectangle(0, 0, 60, 30, fill=hx, outline=hx)
        else:
            self.g_hex.set("N/A")
            self.g_swatch.delete("all")
            self.g_swatch.create_rectangle(0, 0, 60, 30, fill="#222222", outline="#222222")

        if obs_rgb:
            hx = rgb_to_hex(obs_rgb)
            self.o_hex.set(hx)
            self.o_swatch.delete("all")
            self.o_swatch.create_rectangle(0, 0, 60, 30, fill=hx, outline=hx)
        else:
            self.o_hex.set("N/A")
            self.o_swatch.delete("all")
            self.o_swatch.create_rectangle(0, 0, 60, 30, fill="#222222", outline="#222222")

    def tick(self):
        x, y = get_cursor_pos()
        self.global_pos_var.set(f"Global: X={x}, Y={y}")

        # Global color (pantalla real)
        try:
            g_rgb = get_screen_pixel_rgb(x, y)
        except Exception:
            g_rgb = None

        obs_rgb = None

        if not self.ensure_obs_hwnd():
            self.status_var.set("OBS: No encontrada. Abre 'Windowed Projector (Source)'.")
            self.rel_pos_var.set("OBS Rel: X=?, Y=? (N/A)")
            self.update_swatches(g_rgb, None)
            self.after(50, self.tick)
            return

        # Geometría OBS
        try:
            _, (cx, cy), (cw, ch) = get_obs_client_geometry(self.obs_hwnd)
            rx = x - cx
            ry = y - cy

            inside = (0 <= rx < cw) and (0 <= ry < ch)
            if inside:
                self.rel_pos_var.set(f"OBS Rel: X={rx}, Y={ry}")
            else:
                self.rel_pos_var.set(f"OBS Rel: (fuera) X={rx}, Y={ry}")

            self.status_var.set("OBS: OK (capturando sin focus)")

            # Captura OBS (no cada tick para no matar CPU)
            now = time.time()
            if self.obs_img is None or (now - self.last_obs_capture_time) > 0.10:  # 10 fps
                self.obs_img = capture_window_image(self.obs_hwnd)
                self.last_obs_capture_time = now

            if inside and self.obs_img is not None:
                # La captura es del window completo; necesitamos mapear cliente dentro de esa imagen.
                wL, wT, wR, wB = win32gui.GetWindowRect(self.obs_hwnd)
                win_w = max(1, wR - wL)
                win_h = max(1, wB - wT)

                # Origen cliente en pantalla vs origen window en pantalla => offset cliente dentro del bitmap
                client_origin_screen = win32gui.ClientToScreen(self.obs_hwnd, (0, 0))
                offx = client_origin_screen[0] - wL
                offy = client_origin_screen[1] - wT

                px = int(offx + rx)
                py = int(offy + ry)

                if 0 <= px < win_w and 0 <= py < win_h:
                    obs_rgb = self.obs_img.getpixel((px, py))
        except Exception:
            self.status_var.set("OBS: Error capturando. (¿cambió el título o permisos?)")
            self.rel_pos_var.set("OBS Rel: X=?, Y=? (error)")
            obs_rgb = None

        self.update_swatches(g_rgb, obs_rgb)
        self.after(50, self.tick)


if __name__ == "__main__":
    # UI theme básico
    try:
        from tkinter import font as tkfont
        # Forzar un tamaño legible
    except Exception:
        pass

    app = App()
    app.mainloop()