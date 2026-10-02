"""账号 / 设置对话框。"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import Config
from ..models import Platform
from ..platforms import all_clients
from ..util import apply_window_icon
from ..weblogin import get_login_service
from . import theme
from .anim import Tween, enable_smooth_timers, mix
from .widgets import AnimatedButton


class _BaseDialog(tk.Toplevel):
    def __init__(self, master, title: str, width: int, height: int) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=theme.BG)
        self.transient(master)
        self.grab_set()
        # 内容按最终尺寸固定居中放置：动画只改变窗口大小，内容不再重排，
        # 这样弹出过程才不会出现控件跳动（卡顿感来源）。
        self._content = tk.Frame(
            self, bg=theme.BG, width=width, height=height,
            highlightthickness=0, bd=0,
        )
        self._content.pack_propagate(False)
        self._content.place(
            relx=0.5, rely=0.5, anchor="center", width=width, height=height
        )
        self.body = self._content
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 2
        self._pop_box = (max(x, 0), max(y, 0), width, height)
        # 动画期间允许改变尺寸，否则 Tk 会把窗口锁在内容尺寸、弹出手感会失效
        self.resizable(True, True)
        self.minsize(int(width * 0.85), int(height * 0.85))
        self.maxsize(width, height)
        try:
            self.attributes("-alpha", 0.0)
        except Exception:  # noqa: BLE001
            pass
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        apply_window_icon(self)
        enable_smooth_timers()
        self._pop_in(0.0)

    def _pop_in(self, start=None) -> None:
        """从中心弹出：尺寸由 90% 放大到 100%，同时淡入（按真实时间推进，避免掉帧感）。

        - 内容按最终尺寸固定居中，缩放时不会重新排版；
        - 尺寸只在开头几步变化，其余帧只改透明度（改透明度几乎零开销）。
        """
        import time

        if start is None:
            start = time.perf_counter()
        duration = 0.19
        t = min(1.0, max(0.0, (time.perf_counter() - start) / duration))
        eased = 1 - (1 - t) ** 3
        base_x, base_y, full_w, full_h = self._pop_box
        try:
            if t < 0.45:
                # 前 45% 时间做尺寸放大，之后不再动窗口（避免整窗重绘）
                p = t / 0.45
                scale = 0.90 + 0.10 * (1 - (1 - p) ** 2)
                width = int(full_w * scale)
                height = int(full_h * scale)
                x = base_x + (full_w - width) // 2
                y = base_y + (full_h - height) // 2
                self.geometry(f"{width}x{height}+{x}+{y}")
            self.attributes("-alpha", min(1.0, 0.35 + 0.65 * eased))
        except Exception:  # noqa: BLE001
            return
        if t < 1.0:
            self.after(8, lambda: self._pop_in(start))
        else:
            # 动画结束：钉住最终尺寸并禁止缩放
            try:
                self.minsize(full_w, full_h)
                self.geometry(f"{full_w}x{full_h}+{base_x}+{base_y}")
                self.resizable(False, False)
            except Exception:  # noqa: BLE001
                pass


class CredentialDialog(_BaseDialog):
    """按平台管理登录凭证。"""

    def __init__(self, master, config: Config) -> None:
        super().__init__(master, "账号与凭证", 740, 620)
        self.config = config
        self.clients = all_clients()
        self.platforms = list(self.clients.keys())
        self.current = self.platforms[0]
        self.saved = False
        self._loaded = False
        self._login_queue: queue.Queue | None = None
        self._login_platform: Platform | None = None

        header = ttk.Frame(self.body, style="TFrame")
        header.pack(fill="x", padx=20, pady=(18, 6))
        ttk.Label(header, text="账号与凭证", style="Title.TLabel").pack(side="left")

        body = ttk.Frame(self.body, style="Panel.TFrame")
        body.pack(fill="both", expand=True, padx=20, pady=(6, 16))

        left = tk.Frame(body, bg=theme.PANEL)
        left.pack(side="left", fill="y", padx=(14, 8), pady=14)
        self.tab_buttons: dict[Platform, tk.Label] = {}
        self._tab_prev: Platform | None = None
        self._tab_tween = Tween(self, self._on_tab_frame, duration=150)
        for platform in self.platforms:
            label = tk.Label(
                left,
                text=platform.label,
                bg=theme.PANEL,
                fg=theme.TEXT_DIM,
                font=("Microsoft YaHei UI", 10),
                anchor="w",
                padx=14,
                pady=8,
                width=14,
                cursor="hand2",
            )
            label.pack(fill="x", pady=1)
            label.bind("<Button-1>", lambda _e, p=platform: self._select(p))
            self.tab_buttons[platform] = label

        right = tk.Frame(body, bg=theme.PANEL)
        right.pack(side="left", fill="both", expand=True, padx=(8, 14), pady=14)

        # 先把底部操作区与状态栏「钉」在底部，避免说明文字过长时按钮被挤出可视区；
        # 操作区分两行，保证每个平台的按钮都完整可见
        actions = tk.Frame(right, bg=theme.PANEL)
        actions.pack(side="bottom", fill="x")

        row1 = tk.Frame(actions, bg=theme.PANEL)
        row1.pack(fill="x")
        self.login_button = AnimatedButton(
            row1, "网页登录", self._web_login, kind="accent",
            parent_bg=theme.PANEL, width=108,
        )
        self.login_button.pack(side="left")
        self.close_button = AnimatedButton(
            row1, "关闭", self.destroy, kind="quiet", parent_bg=theme.PANEL
        )
        self.close_button.pack(side="right")
        self.alt_button = AnimatedButton(
            row1, "账号密码登录", self._xunlei_login, kind="ghost",
            parent_bg=theme.PANEL,
        )
        self.alt_button.pack(side="left", padx=(8, 0), before=self.close_button)

        row2 = tk.Frame(actions, bg=theme.PANEL)
        row2.pack(fill="x", pady=(8, 0))
        AnimatedButton(row2, "校验并保存", self._validate_save, kind="violet",
                       parent_bg=theme.PANEL).pack(side="left")
        AnimatedButton(row2, "清空", self._clear, kind="danger",
                       parent_bg=theme.PANEL).pack(side="left", padx=8)
        AnimatedButton(row2, "仅保存", self._save_only, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right")

        self.status = tk.Label(
            right, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
            font=("Microsoft YaHei UI", 9), anchor="w",
        )
        self.status.pack(side="bottom", fill="x", pady=(6, 4))

        self.title_label = tk.Label(
            right, text="", bg=theme.PANEL, fg=theme.TEXT,
            font=("Microsoft YaHei UI", 11, "bold"), anchor="w",
        )
        self.title_label.pack(fill="x")
        self.help_label = tk.Label(
            right, text="", bg=theme.PANEL, fg=theme.TEXT_DIM, justify="left",
            anchor="w", font=("Microsoft YaHei UI", 9), wraplength=430,
        )
        self.help_label.pack(fill="x", pady=(6, 10))

        self.token_label = tk.Label(
            right, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
            font=("Microsoft YaHei UI", 9), anchor="w",
        )
        self.token_label.pack(fill="x")
        self.text = tk.Text(
            right,
            height=5,
            bg=theme.FIELD,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT,
            font=("Consolas", 9),
            wrap="char",
            padx=8,
            pady=6,
        )
        self.text.pack(fill="both", expand=True, pady=(4, 8))

        self.refresh_frame = tk.Frame(right, bg=theme.PANEL)
        self.refresh_label = tk.Label(
            self.refresh_frame, text="refresh_token（可选，用于自动续期）",
            bg=theme.PANEL, fg=theme.TEXT_DIM, font=("Microsoft YaHei UI", 9), anchor="w",
        )
        self.refresh_label.pack(anchor="w")
        self.refresh_entry = ttk.Entry(self.refresh_frame)
        self.refresh_entry.pack(fill="x", pady=(4, 0))

        self._select(self.platforms[0])

    def _select(self, platform: Platform) -> None:
        if self._login_queue is not None and platform is not self.current:
            self.status.configure(text="请先完成当前平台的登录", fg=theme.WARN)
            return
        if self._loaded:
            self._stash()
        previous = self.current
        self.current = platform
        self._tab_prev = previous if previous is not platform else None
        self._tab_tween.start(0.0, 1.0)
        client = self.clients[platform]
        self.title_label.configure(text=f"{platform.label}  ·  {client.cred_title}")
        self.help_label.configure(text=client.cred_help)
        self.token_label.configure(text=f"{client.cred_title}：")
        self.login_button.set_text("网页登录")
        if platform is Platform.XUNLEI:
            self.alt_button.pack(side="left", padx=(8, 0), before=self.close_button)
        else:
            self.alt_button.pack_forget()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.config.credential(platform))
        self.status.configure(text="", fg=theme.TEXT_DIM)
        if platform is Platform.XUNLEI:
            self._pack_refresh()
            self.refresh_entry.delete(0, "end")
            self.refresh_entry.insert(0, self.config.get("xunlei_refresh_token", ""))
        else:
            self.refresh_frame.pack_forget()
        self._loaded = True

    def _on_tab_frame(self, value: float) -> None:
        """标签选中状态渐变（新选中的淡入、上一个淡出）。"""
        current = self.current
        for platform, label in self.tab_buttons.items():
            if platform is current:
                bg = mix(theme.PANEL, theme.PANEL_ALT, value)
                fg = mix(theme.TEXT_DIM, theme.TEXT, value)
            elif platform is self._tab_prev:
                bg = mix(theme.PANEL_ALT, theme.PANEL, value)
                fg = mix(theme.TEXT, theme.TEXT_DIM, value)
            else:
                bg, fg = theme.PANEL, theme.TEXT_DIM
            try:
                label.configure(bg=bg, fg=fg)
            except Exception:  # noqa: BLE001
                pass

    def _pack_refresh(self) -> None:
        """refresh_token 那一行贴在状态栏上方（side=bottom，最后 pack 即在最上方一层）。"""
        if not self.refresh_frame.winfo_manager():
            self.refresh_frame.pack(fill="x", pady=(0, 6), side="bottom")

    def _stash(self) -> None:
        if not hasattr(self, "current"):
            return
        value = self.text.get("1.0", "end").strip()
        self.config.set_credential(self.current, value)
        if self.current is Platform.XUNLEI:
            self.config.set("xunlei_refresh_token", self.refresh_entry.get().strip())

    def _clear(self) -> None:
        self.text.delete("1.0", "end")
        if self.current is Platform.XUNLEI:
            self.refresh_entry.delete(0, "end")
        self.status.configure(text="已清空，记得保存", fg=theme.WARN)

    def destroy(self) -> None:
        """关闭对话框时一并关掉还开着的登录窗口。"""
        if self._login_queue is not None:
            try:
                get_login_service().close_active()
            except Exception:  # noqa: BLE001
                pass
            self._login_queue = None
        super().destroy()

    # -- 内置网页登录 -------------------------------------------------------
    def _web_login(self) -> None:
        if self._login_queue is not None:
            self.status.configure(text="登录窗口已经打开，请在其中完成登录", fg=theme.TEXT_DIM)
            return
        self._stash()
        platform = self.current
        try:
            self._login_queue = get_login_service().open(platform)
        except Exception as exc:  # noqa: BLE001
            self._login_queue = None
            self.status.configure(text=f"无法打开登录窗口：{exc}", fg=theme.DANGER)
            return
        self._login_platform = platform
        self.login_button.set_enabled(False)
        self.login_button.set_busy(True)
        self.login_button.set_text("登录中…")
        self.status.configure(
            text=f"正在打开{platform.label}登录窗口…",
            fg=theme.TEXT_DIM,
        )
        self.after(400, self._poll_login)

    def _xunlei_login(self) -> None:
        """迅雷网页版的 token 只存在页面内存里，改用官方账号登录接口。"""
        from .xunlei_login import XunleiLoginDialog

        client = self.clients[Platform.XUNLEI]
        dialog = XunleiLoginDialog(self, client)  # type: ignore[arg-type]
        self.wait_window(dialog)
        if not dialog.access_token:
            self.status.configure(text="未完成登录", fg=theme.WARN)
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", dialog.access_token)
        if dialog.refresh_token:
            self.refresh_entry.delete(0, "end")
            self.refresh_entry.insert(0, dialog.refresh_token)
        self._pack_refresh()
        self._stash()
        self.config_store.save()
        self.saved = True
        suffix = f"（{dialog.nickname}）" if dialog.nickname else ""
        self.status.configure(text=f"迅雷网盘 登录成功{suffix}，凭证已保存 ✔", fg=theme.SUCCESS)

    def _reset_login_button(self) -> None:
        self.login_button.set_busy(False)
        self.login_button.set_enabled(True)
        self.login_button.set_text("网页登录")

    def _poll_login(self) -> None:
        login_queue = self._login_queue
        if login_queue is None:
            self._reset_login_button()
            return
        try:
            result = login_queue.get_nowait()
        except queue.Empty:
            platform = self._login_platform
            label = platform.label if platform else ""
            self.status.configure(
                text=f"已打开{label}登录窗口，登录完成后会自动保存凭证…",
                fg=theme.TEXT_DIM,
            )
            self.after(400, self._poll_login)
            return

        self._login_queue = None
        self._reset_login_button()
        platform = self._login_platform or self.current
        if not result.get("ok"):
            self.status.configure(
                text=result.get("error") or "已取消登录", fg=theme.WARN
            )
            return

        credential = result.get("credential") or ""
        if not credential:
            self.status.configure(text="登录窗口没有返回有效凭证", fg=theme.WARN)
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", credential)
        refresh_token = result.get("refresh_token") or ""
        if self.current is Platform.XUNLEI and refresh_token:
            self.refresh_entry.delete(0, "end")
            self.refresh_entry.insert(0, refresh_token)
        self._stash()
        self.config_store.save()
        self.saved = True
        nickname = result.get("nickname") or ""
        suffix = f"（{nickname}）" if nickname else ""
        self.status.configure(
            text=f"{platform.label} 登录成功{suffix}，凭证已保存 ✔",
            fg=theme.SUCCESS,
        )

    def _save_only(self) -> None:
        self._stash()
        self.config.save()
        self.saved = True
        self.status.configure(text="已保存", fg=theme.SUCCESS)

    def _validate_save(self) -> None:
        self._stash()
        value = self.config.credential(self.current)
        if not value:
            self.status.configure(text="请先粘贴凭证", fg=theme.WARN)
            return
        client = self.clients[self.current]
        if self.current is Platform.XUNLEI:
            client.refresh_token = self.config.get("xunlei_refresh_token", "")
        self._result: dict = {}
        self.status.configure(text="校验中，请稍候…", fg=theme.TEXT_DIM)

        def work() -> None:
            try:
                self._result["name"] = client.check_credential(value)
            except Exception as exc:  # noqa: BLE001
                self._result["error"] = str(exc)
            finally:
                self._result["done"] = True

        import threading

        threading.Thread(target=work, daemon=True).start()
        self.after(150, self._poll_validation)

    def _poll_validation(self) -> None:
        if not self._result.get("done"):
            self.after(150, self._poll_validation)
            return
        if "error" in self._result:
            self.status.configure(text=self._result["error"], fg=theme.DANGER)
            return
        client = self.clients[self.current]
        if getattr(client, "refreshed_credential", None):
            self.config.set_credential(self.current, client.refreshed_credential)
            self.text.delete("1.0", "end")
            self.text.insert("1.0", client.refreshed_credential)
            client.refreshed_credential = None
        self.config.save()
        self.saved = True
        name = self._result.get("name")
        suffix = f"（{name}）" if name else ""
        self.status.configure(text=f"校验通过，已保存{suffix} ✔", fg=theme.SUCCESS)


class SettingsDialog(_BaseDialog):
    """下载参数设置。"""

    def __init__(self, master, config: Config) -> None:
        super().__init__(master, "设置", 580, 620)
        self.config = config
        self.changed = False

        ttk.Label(self.body, text="设置", style="Title.TLabel").pack(
            anchor="w", padx=20, pady=(18, 4)
        )
        panel = ttk.Frame(self.body, style="Panel.TFrame")
        panel.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        inner = tk.Frame(panel, bg=theme.PANEL)
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        def row(text: str, widget_factory):
            holder = tk.Frame(inner, bg=theme.PANEL)
            holder.pack(fill="x", pady=6)
            tk.Label(holder, text=text, bg=theme.PANEL, fg=theme.TEXT,
                     font=("Microsoft YaHei UI", 10), width=16, anchor="w").pack(side="left")
            widget = widget_factory(holder)
            widget.pack(side="left", fill="x", expand=True)
            return widget

        # 下载目录
        theme_holder = tk.Frame(inner, bg=theme.PANEL)
        theme_holder.pack(fill="x", pady=6)
        tk.Label(theme_holder, text="界面风格", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=16, anchor="w").pack(side="left")
        self.theme_buttons = tk.Frame(theme_holder, bg=theme.PANEL)
        self.theme_buttons.pack(side="left")
        self.theme_choice = str(config.get("theme", "dark") or "dark")
        self.theme_changed = False
        self._refresh_theme_buttons()

        # 下载目录
        dir_holder = tk.Frame(inner, bg=theme.PANEL)
        dir_holder.pack(fill="x", pady=6)
        tk.Label(dir_holder, text="下载目录", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=16, anchor="w").pack(side="left")
        self.dir_entry = ttk.Entry(dir_holder)
        self.dir_entry.pack(side="left", fill="x", expand=True)
        self.dir_entry.insert(0, config.download_dir())
        AnimatedButton(dir_holder, "浏览", self._pick_dir, kind="ghost",
                       parent_bg=theme.PANEL).pack(side="left", padx=(8, 0))

        # 并发任务
        tasks_holder = tk.Frame(inner, bg=theme.PANEL)
        tasks_holder.pack(fill="x", pady=6)
        tk.Label(tasks_holder, text="同时下载任务数", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=16, anchor="w").pack(side="left")
        self.tasks_spin = tk.Spinbox(
            tasks_holder, from_=1, to=10, width=8, bg=theme.FIELD, fg=theme.TEXT,
            insertbackground=theme.TEXT, relief="flat", buttonbackground=theme.PANEL_ALT,
            highlightthickness=1, highlightbackground=theme.BORDER,
        )
        self.tasks_spin.pack(side="left")
        self.tasks_spin.delete(0, "end")
        self.tasks_spin.insert(0, str(config.max_tasks()))
        tk.Label(tasks_holder, text="建议 2-4", bg=theme.PANEL, fg=theme.TEXT_FAINT,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=10)

        # 限速
        speed_holder = tk.Frame(inner, bg=theme.PANEL)
        speed_holder.pack(fill="x", pady=6)
        tk.Label(speed_holder, text="全局限速 (KB/s)", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=16, anchor="w").pack(side="left")
        self.speed_spin = tk.Spinbox(
            speed_holder, from_=0, to=1048576, increment=256, width=10, bg=theme.FIELD,
            fg=theme.TEXT, insertbackground=theme.TEXT, relief="flat",
            buttonbackground=theme.PANEL_ALT, highlightthickness=1, highlightbackground=theme.BORDER,
        )
        self.speed_spin.pack(side="left")
        self.speed_spin.delete(0, "end")
        self.speed_spin.insert(0, str(config.get("speed_limit_kb", 0)))
        tk.Label(speed_holder, text="0 = 不限速", bg=theme.PANEL, fg=theme.TEXT_FAINT,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=10)

        # 代理
        self.proxy_entry = row("HTTP 代理", lambda parent: ttk.Entry(parent))
        self.proxy_entry.insert(0, config.get("proxy", ""))
        tk.Label(inner, text="例如 http://127.0.0.1:7890，留空表示直连",
                 bg=theme.PANEL, fg=theme.TEXT_FAINT, font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        self.repo_entry = row("项目仓库", lambda parent: ttk.Entry(parent))
        self.repo_entry.insert(0, str(config.get("repo_url", "") or ""))
        tk.Label(inner, text="填写后会在「详细信息」里显示，并提供一键打开",
                 bg=theme.PANEL, fg=theme.TEXT_FAINT, font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        tk.Frame(inner, bg=theme.BORDER, height=1).pack(fill="x", pady=10)
        tk.Label(inner, text="按平台设置下载线程数", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(inner, text="建议 8-32；迅雷 CDN 并发超过 8 会被降级，故默认 8",
                 bg=theme.PANEL, fg=theme.TEXT_FAINT, font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        grid = tk.Frame(inner, bg=theme.PANEL)
        grid.pack(fill="x", pady=(8, 0))
        self.thread_spins: dict[str, tk.Spinbox] = {}
        for idx, platform in enumerate(Platform):
            tk.Label(grid, text=platform.label, bg=theme.PANEL, fg=theme.TEXT_DIM,
                     font=("Microsoft YaHei UI", 9), anchor="w").grid(
                row=idx // 2, column=(idx % 2) * 2, sticky="w", padx=(0, 8), pady=4)
            spin = tk.Spinbox(
                grid, from_=1, to=128, width=6, bg=theme.FIELD, fg=theme.TEXT,
                insertbackground=theme.TEXT, relief="flat", buttonbackground=theme.PANEL_ALT,
                highlightthickness=1, highlightbackground=theme.BORDER,
            )
            spin.delete(0, "end")
            spin.insert(0, str(config.threads(platform)))
            spin.grid(row=idx // 2, column=(idx % 2) * 2 + 1, sticky="w", pady=4)
            self.thread_spins[platform.value] = spin

        actions = tk.Frame(panel, bg=theme.PANEL)
        actions.pack(fill="x", padx=18, pady=(0, 16))
        AnimatedButton(actions, "保存", self._save, kind="accent",
                       parent_bg=theme.PANEL, width=96).pack(side="left")
        AnimatedButton(actions, "取消", self.destroy, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right")

    def _pick_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.dir_entry.get() or ".")
        if chosen:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, chosen)

    def _refresh_theme_buttons(self) -> None:
        for child in self.theme_buttons.winfo_children():
            child.destroy()
        for name, label in (("dark", "蓝色风格"), ("light", "白色风格")):
            AnimatedButton(
                self.theme_buttons,
                label,
                (lambda n=name: self._choose_theme(n)),
                kind="accent" if self.theme_choice == name else "ghost",
                parent_bg=theme.PANEL,
            ).pack(side="left", padx=(0, 8))

    def _choose_theme(self, name: str) -> None:
        self.theme_choice = name
        self._refresh_theme_buttons()

    def _save(self) -> None:
        directory = self.dir_entry.get().strip()
        if not directory:
            messagebox.showwarning("提示", "请选择下载目录", parent=self)
            return
        import os

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("提示", f"无法创建目录：{exc}", parent=self)
            return
        self.config.set("download_dir", directory)
        self.config.set("max_concurrent_tasks", int(self.tasks_spin.get() or 3))
        self.config.set("speed_limit_kb", int(self.speed_spin.get() or 0))
        self.config.set("proxy", self.proxy_entry.get().strip())
        if self.theme_choice != str(self.config.get("theme", "dark")):
            self.theme_changed = True
        self.config.set("theme", self.theme_choice)
        self.config.set("repo_url", self.repo_entry.get().strip())
        threads = {}
        for key, spin in self.thread_spins.items():
            try:
                threads[key] = max(1, min(int(spin.get()), 128))
            except (TypeError, ValueError):
                threads[key] = 16
        self.config.set("threads", threads)
        self.config.save()
        self.changed = True
        self.destroy()
