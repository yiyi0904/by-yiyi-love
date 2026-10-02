"""动画与绘图小工具（纯 tkinter 实现，不引入额外依赖）。"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

FRAME_MS = 16  # ≈60fps


def enable_smooth_timers() -> None:
    """把 Windows 计时器精度提到 1ms。

    系统默认精度是 15.6ms，`after(16)` 常被拖到 ~31ms —— 这正是弹窗动画卡顿的根因。
    进程退出时由系统自动归还，无需手动结束。
    """
    try:
        import ctypes

        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# 颜色
# --------------------------------------------------------------------------
def to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb)


def mix(color_a: str, color_b: str, ratio: float) -> str:
    """在两种颜色之间插值，ratio=0 取 a，1 取 b。"""
    ratio = max(0.0, min(1.0, ratio))
    a, b = to_rgb(color_a), to_rgb(color_b)
    return to_hex(tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3)))


def lighten(color: str, amount: float = 0.12) -> str:
    return mix(color, "#ffffff", amount)


def darken(color: str, amount: float = 0.12) -> str:
    return mix(color, "#000000", amount)


# --------------------------------------------------------------------------
# 绘图
# --------------------------------------------------------------------------
def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius: float, **kwargs):
    """在 canvas 上画圆角矩形（由 4 个圆 + 2 个矩形拼成）。"""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    items = []
    items.append(canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **kwargs))
    items.append(canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **kwargs))
    if radius > 0:
        items += [
            canvas.create_oval(x1, y1, x1 + 2 * radius, y1 + 2 * radius, **kwargs),
            canvas.create_oval(x2 - 2 * radius, y1, x2, y1 + 2 * radius, **kwargs),
            canvas.create_oval(x1, y2 - 2 * radius, x1 + 2 * radius, y2, **kwargs),
            canvas.create_oval(x2 - 2 * radius, y2 - 2 * radius, x2, y2, **kwargs),
        ]
    return items


# --------------------------------------------------------------------------
# 补间
# --------------------------------------------------------------------------
class Tween:
    """把一个 0→1 的进度在 duration 毫秒内推进，逐帧回调。"""

    def __init__(
        self,
        widget: tk.Misc,
        on_frame: Callable[[float], None],
        on_done: Callable[[], None] | None = None,
        duration: int = 140,
    ) -> None:
        self.widget = widget
        self.on_frame = on_frame
        self.on_done = on_done
        self.duration = max(1, duration)
        self._job: str | None = None
        self._start: float | None = None
        self._from = 0.0
        self._to = 1.0

    def start(self, value_from: float = 0.0, value_to: float = 1.0) -> None:
        import time

        self.cancel()
        self._from, self._to = value_from, value_to
        self._start = time.monotonic()
        self._tick()

    def cancel(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:  # noqa: BLE001
                pass
            self._job = None

    def _tick(self) -> None:
        import time

        elapsed = (time.monotonic() - (self._start or 0)) * 1000
        ratio = min(1.0, elapsed / self.duration)
        eased = 1 - (1 - ratio) ** 3  # easeOutCubic
        value = self._from + (self._to - self._from) * eased
        try:
            self.on_frame(value)
        except Exception:  # noqa: BLE001
            return
        if ratio >= 1.0:
            self._job = None
            if self.on_done:
                try:
                    self.on_done()
                except Exception:  # noqa: BLE001
                    pass
            return
        self._job = self.widget.after(FRAME_MS, self._tick)
