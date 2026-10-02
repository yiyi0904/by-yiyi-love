"""通用小工具。"""

from __future__ import annotations

import os
import re
import sys
import time

_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def human_size(n: int | float | None) -> str:
    """字节数转可读文本。"""
    if n is None:
        return "-"
    try:
        value = float(n)
    except (TypeError, ValueError):
        return "-"
    if value < 0:
        return "-"
    units = ("B", "KB", "MB", "GB", "TB")
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(value)} B"
    return f"{value:.2f} {units[idx]}"


def human_speed(bps: float) -> str:
    if bps <= 0:
        return "0 B/s"
    return f"{human_size(bps)}/s"


def human_duration(seconds: float) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def sanitize_filename(name: str, fallback: str = "unnamed") -> str:
    """清理为合法的 Windows 文件名。"""
    name = (name or "").strip().replace("\r", " ").replace("\n", " ")
    name = _ILLEGAL.sub("_", name).strip(" .")
    if not name:
        return fallback
    stem = name.split(".")[0].upper()
    if stem in _RESERVED:
        name = "_" + name
    return name[:180]


def unique_path(path: str) -> str:
    """若目标已存在则追加 (1)、(2)…。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{base} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def app_data_dir() -> str:
    """配置/任务数据目录。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "YiXi-PC")
    os.makedirs(path, exist_ok=True)
    return path


def asset_path(name: str) -> str:
    """定位随程序分发的资源文件（打包后从解包目录读取）。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def apply_window_icon(window) -> None:
    """给 Tk 窗口设置图标：优先 .ico，其次 .png。"""
    ico = asset_path("app.ico")
    if os.path.exists(ico):
        try:
            window.iconbitmap(ico)
            return
        except Exception:  # noqa: BLE001
            pass
    png = asset_path("icon.png")
    if not os.path.exists(png):
        return
    try:
        import tkinter as tk

        image = tk.PhotoImage(file=png)
        window.iconphoto(True, image)
        setattr(window, "_icon_photo_ref", image)  # 防止被垃圾回收
    except Exception:  # noqa: BLE001
        pass


def default_download_dir() -> str:
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        return downloads
    return os.path.expanduser("~")


def open_in_explorer(path: str, select: bool = False) -> None:
    """在资源管理器中打开目录 / 定位文件。"""
    if sys.platform != "win32":
        return
    if select and os.path.isfile(path):
        os.system(f'explorer /select,"{path}"')
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if folder:
            os.startfile(folder)  # type: ignore[attr-defined]


class RateMeter:
    """滑动窗口测速。"""

    def __init__(self, window: float = 2.0) -> None:
        self.window = window
        self._samples: list[tuple[float, int]] = []

    def add(self, nbytes: int) -> None:
        now = time.monotonic()
        self._samples.append((now, nbytes))
        cutoff = now - self.window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    def speed(self) -> float:
        if not self._samples:
            return 0.0
        now = time.monotonic()
        cutoff = now - self.window
        total = sum(n for t, n in self._samples if t >= cutoff)
        span = max(now - max(cutoff, self._samples[0][0]), 0.2)
        return total / span
