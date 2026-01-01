# overlay_hunt.py
import json
import threading
import tkinter as tk
from pathlib import Path

import win32gui
from PIL import Image, ImageTk, ImageSequence


def is_foreground_title_contains(substring: str) -> bool:
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or ""
        return substring.lower() in title.lower()
    except Exception:
        return False


class GifOverlay:
    def __init__(self, gif_path: str, x: int = 100, y: int = 100, scale: float = 1.0, save_path: str | None = None):
        self.gif_path = gif_path
        self.scale = float(scale) if scale else 1.0

        self._save_path = Path(save_path) if save_path else None

        self._root = None
        self._win = None
        self._canvas = None
        self._img_item = None
        self._border_item = None

        self._visible = True
        self._border_color = "#39FF14"

        self._frames = []
        self._durations = []
        self._frame_idx = 0

        self._dragging = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        self._x = int(x)
        self._y = int(y)

        self._ready = threading.Event()

        self._load_position_if_any()

    def start(self):
        t = threading.Thread(target=self._tk_thread, daemon=True)
        t.start()
        self._ready.wait(timeout=10)  # Aumentado timeout por si el GIF es grande

    def show(self):
        self._visible = True
        self._safe_ui(self._ui_show)

    def hide(self):
        self._visible = False
        self._safe_ui(self._ui_hide)

    def set_border_color(self, color_hex: str):
        self._border_color = color_hex
        self._safe_ui(self._ui_apply_border)

    def _load_position_if_any(self):
        if not self._save_path:
            return
        try:
            if self._save_path.exists():
                data = json.loads(self._save_path.read_text(encoding="utf-8"))
                self._x = int(data.get("x", self._x))
                self._y = int(data.get("y", self._y))
        except Exception:
            pass

    def _save_position(self):
        if not self._save_path:
            return
        try:
            self._save_path.write_text(
                json.dumps({"x": self._x, "y": self._y}),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _safe_ui(self, fn):
        try:
            if self._root and self._root.winfo_exists():
                self._root.after(0, fn)
        except Exception:
            pass

    def _tk_thread(self):
        self._root = tk.Tk()
        self._root.withdraw()

        self._win = tk.Toplevel(self._root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-transparentcolor", "gray17")
        self._win.config(bg="gray17")
        self._win.geometry(f"+{self._x}+{self._y}")

        self._canvas = tk.Canvas(self._win, bg="gray17", highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)

        # === PRIMERO CARGAR FRAMES ===
        self._load_gif_frames()

        # === LUEGO CONSTRUIR LA ESCENA ===
        if self._frames:
            self._build_scene()
        else:
            print(f"⚠️ No se pudieron cargar los frames del GIF: {self.gif_path}")

        # Click derecho para arrastrar
        self._win.bind("<ButtonPress-3>", self._on_right_down)
        self._win.bind("<B3-Motion>", self._on_right_move)
        self._win.bind("<ButtonRelease-3>", self._on_right_up)
        self._canvas.bind("<ButtonPress-3>", self._on_right_down)
        self._canvas.bind("<B3-Motion>", self._on_right_move)
        self._canvas.bind("<ButtonRelease-3>", self._on_right_up)

        if not self._visible:
            self._win.withdraw()

        self._ready.set()
        self._animate()
        self._root.mainloop()

    def _load_gif_frames(self):
        try:
            im = Image.open(self.gif_path)
            self._frames = []
            self._durations = []

            for frame in ImageSequence.Iterator(im):
                f = frame.convert("RGBA")
                if self.scale != 1.0:
                    w, h = f.size
                    nw = max(1, int(w * self.scale))
                    nh = max(1, int(h * self.scale))
                    f = f.resize((nw, nh), Image.NEAREST)
                photo = ImageTk.PhotoImage(f, master=self._root)
                self._frames.append(photo)
                self._durations.append(int(frame.info.get("duration", 60)) or 60)

            if not self._frames:
                print(f"⚠️ GIF vacío o corrupto: {self.gif_path}")
        except Exception as e:
            print(f"❌ Error cargando GIF {self.gif_path}: {e}")
            self._frames = []

    def _build_scene(self):
        if not self._frames:
            return

        w = self._frames[0].width()
        h = self._frames[0].height()
        pad = 6
        cw = w + pad * 2
        ch = h + pad * 2

        self._canvas.config(width=cw, height=ch)
        self._win.geometry(f"{cw}x{ch}+{self._x}+{self._y}")

        self._border_item = self._canvas.create_rectangle(
            1, 1, cw - 1, ch - 1,
            outline=self._border_color,
            width=3
        )

        self._img_item = self._canvas.create_image(pad, pad, anchor="nw", image=self._frames[0])

    def _ui_apply_border(self):
        if self._canvas and self._border_item:
            self._canvas.itemconfig(self._border_item, outline=self._border_color)

    def _ui_show(self):
        if self._win:
            self._win.deiconify()

    def _ui_hide(self):
        if self._win:
            self._win.withdraw()

    def _animate(self):
        if not self._win or not self._frames:
            return

        try:
            self._canvas.itemconfig(self._img_item, image=self._frames[self._frame_idx])
            delay = self._durations[self._frame_idx] if self._durations else 60
            self._frame_idx = (self._frame_idx + 1) % len(self._frames)
            self._root.after(max(20, delay), self._animate)
        except Exception:
            pass  # Evita crash si la ventana se cierra

    def _on_right_down(self, event):
        try:
            self._dragging = True
            self._drag_offset_x = event.x_root - self._win.winfo_x()
            self._drag_offset_y = event.y_root - self._win.winfo_y()
        except Exception:
            self._dragging = False

    def _on_right_move(self, event):
        if not self._dragging:
            return
        try:
            nx = event.x_root - self._drag_offset_x
            ny = event.y_root - self._drag_offset_y
            self._x, self._y = int(nx), int(ny)
            self._win.geometry(f"+{self._x}+{self._y}")
        except Exception:
            pass

    def _on_right_up(self, event):
        if not self._dragging:
            return
        self._dragging = False
        self._save_position()