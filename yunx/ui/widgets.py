"""自定义控件：动画按钮、流光进度条、任务卡片、忙碌指示器、滚动容器。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..downloader import DlState, Download
from ..util import human_duration, human_size, human_speed, open_in_explorer
from . import theme
from .anim import Tween, darken, lighten, mix, rounded_rect

UI_FONT = "Microsoft YaHei UI"


# --------------------------------------------------------------------------
# 动画按钮
# --------------------------------------------------------------------------
class AnimatedButton(tk.Canvas):
    """圆角按钮：悬停渐变、按下回弹、禁用淡化、忙碌呼吸。"""

    @staticmethod
    def kinds() -> dict:
        """按当前配色现算按钮风格（主题切换后立即生效）。"""
        light = theme.is_light()
        return {
            "accent": {
                "bg": theme.ACCENT,
                "fg": theme.ON_ACCENT,
                "hover": theme.ACCENT_HOVER,
                "press": theme.ACCENT_DARK,
                "glow": True,
            },
            "violet": {
                "bg": theme.ACCENT_2,
                "fg": theme.ON_ACCENT,
                "hover": lighten(theme.ACCENT_2, 0.14),
                "press": darken(theme.ACCENT_2, 0.16),
                "glow": True,
            },
            "ghost": {
                "bg": theme.PANEL_ALT,
                "fg": theme.TEXT,
                "hover": theme.PANEL_HI,
                "press": theme.BORDER_SOFT,
                "glow": False,
            },
            "quiet": {
                # 比面板亮/灰一点点，保证在面板上仍然看得出是个按钮
                "bg": mix(theme.PANEL, theme.PANEL_ALT, 0.85),
                "fg": theme.TEXT_DIM,
                "hover": theme.PANEL_ALT,
                "press": theme.PANEL_HI,
                "glow": False,
            },
            "danger": {
                "bg": theme.PANEL_ALT,
                "fg": theme.DANGER,
                "hover": mix(theme.PANEL_ALT, theme.DANGER, 0.18),
                "press": mix(theme.PANEL_ALT, theme.DANGER, 0.28),
                "glow": False,
            },
            "success": {
                "bg": theme.PANEL_ALT,
                "fg": theme.SUCCESS,
                "hover": mix(theme.PANEL_ALT, theme.SUCCESS, 0.18),
                "press": mix(theme.PANEL_ALT, theme.SUCCESS, 0.28),
                "glow": False,
            },
        }

    def __init__(
        self,
        master,
        text: str = "",
        command: Callable[[], None] | None = None,
        kind: str = "ghost",
        font=None,
        height: int = 34,
        radius: int = 9,
        padx: int = 16,
        width: int | None = None,
        parent_bg: str | None = None,
    ) -> None:
        kinds = self.kinds()
        self.spec = kinds.get(kind, kinds["ghost"])
        parent_bg = parent_bg or theme.PANEL
        self.parent_bg = parent_bg
        self.font = font or (UI_FONT, 10)
        self.radius = radius
        self.padx = padx
        self._text = text
        self._command = command
        self._state = "normal"
        self._hover = 0.0
        self._pressed = False
        self._busy = False
        self._pulse = 0.0
        self._pulse_dir = 1

        measured = tk.font.Font(font=self.font).measure(text) if text else 0
        self._width = width or max(64, measured + padx * 2)
        super().__init__(
            master,
            width=self._width,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._height = height

        self._tween = Tween(self, self._on_hover_frame, duration=120)
        self._pulse_job: str | None = None

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda _e: self._render())
        self._render()

    # -- 对外 ---------------------------------------------------------------
    def cget(self, key):
        """让 cget('text') 与旧代码兼容。"""
        if key == "text":
            return self._text
        return super().cget(key)

    def set_text(self, text: str) -> None:
        self._text = text
        self._render()

    def set_enabled(self, enabled: bool) -> None:
        self._state = "normal" if enabled else "disabled"
        self.configure(cursor="hand2" if enabled else "arrow")
        self._render()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self._start_pulse()
        else:
            self._stop_pulse()
        self._render()

    # -- 交互 ---------------------------------------------------------------
    def _on_enter(self, _event=None) -> None:
        if self._state == "disabled" or self._busy:
            return
        self._tween.start(self._hover, 1.0)

    def _on_leave(self, _event=None) -> None:
        self._pressed = False
        if self._state == "disabled" or self._busy:
            return
        self._tween.start(self._hover, 0.0)

    def _on_press(self, _event=None) -> None:
        if self._state == "disabled" or self._busy:
            return
        self._pressed = True
        self._render()

    def _on_release(self, event=None) -> None:
        if self._state == "disabled" or self._busy or not self._pressed:
            return
        self._pressed = False
        self._render()
        inside = 0 <= (event.x if event else 0) <= self._width
        if inside and self._command is not None:
            try:
                self._command()
            except Exception:  # noqa: BLE001
                pass

    def _on_hover_frame(self, value: float) -> None:
        self._hover = value
        self._render()

    # -- 忙碌呼吸 -----------------------------------------------------------
    def _start_pulse(self) -> None:
        if self._pulse_job is not None:
            return
        self._step_pulse()

    def _stop_pulse(self) -> None:
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:  # noqa: BLE001
                pass
            self._pulse_job = None
        self._pulse = 0.0

    def _step_pulse(self) -> None:
        self._pulse += 0.06 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse, self._pulse_dir = 1.0, -1
        elif self._pulse <= 0.0:
            self._pulse, self._pulse_dir = 0.0, 1
        self._render()
        if self._busy:
            self._pulse_job = self.after(28, self._step_pulse)
        else:
            self._pulse_job = None

    # -- 绘制 ---------------------------------------------------------------
    def _render(self) -> None:
        try:
            width = int(self.winfo_width()) or self._width
            height = int(self.winfo_height()) or self._height
        except Exception:  # noqa: BLE001
            return
        self.delete("all")
        spec = self.spec
        base = spec["bg"]
        if self._state == "disabled":
            base = mix(base, self.parent_bg, 0.55)
        elif self._busy:
            base = mix(base, spec["hover"], 0.35 + 0.45 * self._pulse)
        elif self._pressed:
            base = spec["press"]
        elif self._hover > 0:
            base = mix(base, spec["hover"], self._hover)

        shift = 1 if self._pressed else 0
        if spec.get("glow") and self._state != "disabled":
            # 外发光：比按钮大一圈的柔和光晕
            glow_alpha = 0.30 + 0.55 * self._hover
            rounded_rect(
                self,
                0,
                0,
                width,
                height - 1,
                self.radius + 1,
                fill=mix(self.parent_bg, theme.GLOW, glow_alpha),
                outline="",
            )
        rounded_rect(
            self,
            1.5,
            shift + 2,
            width - 1.5,
            height - 2 + shift,
            self.radius,
            fill=base,
            outline="",
        )
        if spec.get("glow"):
            rounded_rect(
                self,
                1.5,
                shift + 2,
                width - 1.5,
                height - 2 + shift,
                self.radius,
                fill="",
                outline=lighten(base, 0.18),
            )
        # 顶部高光
        self.create_line(
            self.radius,
            shift + 3,
            width - self.radius,
            shift + 3,
            fill=lighten(base, 0.16) if spec.get("glow") else lighten(base, 0.10),
        )
        fg = spec["fg"]
        if self._state == "disabled":
            fg = mix(fg, self.parent_bg, 0.6)
        self.create_text(
            width // 2,
            (height + shift) // 2,
            text=self._text,
            fill=fg,
            font=self.font,
        )


# --------------------------------------------------------------------------
# 进度条
# --------------------------------------------------------------------------
class ProgressBar(tk.Canvas):
    """带补间与流光的进度条。"""

    def __init__(self, master, height: int = 8, **kwargs) -> None:
        super().__init__(
            master,
            height=height,
            bg=theme.FIELD,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._height = height
        self._ratio = 0.0
        self._shown = 0.0
        self._color = theme.ACCENT
        self._indeterminate = False
        self._running = False
        self._sweep = 0.0
        self._sweep_job: str | None = None
        self._tween = Tween(self, self._on_tween, duration=220)
        self.bind("<Configure>", lambda _e: self._redraw())

    # -- 对外 ---------------------------------------------------------------
    def set(self, ratio: float, color: str | None = None) -> None:
        self._ratio = max(0.0, min(1.0, ratio))
        if color:
            self._color = color
        self._tween.start(self._shown, self._ratio)

    def set_now(self, ratio: float, color: str | None = None) -> None:
        self._ratio = self._shown = max(0.0, min(1.0, ratio))
        if color:
            self._color = color
        self._redraw()

    def set_indeterminate(self, active: bool) -> None:
        if active == self._indeterminate:
            return
        self._indeterminate = active
        if active:
            self._start_sweep()
        else:
            self._stop_sweep()
        self._redraw()

    def set_running(self, running: bool) -> None:
        """下载中才跑流光，避免静止时也一直重绘。"""
        self._running = running
        if running:
            self._start_sweep()
        elif not self._indeterminate:
            self._stop_sweep()

    # -- 动画 ---------------------------------------------------------------
    def _on_tween(self, value: float) -> None:
        self._shown = value
        self._redraw()

    def _start_sweep(self) -> None:
        if self._sweep_job is not None:
            return
        # 异步启动：_step_sweep 内部会重绘，直接调用会与 _redraw 形成递归
        self._sweep_job = self.after(24, self._step_sweep)

    def _stop_sweep(self) -> None:
        if self._sweep_job is not None:
            try:
                self.after_cancel(self._sweep_job)
            except Exception:  # noqa: BLE001
                pass
            self._sweep_job = None

    def _step_sweep(self) -> None:
        self._sweep_job = None
        self._sweep = (self._sweep + 0.035) % 1.3
        self._redraw()
        if self._indeterminate or self._running:
            self._sweep_job = self.after(24, self._step_sweep)

    # -- 绘制 ---------------------------------------------------------------
    def _redraw(self) -> None:
        width = int(self.winfo_width()) or int(self["width"]) or 200
        height = self._height
        radius = height / 2
        self.delete("all")
        rounded_rect(self, 0, 0, width, height, radius, fill=theme.FIELD, outline="")
        if self._indeterminate:
            band = max(60, width // 5)
            center = int(self._sweep * (width + band)) - band
            x1 = max(radius, center - band / 2)
            x2 = min(width - radius, center + band / 2)
            if x2 > x1:
                self.create_rectangle(x1, 0, x2, height, fill=self._color, outline="")
            return
        filled = int(width * self._shown)
        if filled > 1:
            rounded_rect(
                self, 0, 0, max(filled, height), height, radius,
                fill=self._color, outline="",
            )
            # 完成段的流光
            if 12 < filled < width - 2:
                band = max(10, filled // 6)
                x = int((self._sweep % 1.0) * max(filled - band, 1))
                self.create_rectangle(
                    max(radius, x), 1, min(filled - radius, x + band), height - 1,
                    fill=lighten(self._color, 0.35), outline="",
                )


# --------------------------------------------------------------------------
# 忙碌指示器
# --------------------------------------------------------------------------
class BusySpinner(tk.Canvas):
    """状态栏里的小转圈。"""

    def __init__(self, master, size: int = 14, bg: str | None = None) -> None:
        super().__init__(
            master, width=size, height=size, bg=bg or theme.PANEL_ALT,
            highlightthickness=0, bd=0
        )
        self._size = size
        self._angle = 0
        self._job: str | None = None

    def start(self) -> None:
        if self._job is None:
            self._spin()

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:  # noqa: BLE001
                pass
            self._job = None
        self.delete("all")

    def _spin(self) -> None:
        self.delete("all")
        pad = 2
        self.create_arc(
            pad, pad, self._size - pad, self._size - pad,
            start=self._angle, extent=260, style="arc",
            outline=theme.ACCENT, width=2,
        )
        self.create_arc(
            pad, pad, self._size - pad, self._size - pad,
            start=self._angle + 260, extent=100, style="arc",
            outline=theme.TEXT_FAINT, width=2,
        )
        self._angle = (self._angle - 24) % 360
        self._job = self.after(32, self._spin)


# --------------------------------------------------------------------------
# 滚动容器
# --------------------------------------------------------------------------
class ScrollableFrame(ttk.Frame):
    """竖向滚动的容器，内容放在 .body 里。"""

    def __init__(self, master, bg: str | None = None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        bg = bg or theme.BG
        self.container_bg = bg
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda _e: self._bind_wheel(False))
        self.body.bind("<Enter>", lambda _e: self._bind_wheel(True))
        self.body.bind("<Leave>", lambda _e: self._bind_wheel(False))

    def _on_body_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, active: bool) -> None:
        if active:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


# --------------------------------------------------------------------------
# 下载任务卡片
# --------------------------------------------------------------------------
def _truncate(text: str, limit: int = 60) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class TaskCard(tk.Frame):
    """单个下载任务的卡片（悬停描边高亮 + 动画按钮）。"""

    def __init__(
        self,
        master,
        task: Download,
        on_pause: Callable[[Download], None],
        on_resume: Callable[[Download], None],
        on_cancel: Callable[[Download], None],
        on_remove: Callable[[Download], None],
        bg: str | None = None,
    ) -> None:
        bg = bg or theme.PANEL
        super().__init__(master, bg=bg, highlightthickness=1,
                         highlightbackground=theme.BORDER_SOFT,
                         highlightcolor=theme.BORDER_SOFT)
        self.task = task
        self.card_bg = bg
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_cancel = on_cancel
        self.on_remove = on_remove
        self._button_state: DlState | None = None
        self._hover_tween = Tween(self, self._on_hover, duration=140)
        self._hover = 0.0
        self._last_state = None

        top = tk.Frame(self, bg=bg)
        top.pack(fill="x", padx=14, pady=(11, 2))
        self.name_label = tk.Label(
            top, text=_truncate(task.filename), bg=bg, fg=theme.TEXT,
            font=(UI_FONT, 10, "bold"), anchor="w",
        )
        self.name_label.pack(side="left")
        self.state_label = tk.Label(
            top, text="排队中", bg=bg, fg=theme.TEXT_DIM, font=(UI_FONT, 9)
        )
        self.state_label.pack(side="right")

        mid = tk.Frame(self, bg=bg)
        mid.pack(fill="x", padx=14, pady=(4, 0))
        self.bar = ProgressBar(mid, height=8)
        self.bar.pack(fill="x", pady=(2, 7))

        info = tk.Frame(self, bg=bg)
        info.pack(fill="x", padx=14, pady=(0, 10))
        self.detail_label = tk.Label(
            info, text="等待开始", bg=bg, fg=theme.TEXT_DIM,
            font=(UI_FONT, 9), anchor="w",
        )
        self.detail_label.pack(side="left")

        self.buttons = tk.Frame(info, bg=bg)
        self.buttons.pack(side="right")

        for widget in (self, top, mid, info, self.name_label, self.detail_label):
            widget.bind("<Enter>", lambda _e: self._hover_tween.start(self._hover, 1.0))
            widget.bind("<Leave>", lambda _e: self._hover_tween.start(self._hover, 0.0))
        self._build_buttons()

    def _on_hover(self, value: float) -> None:
        self._hover = value
        color = mix(theme.BORDER_SOFT, theme.ACCENT, 0.55 * value)
        self.configure(highlightbackground=color, highlightcolor=color)

    def _mk_button(self, text: str, command, kind: str) -> AnimatedButton:
        button = AnimatedButton(
            self.buttons,
            text=text,
            command=command,
            kind=kind,
            font=(UI_FONT, 9),
            height=26,
            radius=7,
            padx=12,
            parent_bg=self.card_bg,
        )
        button.pack(side="left", padx=(6, 0))
        return button

    def _build_buttons(self) -> None:
        if self._button_state is self.task.state and self.buttons.winfo_children():
            return
        self._button_state = self.task.state
        for child in self.buttons.winfo_children():
            child.destroy()
        state = self.task.state
        if state in (DlState.QUEUED, DlState.RUNNING):
            self._mk_button("暂停", lambda: self.on_pause(self.task), "ghost")
            self._mk_button("取消", lambda: self.on_cancel(self.task), "danger")
        elif state == DlState.PAUSED:
            self._mk_button("继续", lambda: self.on_resume(self.task), "success")
            self._mk_button("取消", lambda: self.on_cancel(self.task), "danger")
        elif state == DlState.FAILED:
            self._mk_button("重试", lambda: self.on_resume(self.task), "accent")
            self._mk_button("移除", lambda: self.on_remove(self.task), "danger")
        elif state == DlState.COMPLETED:
            self._mk_button(
                "打开文件夹", lambda: open_in_explorer(self.task.target_path, True), "ghost"
            )
            self._mk_button("移除记录", lambda: self.on_remove(self.task), "quiet")
        else:
            self._mk_button("移除", lambda: self.on_remove(self.task), "quiet")

    def refresh(self) -> None:
        snap = self.task.snapshot()
        state = snap.state
        colors = {
            DlState.QUEUED: theme.TEXT_DIM,
            DlState.RUNNING: theme.ACCENT,
            DlState.PAUSED: theme.WARN,
            DlState.COMPLETED: theme.SUCCESS,
            DlState.FAILED: theme.DANGER,
            DlState.CANCELED: theme.TEXT_FAINT,
        }
        self.state_label.configure(text=state.label, fg=colors.get(state, theme.TEXT_DIM))
        self.name_label.configure(text=_truncate(self.task.filename))

        if state == DlState.COMPLETED:
            self.bar.set(1.0, theme.SUCCESS)
            self.bar.set_indeterminate(False)
            self.bar.set_running(False)
            self.detail_label.configure(
                text=f"{human_size(snap.total or snap.downloaded)} · 已完成", fg=theme.SUCCESS
            )
        elif state == DlState.FAILED:
            self.bar.set_now(self.task.progress, theme.DANGER)
            self.bar.set_indeterminate(False)
            self.bar.set_running(False)
            self.detail_label.configure(text=snap.message or "下载失败", fg=theme.DANGER)
        elif state == DlState.RUNNING and snap.total <= 0:
            self.bar.set_indeterminate(True)
            self.bar.set_running(True)
            self.detail_label.configure(
                text=f"已下载 {human_size(snap.downloaded)}  ·  {human_speed(snap.speed)}",
                fg=theme.TEXT_DIM,
            )
        else:
            self.bar.set_indeterminate(False)
            self.bar.set_running(state == DlState.RUNNING)
            self.bar.set(self.task.progress, theme.ACCENT)
            parts = []
            if snap.total > 0:
                parts.append(f"{human_size(snap.downloaded)} / {human_size(snap.total)}")
                parts.append(f"{snap.downloaded * 100 // max(snap.total, 1)}%")
            else:
                parts.append(f"已下载 {human_size(snap.downloaded)}")
            if state == DlState.RUNNING:
                speed = snap.speed
                parts.append(human_speed(speed))
                if speed > 0 and snap.total > snap.downloaded:
                    parts.append("剩余 " + human_duration((snap.total - snap.downloaded) / speed))
                parts.append(f"{snap.workers} 线程")
            elif state == DlState.PAUSED:
                parts.append("已暂停")
            self.detail_label.configure(text="  ·  ".join(parts), fg=theme.TEXT_DIM)

        self._build_buttons()


def animated_buttons_in(widget) -> list[AnimatedButton]:
    """递归收集容器里的动画按钮（便于统一启用/禁用）。"""
    found: list[AnimatedButton] = []
    for child in widget.winfo_children():
        if isinstance(child, AnimatedButton):
            found.append(child)
        found.extend(animated_buttons_in(child))
    return found
