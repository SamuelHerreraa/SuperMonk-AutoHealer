import time
import tkinter as tk
from tkinter import ttk
import win32gui
import win32ui
import win32con
from PIL import Image
import json
import os

OBS_TITLE_PREFIX = "Windowed Projector (Source)"

# Archivo opcional para guardar coordenada relativa del cursor (si lo quieres)
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(ROOT, "obs_rel_cursor.json")

# --- Todas tus funciones originales (find_window_by_prefix, get_cursor_pos, etc.) ---
# (Las dejo iguales, solo copio las necesarias para el cambio visual)

def find_window_by_prefix(prefix: str):
    found = []
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if title.startswith(prefix):
                found.append(hwnd)
    win32gui.EnumWindows(enum_cb, None)
    return found[0] if found else None

def get_cursor_pos():
    return win32gui.GetCursorPos()

def get_screen_pixel_rgb(x, y):
    hdc = win32gui.GetDC(0)
    try:
        color = win32gui.GetPixel(hdc, x, y)
        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF
        return (r, g, b)
    finally:
        win32gui.ReleaseDC(0, hdc)

def capture_window_image(hwnd):
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
        result = win32gui.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
        if result != 1:
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

def get_obs_client_geometry(hwnd):
    wL, wT, wR, wB = win32gui.GetWindowRect(hwnd)
    cL, cT, cR, cB = win32gui.GetClientRect(hwnd)
    cw = max(1, cR - cL)
    ch = max(1, cB - cT)
    cx, cy = win32gui.ClientToScreen(hwnd, (0, 0))
    return (wL, wT, wR, wB), (cx, cy), (cw, ch)

# --- Fin de funciones originales ---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SuperMonk - Pixel Inspector (OBS)")
        self.geometry("480x240")
        self.resizable(False, False)

        self.obs_hwnd = None
        self.last_obs_capture_time = 0.0
        self.obs_img = None

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Buscando ventana OBS...")
        ttk.Label(frm, textvariable=self.status_var).pack(anchor="w")

        sep = ttk.Separator(frm)
        sep.pack(fill="x", pady=8)

        self.global_pos_var = tk.StringVar(value="Global: X=0, Y=0")
        self.rel_pos_var = tk.StringVar(value="OBS Rel: X=?, Y=?")
        ttk.Label(frm, textvariable=self.global_pos_var).pack(anchor="w")
        ttk.Label(frm, textvariable=self.rel_pos_var).pack(anchor="w", pady=(0, 10))

        colors_row = ttk.Frame(frm)
        colors_row.pack(fill="x")

        # === Color Global ===
        gbox = ttk.Frame(colors_row)
        gbox.pack(side="left", expand=True, fill="x", padx=(0, 10))

        ttk.Label(gbox, text="RGB Global (pantalla):").pack(anchor="w")
        self.g_rgb = tk.StringVar(value="N/A")
        self.g_swatch = tk.Canvas(gbox, width=60, height=30, highlightthickness=1, highlightbackground="#666")
        self.g_swatch.pack(anchor="w", pady=4)
        ttk.Label(gbox, textvariable=self.g_rgb).pack(anchor="w")

        # === Color OBS ===
        obox = ttk.Frame(colors_row)
        obox.pack(side="left", expand=True, fill="x")

        ttk.Label(obox, text="RGB OBS (ventana):").pack(anchor="w")
        self.o_rgb = tk.StringVar(value="N/A")
        self.o_swatch = tk.Canvas(obox, width=60, height=30, highlightthickness=1, highlightbackground="#666")
        self.o_swatch.pack(anchor="w", pady=4)
        ttk.Label(obox, textvariable=self.o_rgb).pack(anchor="w")

        note = ttk.Label(frm, text="Nota: OBS NO se traerá al frente. Si no existe o cambia título → N/A")
        note.pack(anchor="w", pady=(12, 0))

        # Opcional: guardar coordenada relativa en JSON cada vez que cambia
        self.last_rel = None

        self.after(50, self.tick)

    def ensure_obs_hwnd(self):
        if self.obs_hwnd and win32gui.IsWindow(self.obs_hwnd):
            return True
        self.obs_hwnd = find_window_by_prefix(OBS_TITLE_PREFIX)
        return self.obs_hwnd is not None

    def update_swatches(self, global_rgb=None, obs_rgb=None):
        # Global RGB
        if global_rgb:
            r, g, b = global_rgb
            self.g_rgb.set(f"({r}, {g}, {b})")
            color = f"#{r:02X}{g:02X}{b:02X}"
            self.g_swatch.delete("all")
            self.g_swatch.create_rectangle(0, 0, 60, 30, fill=color, outline=color)
        else:
            self.g_rgb.set("N/A")
            self.g_swatch.delete("all")
            self.g_swatch.create_rectangle(0, 0, 60, 30, fill="#222222", outline="#222222")

        # OBS RGB
        if obs_rgb:
            r, g, b = obs_rgb
            self.o_rgb.set(f"({r}, {g}, {b})")
            color = f"#{r:02X}{g:02X}{b:02X}"
            self.o_swatch.delete("all")
            self.o_swatch.create_rectangle(0, 0, 60, 30, fill=color, outline=color)
        else:
            self.o_rgb.set("N/A")
            self.o_swatch.delete("all")
            self.o_swatch.create_rectangle(0, 0, 60, 30, fill="#222222", outline="#222222")

    def tick(self):
        x, y = get_cursor_pos()
        self.global_pos_var.set(f"Global: X={x}, Y={y}")

        g_rgb = get_screen_pixel_rgb(x, y)

        obs_rgb = None
        rel_x, rel_y = None, None

        if not self.ensure_obs_hwnd():
            self.status_var.set("OBS: No encontrada. Abre 'Windowed Projector (Source)'.")
            self.rel_pos_var.set("OBS Rel: X=?, Y=? (N/A)")
            self.update_swatches(g_rgb, None)
            self.after(50, self.tick)
            return

        try:
            _, (cx, cy), (cw, ch) = get_obs_client_geometry(self.obs_hwnd)
            rx = x - cx
            ry = y - cy

            inside = (0 <= rx < cw) and (0 <= ry < ch)
            if inside:
                self.rel_pos_var.set(f"OBS Rel: X={rx}, Y={ry}")
                rel_x, rel_y = int(rx), int(ry)
            else:
                self.rel_pos_var.set(f"OBS Rel: (fuera) X={rx}, Y={ry}")

            self.status_var.set("OBS: OK (capturando sin focus)")

            now = time.time()
            if self.obs_img is None or (now - self.last_obs_capture_time) > 0.10:
                self.obs_img = capture_window_image(self.obs_hwnd)
                self.last_obs_capture_time = now

            if inside and self.obs_img is not None:
                wL, wT, wR, wB = win32gui.GetWindowRect(self.obs_hwnd)
                win_w = max(1, wR - wL)
                win_h = max(1, wB - wT)
                offx = win32gui.ClientToScreen(self.obs_hwnd, (0, 0))[0] - wL
                offy = win32gui.ClientToScreen(self.obs_hwnd, (0, 0))[1] - wT
                px = int(offx + rx)
                py = int(offy + ry)
                if 0 <= px < win_w and 0 <= py < win_h:
                    obs_rgb = self.obs_img.getpixel((px, py))

            # === GUARDAR COORDENADA RELATIVA EN JSON (solo si cambió y está dentro) ===
            if inside and (rel_x, rel_y) != self.last_rel:
                self.last_rel = (rel_x, rel_y)
                payload = {
                    "rel_x": rel_x,
                    "rel_y": rel_y,
                    "ts": time.time()
                }
                with open(OUT_JSON, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)

        except Exception as e:
            self.status_var.set(f"OBS: Error → {str(e)}")
            self.rel_pos_var.set("OBS Rel: error")
            obs_rgb = None

        self.update_swatches(g_rgb, obs_rgb)
        self.after(50, self.tick)


if __name__ == "__main__":
    app = App()
    app.mainloop()