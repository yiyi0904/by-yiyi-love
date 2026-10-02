"""取运行中窗口的 ICON_BIG，确认任务栏图标已生效。

用法：
    python icon_check.py                       # 检查源码运行的主窗口
    python icon_check.py <exe> [标题前缀]       # 检查打包后的 exe
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.dirname(os.path.abspath(__file__))
WM_GETICON = 0x007F
ICON_BIG = 1
GCLP_HICON = -14


def hicon_to_image(hicon: int) -> Image.Image:
    info = win32gui.GetIconInfo(hicon)
    hbm_color = info[4]
    if not hbm_color:
        hbm_color = info[3]
    if not hbm_color:
        raise RuntimeError("图标没有位图数据")
    bmp = win32ui.CreateBitmapFromHandle(hbm_color)
    bmp_info = bmp.GetInfo()
    width, height = bmp_info["bmWidth"], bmp_info["bmHeight"]
    bits = bmp.GetBitmapBits(True)
    return Image.frombuffer("RGBA", (width, height), bits, "raw", "BGRA", 0, 1)


def main() -> int:
    args = sys.argv[1:]
    exe = args[0] if args else ""
    prefix = args[1] if len(args) > 1 else "亦析 PC"
    cmd = [exe] if exe else [sys.executable, os.path.join(BASE, "app.py")]
    env = dict(os.environ)
    if len(args) > 2 and args[2].startswith("weblogin:"):
        platform = args[2].split(":", 1)[1]
        out_path = os.path.join(BASE, "icon_check_login.json")
        cmd += ["--weblogin", platform, "--out", out_path]
        env["YIXI_LOGIN_AUTOCLOSE"] = "25"
    proc = subprocess.Popen(cmd, env=env)
    try:
        found: list[int] = []
        for _ in range(80):
            time.sleep(0.5)

            def visit(handle, _acc):
                if win32gui.IsWindowVisible(handle):
                    title = win32gui.GetWindowText(handle)
                    if title.startswith(prefix):
                        found.append(handle)
                return True

            win32gui.EnumWindows(visit, None)
            if found:
                break
        if not found:
            print(f"找不到标题以「{prefix}」开头的窗口")
            return 1
        hwnd = found[0]

        result: dict = {"title": win32gui.GetWindowText(hwnd)}
        hicon = win32gui.SendMessage(hwnd, WM_GETICON, ICON_BIG, 0)
        result["WM_GETICON/BIG"] = bool(hicon)
        if not hicon:
            hicon = win32gui.GetClassLongPtr(hwnd, GCLP_HICON)
            result["GCLP_HICON"] = bool(hicon)
        if hicon:
            image = hicon_to_image(hicon)
            out = os.path.join(BASE, "window_icon.png")
            image.save(out)
            result["size"] = image.size
            result["md5"] = hashlib.md5(image.tobytes()).hexdigest()[:16]
            print("saved", out)
        print(result, flush=True)
        return 0
    finally:
        proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
