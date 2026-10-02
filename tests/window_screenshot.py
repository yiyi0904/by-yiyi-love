"""把主窗口截成图片，用于肉眼检查界面风格。"""

from __future__ import annotations

import ctypes
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win32con
import win32gui
import win32ui
from PIL import Image

from yunx.downloader import DlState, Download
from yunx.models import DownloadLink, PanFile
from yunx.ui.main_window import MainWindow

BASE = os.path.dirname(os.path.abspath(__file__))


def capture(hwnd: int, path: str) -> tuple[int, int]:
    """直接从屏幕抓客户区，避免 PrintWindow 的偏移。"""
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
    want = sys.argv[1] if len(sys.argv) > 1 else "dark"
    from yunx.ui import theme as theme_mod

    theme_mod.set_palette(want)
    app = MainWindow()
    if want != theme_mod.palette_name():
        theme_mod.set_palette(want)
        app._rebuild_ui()  # noqa: SLF001
    app.link_var.set("https://pan.quark.cn/s/35d3c89573ec 提取码: 1234")
    app._on_link_changed()  # noqa: SLF001
    app.files = [
        PanFile(fid="1", name="客户端", is_dir=True),
        PanFile(fid="2", name="DLC内容", is_dir=True),
        PanFile(fid="3", name="游玩说明.pdf", size=57157),
        PanFile(fid="4", name="VestigesOfThePresent 1.20.1-1.7.1.jar", size=18801395),
    ]
    app._render_files()  # noqa: SLF001
    app.tree.selection_set(["2"])
    app.set_status("解析成功：登神者：天阶咏叹（4 项）")

    # 造两个示例任务卡片，展示不同状态
    for name, ratio, state, speed in (
        ("VestigesOfThePresent 1.20.1-1.7.1.jar", 0.62, DlState.RUNNING, 5.4),
        ("游玩说明.pdf", 1.0, DlState.COMPLETED, 0),
    ):
        link = DownloadLink(url="http://example.com/x.bin", filename=name, size=18801395)
        task = Download(f"demo-{name}", link, os.path.expanduser("~"), threads=16)
        task.state = state
        task.total = 18801395
        task.downloaded = int(18801395 * ratio)
        task.workers = 16
        card = __import__("yunx.ui.widgets", fromlist=["TaskCard"]).TaskCard(
            app.dl_scroll.body,
            task,
            on_pause=lambda _t: None,
            on_resume=lambda _t: None,
            on_cancel=lambda _t: None,
            on_remove=lambda _t: None,
        )
        card.pack(fill="x", pady=5)
        app.tasks[task.id] = task
        app.cards[task.id] = card
        card.refresh()
    app.empty_hint.pack_forget()

    app.lift()
    app.attributes("-topmost", True)
    app.update_idletasks()
    for _ in range(30):
        app.update()
        time.sleep(0.03)

    # Tk 的 winfo_id() 就是实际绘制内容的窗口，直接抓它的客户区最准
    target = app.winfo_id()
    out = os.path.join(BASE, f"window_ui_{want}.png")
    print("截图:", out, capture(target, out))
    app._on_close()  # noqa: SLF001
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
