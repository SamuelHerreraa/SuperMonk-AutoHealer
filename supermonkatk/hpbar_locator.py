import os
import json
import cv2
import numpy as np
import win32gui
import win32ui
import win32con

# ================= CONFIG =================
OBS_TITLE_PREFIX = "Windowed Projector (Source)"
IMG_DIR = "img"
TEMPLATE_FILE = "hp.png"
OUT_JSON = "heart_center.json"
THRESHOLD = 0.50
# ==========================================


def find_obs_window(title_sub):
    result = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_sub.lower() in title.lower():
                result.append(hwnd)
        return True

    win32gui.EnumWindows(enum_cb, None)
    return result[0] if result else None


def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

    img = np.frombuffer(bmp.GetBitmapBits(True), dtype=np.uint8)
    img = img.reshape((h, w, 4))[:, :, :3]

    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(root, IMG_DIR, TEMPLATE_FILE)
    out_path = os.path.join(root, IMG_DIR, OUT_JSON)

    hwnd = find_obs_window(OBS_TITLE_PREFIX)
    if not hwnd:
        print("OBS window not found")
        return

    if not os.path.exists(template_path):
        print("Template not found")
        return

    screen = capture_window(hwnd)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < THRESHOLD:
        print("Heart not found")
        return

    h, w = template.shape
    cx = max_loc[0] + w // 2
    cy = max_loc[1] + h // 2

    # 👉 SOLO esto
    print(f"{cx} {cy}")

    os.makedirs(os.path.join(root, IMG_DIR), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"x": cx, "y": cy}, f, indent=2)


if __name__ == "__main__":
    main()
