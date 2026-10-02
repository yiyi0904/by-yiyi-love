"""迅雷网盘登录对话框（账号密码 + 短信验证码，与官方 App 同一套接口）。

迅雷网页版的 access_token 只存在页面内存里，抓不到；所以这里走官方登录接口。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from ..platforms.xunlei import XunleiClient
from ..util import apply_window_icon
from . import theme
from .dialogs import _BaseDialog
from .widgets import AnimatedButton


class XunleiLoginDialog(_BaseDialog):
    def __init__(self, master, client: XunleiClient) -> None:
        super().__init__(master, "迅雷网盘登录", 480, 420)
        self.client = client
        self.access_token = ""
        self.refresh_token = ""
        self.nickname = ""
        self._credit_key = ""
        self._sms_token = ""
        self._sms_sent = False
        self._busy = False
        self._events: queue.Queue = queue.Queue()

        ttk.Label(self, text="登录迅雷网盘", style="Title.TLabel").pack(
            anchor="w", padx=20, pady=(18, 2)
        )
        ttk.Label(
            self,
            text="使用迅雷账号登录。若触发安全验证，会需要短信验证码。",
            style="Dim.TLabel",
            background=theme.BG,
        ).pack(anchor="w", padx=20)

        panel = ttk.Frame(self, style="Panel.TFrame")
        panel.pack(fill="both", expand=True, padx=20, pady=(10, 16))
        body = tk.Frame(panel, bg=theme.PANEL)
        body.pack(fill="both", expand=True, padx=18, pady=16)

        self.user_var = tk.StringVar()
        self.pwd_var = tk.StringVar()
        self.code_var = tk.StringVar()

        user_row = tk.Frame(body, bg=theme.PANEL)
        user_row.pack(fill="x", pady=6)
        tk.Label(user_row, text="迅雷账号", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=10, anchor="w").pack(side="left")
        ttk.Entry(user_row, textvariable=self.user_var).pack(side="left", fill="x", expand=True)
        tk.Label(body, text="手机号或邮箱，与迅雷 App 登录用的一致",
                 bg=theme.PANEL, fg=theme.TEXT_FAINT, font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        pwd_row = tk.Frame(body, bg=theme.PANEL)
        pwd_row.pack(fill="x", pady=(10, 6))
        tk.Label(pwd_row, text="密码", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=10, anchor="w").pack(side="left")
        ttk.Entry(pwd_row, textvariable=self.pwd_var, show="●").pack(
            side="left", fill="x", expand=True
        )

        self.sms_frame = tk.Frame(body, bg=theme.PANEL)
        code_row = tk.Frame(self.sms_frame, bg=theme.PANEL)
        code_row.pack(fill="x", pady=(6, 6))
        tk.Label(code_row, text="验证码", bg=theme.PANEL, fg=theme.TEXT,
                 font=("Microsoft YaHei UI", 10), width=10, anchor="w").pack(side="left")
        ttk.Entry(code_row, textvariable=self.code_var, width=10).pack(side="left")
        self.send_button = AnimatedButton(
            code_row, "发送验证码", self._send_sms, kind="violet",
            parent_bg=theme.PANEL,
        )
        self.send_button.pack(side="left", padx=10)

        self.status = tk.Label(
            body, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
            font=("Microsoft YaHei UI", 9), anchor="w", wraplength=380, justify="left",
        )
        self.status.pack(fill="x", pady=(14, 4))

        actions = tk.Frame(body, bg=theme.PANEL)
        actions.pack(fill="x", pady=(6, 0))
        self.login_button = AnimatedButton(
            actions, "登录", self._submit, kind="accent",
            parent_bg=theme.PANEL, width=96,
        )
        self.login_button.pack(side="left")
        AnimatedButton(actions, "取消", self.destroy, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right")

        apply_window_icon(self)
        self.after(80, self._drain_events)
        self.after(200, lambda: self.focus_force())

    # -- 流程 ---------------------------------------------------------------
    def _set_status(self, text: str, color: str = theme.TEXT_DIM) -> None:
        self.status.configure(text=text, fg=color)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.login_button.set_enabled(not busy)
        self.login_button.set_busy(busy)
        self.send_button.set_enabled(not busy)

    def _show_sms_row(self) -> None:
        if not self.sms_frame.winfo_manager():
            self.sms_frame.pack(fill="x", before=self.status)

    def _send_sms(self) -> None:
        if self._busy:
            return
        user = self.user_var.get().strip()
        if not user:
            self._set_status("请先填写迅雷账号", theme.WARN)
            return
        self._set_busy(True)
        self._set_status("正在发送验证码…")
        self._run(self._do_send_sms, user)

    def _submit(self) -> None:
        if self._busy:
            return
        user = self.user_var.get().strip()
        password = self.pwd_var.get()
        if not user or not password:
            self._set_status("请填写账号和密码", theme.WARN)
            return
        self._set_busy(True)
        if self._sms_sent:
            code = self.code_var.get().strip()
            if not code:
                self._set_busy(False)
                self._set_status("请填写短信验证码", theme.WARN)
                return
            self._set_status("正在校验验证码…")
            self._run(self._do_sms_login, user, code)
        else:
            self._set_status("正在登录…")
            self._run(self._do_password_login, user, password)

    # -- 后台任务 -----------------------------------------------------------
    def _post(self, func) -> None:
        self._events.put(func)

    def _drain_events(self) -> None:
        """界面更新统一回到主线程执行（tkinter 不是线程安全的）。"""
        try:
            while True:
                func = self._events.get_nowait()
                try:
                    func()
                except Exception:  # noqa: BLE001
                    pass
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(80, self._drain_events)
        except Exception:  # noqa: BLE001
            pass

    def _run(self, func, *args) -> None:
        def work() -> None:
            try:
                func(*args)
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or exc.__class__.__name__
                self._post(lambda m=message: self._on_error(m))

        threading.Thread(target=work, daemon=True).start()

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self._set_status(f"出错：{message}", theme.DANGER)

    def _on_success(self) -> None:
        self._set_status(f"登录成功{'（' + self.nickname + '）' if self.nickname else ''}", theme.SUCCESS)
        self.after(300, self.destroy)

    def _do_send_sms(self, user: str) -> None:
        result = self.client.begin_sms_login(user)
        self._post(lambda: self._after_send_sms(result))

    def _after_send_sms(self, result: dict) -> None:
        self._set_busy(False)
        if result.get("ok"):
            self._credit_key = result.get("credit_key", "")
            self._sms_token = result.get("token", "")
            self._sms_sent = True
            self._show_sms_row()
            self._set_status(
                "验证码已发送，请在下方填写后点「登录」" if self._credit_key
                else "验证码已发送，请在下方填写后点「登录」",
                theme.SUCCESS,
            )
        else:
            self._set_status(result.get("message") or "验证码发送失败", theme.DANGER)

    def _do_password_login(self, user: str, password: str) -> None:
        result = self.client.complete_password_login(user, password)
        self._post(lambda: self._after_password_login(result, user))

    def _after_password_login(self, result: dict, user: str) -> None:
        if result.get("ok"):
            self._finish(result)
            return
        if result.get("need_sms"):
            self._set_busy(False)
            self._show_sms_row()
            self._set_status("该账号需要短信验证，已自动发送验证码…", theme.WARN)
            self._send_sms()
            return
        self._set_busy(False)
        self._set_status(result.get("message") or "登录失败", theme.DANGER)

    def _do_sms_login(self, user: str, code: str) -> None:
        result = self.client.complete_sms_login(
            user, code, self._credit_key, self._sms_token
        )
        self._post(lambda: self._after_sms_login(result))

    def _after_sms_login(self, result: dict) -> None:
        if result.get("ok"):
            self._finish(result)
            return
        self._set_busy(False)
        self._set_status(result.get("message") or "验证码校验失败", theme.DANGER)

    def _finish(self, result: dict) -> None:
        self.access_token = result.get("access_token", "")
        self.refresh_token = result.get("refresh_token", "")
        self.nickname = result.get("nickname", "")
        self._set_busy(False)
        self._on_success()
