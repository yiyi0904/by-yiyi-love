"""把账号对话框截成图片，肉眼确认按钮可见。"""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win32con
import win32gui
import win32ui
from PIL import Image

from yunx.config import Config
from yunx.models import Platform
from yunx.ui import theme
from yunx.ui.dialogs import CredentialDialog, SettingsDialog

BASE = os.path.dirname(os.path.abspath(__file__))


def capture(hwnd: int, path: str) -> tuple[int, int]:
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    _l, _t, width, height = win32gui.GetClientRect(hwnd)
    desktop = win32gui.GetWindowDC(0)
    mfc_dc = win32ui.CreateDCFromHandle(desktop)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)
    save_dc.BitBlt((0, 0), (width, height), mfc_dc, (left, top), win32con.SRCCOPY)
    info = bitmap.GetInfo()
    bits = bitmap.GetBitmapBits(True)
    image = Image.frombuffer(
        "RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1
    )
    image.save(path)
    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(0, desktop)
    return image.size


def main() -> int:
    # 与打包后的 app.py 保持一致：先开 DPI 感知，字体缩放会影响布局
    import app

    app._enable_dpi_awareness()

    target_name = sys.argv[1] if len(sys.argv) > 1 else "xunlei"
    palette = sys.argv[2] if len(sys.argv) > 2 else "dark"
    theme.set_palette(palette)
    out_name = f"dialog_{target_name}_{palette}.png"

    root = tk.Tk()
    root.withdraw()
    theme.apply_theme(root)
    if target_name == "settings":
        dialog = SettingsDialog(root, Config())
    elif target_name == "details":
        from yunx.ui.details import DetailsDialog

        dialog = DetailsDialog(root, Config())
    else:
        dialog = CredentialDialog(root, Config())
        dialog._select(Platform(target_name))  # noqa: SLF001
    dialog.deiconify()
    dialog.lift()
    dialog.attributes("-topmost", True)
    for _ in range(20):
        root.update()
        time.sleep(0.05)

    target = dialog.winfo_id()
    out = os.path.join(BASE, out_name)
    size = capture(target, out)
    print("截图:", out, size)
    dialog.destroy()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
