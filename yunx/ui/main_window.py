"""主窗口。"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .. import APP_NAME, __version__
from ..config import Config
from ..downloader import DlState, Download, DownloadQueue
from ..limiter import GlobalRateLimiter
from ..link_parser import parse_share
from ..models import ApiError, PanFile, Platform, ShareSession
from ..net import set_proxy
from ..platforms import get_client
from ..util import apply_window_icon, human_size, human_speed, open_in_explorer
from . import theme
from .dialogs import CredentialDialog, SettingsDialog
from .anim import enable_smooth_timers
from .widgets import AnimatedButton, BusySpinner, ScrollableFrame, TaskCard


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.config_store = Config()
        enable_smooth_timers()
        theme.set_palette(self.config_store.get("theme", "dark"))
        self.fonts = theme.apply_theme(self)
        set_proxy(self.config_store.get("proxy", ""))

        self.title(f"{APP_NAME} v{__version__}  ·  网盘解析多线程下载")
        self.minsize(1000, 640)
        window = self.config_store.get("window", {}) or {}
        width = int(window.get("width") or 1180)
        height = int(window.get("height") or 780)
        self.geometry(f"{width}x{height}")
        if window.get("x") is not None and window.get("y") is not None:
            self.geometry(f"+{int(window['x'])}+{int(window['y'])}")

        self.limiter = GlobalRateLimiter(self.config_store.speed_limit())
        self.queue = DownloadQueue(self.config_store.max_tasks(), self.limiter)
        self.queue.start()

        apply_window_icon(self)

        self.events: queue.Queue = queue.Queue()
        self.session: ShareSession | None = None
        self.session_platform: Platform | None = None
        self.files: list[PanFile] = []
        self.nav_stack: list[tuple[str, str]] = []  # (dir_id, dir_name)
        self.tasks: dict[str, Download] = {}
        self.cards: dict[str, TaskCard] = {}
        self.cleaned: set[str] = set()
        self._busy = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._drain_events)
        self.after(600, self._tick)

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self._build_header()

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self._build_parse_panel(body)
        self._build_file_panel(body)
        self._build_download_panel(body)
        self._build_status_bar()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=theme.BG)
        header.pack(fill="x", padx=16, pady=(14, 10))

        tk.Label(
            header, text=APP_NAME, bg=theme.BG, fg=theme.TEXT, font=self.fonts["title"]
        ).pack(side="left")
        tk.Label(
            header,
            text=f"v{__version__}  ·  网盘分享解析 + 多线程高速下载",
            bg=theme.BG,
            fg=theme.TEXT_FAINT,
            font=self.fonts["small"],
        ).pack(side="left", padx=(10, 0), pady=(4, 0))

        AnimatedButton(header, "设置", self._open_settings, kind="quiet",
                       parent_bg=theme.BG).pack(side="right")
        AnimatedButton(header, "账号与凭证", self._open_credentials, kind="accent",
                       parent_bg=theme.BG).pack(side="right", padx=8)
        AnimatedButton(header, "使用说明", self._show_help, kind="quiet",
                       parent_bg=theme.BG).pack(side="right", padx=(8, 0))
        AnimatedButton(header, "详细信息", self._show_details, kind="quiet",
                       parent_bg=theme.BG).pack(side="right", padx=(8, 0))

    def _build_parse_panel(self, parent) -> None:
        panel = tk.Frame(parent, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.BORDER)
        panel.pack(fill="x", pady=(0, 10))

        row1 = tk.Frame(panel, bg=theme.PANEL)
        row1.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(row1, text="分享链接 / 分享文案", bg=theme.PANEL, fg=theme.TEXT_DIM,
                 font=self.fonts["small"]).pack(side="left", padx=(0, 10))
        self.platform_label = tk.Label(
            row1, text="", bg=theme.PANEL_ALT, fg=theme.ACCENT,
            font=self.fonts["small"], padx=8, pady=2,
        )
        self.platform_label.pack(side="right")

        row2 = tk.Frame(panel, bg=theme.PANEL)
        row2.pack(fill="x", padx=14, pady=(0, 6))
        self.link_var = tk.StringVar()
        self.link_entry = tk.Entry(
            row2, textvariable=self.link_var, bg=theme.FIELD, fg=theme.TEXT,
            insertbackground=theme.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            font=self.fonts["base"],
        )
        self.link_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.link_entry.bind("<KeyRelease>", lambda _e: self._on_link_changed())
        self.link_entry.bind("<Return>", lambda _e: self._on_parse())
        tk.Label(row2, text="提取码", bg=theme.PANEL, fg=theme.TEXT_DIM,
                 font=self.fonts["small"]).pack(side="left", padx=(12, 6))
        self.pwd_var = tk.StringVar()
        tk.Entry(
            row2, textvariable=self.pwd_var, width=10, bg=theme.FIELD, fg=theme.TEXT,
            insertbackground=theme.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
        ).pack(side="left", ipady=6)
        self.parse_button = AnimatedButton(
            row2, "解析", self._on_parse, kind="accent",
            parent_bg=theme.PANEL, width=96,
        )
        self.parse_button.pack(side="left", padx=(10, 0))
        AnimatedButton(row2, "粘贴", self._paste_link, kind="ghost",
                       parent_bg=theme.PANEL).pack(side="left", padx=(8, 0))

        row3 = tk.Frame(panel, bg=theme.PANEL)
        row3.pack(fill="x", padx=14, pady=(0, 12))
        self.hint_label = tk.Label(
            row3, text="支持：夸克 / UC / 迅雷 / 百度 / 移动云盘(139) / 123 云盘",
            bg=theme.PANEL, fg=theme.TEXT_FAINT, font=self.fonts["small"], anchor="w",
        )
        self.hint_label.pack(side="left")

    def _build_file_panel(self, parent) -> None:
        panel = tk.Frame(parent, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.BORDER)
        panel.pack(fill="both", expand=True)

        bar = tk.Frame(panel, bg=theme.PANEL)
        bar.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(bar, text="文件列表", bg=theme.PANEL, fg=theme.TEXT,
                 font=self.fonts["subtitle"]).pack(side="left")
        self.path_label = tk.Label(bar, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
                                   font=self.fonts["small"])
        self.path_label.pack(side="left", padx=12)
        AnimatedButton(bar, "刷新", self._reload_dir, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right")
        AnimatedButton(bar, "返回上级", self._go_up, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right", padx=8)
        AnimatedButton(bar, "下载选中", self._download_selected, kind="accent",
                       parent_bg=theme.PANEL, width=112).pack(side="right", padx=(8, 0))
        AnimatedButton(bar, "复制直链", self._copy_links, kind="ghost",
                       parent_bg=theme.PANEL).pack(side="right", padx=8)
        AnimatedButton(bar, "全选", self._select_all, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right")

        columns = ("name", "size", "kind")
        tree_holder = tk.Frame(panel, bg=theme.PANEL)
        tree_holder.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.tree = ttk.Treeview(
            tree_holder, columns=columns, show="headings", selectmode="extended"
        )
        self.tree.heading("name", text="名称")
        self.tree.heading("size", text="大小")
        self.tree.heading("kind", text="类型")
        self.tree.column("name", width=560, anchor="w")
        self.tree.column("size", width=110, anchor="e")
        self.tree.column("kind", width=80, anchor="center")
        self.tree.tag_configure("dir", foreground=theme.ACCENT)
        self.tree.tag_configure("file", foreground=theme.TEXT)
        self.tree.tag_configure("odd", background=theme.PANEL_ALT)
        self.tree.tag_configure("even", background=theme.PANEL)
        self.tree.tag_configure("hover", background=theme.PANEL_HI)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_selection_hint())
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda _e: self._clear_hover_row())
        self._hover_row = ""
        self._row_tags: dict[str, tuple] = {}

        scrollbar = ttk.Scrollbar(tree_holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.file_footer = tk.Label(
            panel, text="还没有解析结果", bg=theme.PANEL, fg=theme.TEXT_FAINT,
            font=self.fonts["small"], anchor="w",
        )
        self.file_footer.pack(fill="x", padx=14, pady=(0, 8))

    def _build_download_panel(self, parent) -> None:
        panel = tk.Frame(parent, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.BORDER)
        panel.pack(fill="both", expand=True, pady=(10, 0))

        bar = tk.Frame(panel, bg=theme.PANEL)
        bar.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(bar, text="下载任务", bg=theme.PANEL, fg=theme.TEXT,
                 font=self.fonts["subtitle"]).pack(side="left")
        self.dl_summary = tk.Label(bar, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
                                   font=self.fonts["small"])
        self.dl_summary.pack(side="left", padx=12)
        AnimatedButton(
            bar, "打开下载目录",
            lambda: open_in_explorer(self.config_store.download_dir()),
            kind="quiet", parent_bg=theme.PANEL,
        ).pack(side="right")
        AnimatedButton(bar, "全部继续", self._resume_all, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right", padx=8)
        AnimatedButton(bar, "清空已完成", self._clear_finished, kind="quiet",
                       parent_bg=theme.PANEL).pack(side="right")

        self.dl_scroll = ScrollableFrame(panel, bg=theme.PANEL)
        self.dl_scroll.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.empty_hint = tk.Label(
            self.dl_scroll.body,
            text="下载任务会显示在这里",
            bg=theme.PANEL,
            fg=theme.TEXT_FAINT,
            font=self.fonts["small"],
        )
        self.empty_hint.pack(pady=20)

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self, bg=theme.PANEL_ALT)
        bar.pack(fill="x", side="bottom")
        self.spinner = BusySpinner(bar, size=14)
        self.spinner.pack(side="left", padx=(12, 2), pady=6)
        self.status_label = tk.Label(
            bar, text="就绪", bg=theme.PANEL_ALT, fg=theme.TEXT_DIM,
            font=self.fonts["small"], anchor="w",
        )
        self.status_label.pack(side="left", padx=(2, 14), pady=6)
        self.speed_label = tk.Label(
            bar, text="", bg=theme.PANEL_ALT, fg=theme.TEXT_DIM,
            font=self.fonts["small"], anchor="e",
        )
        self.speed_label.pack(side="right", padx=14, pady=6)

    # ------------------------------------------------------------------
    # 事件循环
    # ------------------------------------------------------------------
    def post(self, func) -> None:
        self.events.put(func)

    def log(self, message: str) -> None:
        self.post(lambda: self.set_status(message))

    def set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def _drain_events(self) -> None:
        try:
            while True:
                func = self.events.get_nowait()
                try:
                    func()
                except Exception as exc:  # noqa: BLE001
                    self.set_status(f"界面更新出错：{exc}")
        except queue.Empty:
            pass
        self.after(120, self._drain_events)

    def _tick(self) -> None:
        active = 0
        total_speed = 0.0
        for task_id, task in self.tasks.items():
            card = self.cards.get(task_id)
            if card is not None:
                card.refresh()
            snap = task.snapshot()
            if snap.state == DlState.RUNNING:
                active += 1
                total_speed += snap.speed
            if snap.state == DlState.COMPLETED and task_id not in self.cleaned:
                self.cleaned.add(task_id)
                self._after_complete(task)
        self.dl_summary.configure(
            text=f"{len(self.tasks)} 个任务 · {active} 个下载中" if self.tasks else ""
        )
        self.speed_label.configure(
            text=f"总速度 {human_speed(total_speed)}  " if total_speed > 0 else ""
        )
        self.after(500, self._tick)

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------
    def _paste_link(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        self.link_var.set(text.strip())
        self._on_link_changed()
        parsed = parse_share(text)
        if parsed and parsed.pwd and not self.pwd_var.get():
            self.pwd_var.set(parsed.pwd)

    def _on_link_changed(self) -> None:
        text = self.link_var.get().strip()
        parsed = parse_share(text) if text else None
        if parsed:
            self.platform_label.configure(text=parsed.platform.label)
            if parsed.pwd and not self.pwd_var.get():
                self.pwd_var.set(parsed.pwd)
        else:
            self.platform_label.configure(text="")

    def _on_parse(self) -> None:
        if self._busy:
            return
        text = self.link_var.get().strip()
        if not text:
            messagebox.showinfo("提示", "请先粘贴网盘分享链接或分享文案", parent=self)
            return
        parsed = parse_share(text)
        if parsed is None:
            messagebox.showwarning(
                "无法识别",
                "没有识别出支持的网盘链接。\n\n"
                "支持：pan.quark.cn / drive.uc.cn / pan.xunlei.com / pan.baidu.com / "
                "yun.139.com / 123pan.com",
                parent=self,
            )
            return
        client = get_client(parsed.platform)
        credential = self.config_store.credential(parsed.platform)
        if parsed.platform in (
            Platform.QUARK,
            Platform.UC,
            Platform.BAIDU,
            Platform.C139,
            Platform.XUNLEI,
        ):
            if not credential:
                self._prompt_credentials(parsed.platform)
                credential = self.config_store.credential(parsed.platform)
                if not credential:
                    return

        pwd = self.pwd_var.get().strip() or parsed.pwd or ""
        self._set_busy(True, f"正在解析 {parsed.platform.label} 分享…")
        self.files = []
        self._render_files()
        platform = parsed.platform

        def work() -> None:
            try:
                if platform is Platform.XUNLEI:
                    client.refresh_token = self.config_store.get("xunlei_refresh_token", "")
                session = client.open_session(text, pwd, credential)
                files = client.list_files(session, "0", credential)
                self.post(lambda: self._on_parsed(session, files))
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or exc.__class__.__name__
                self.post(lambda: self._on_parse_failed(message))
            finally:
                self.post(lambda: self._set_busy(False, None))

        threading.Thread(target=work, daemon=True).start()

    def _on_parsed(self, session: ShareSession, files: list[PanFile]) -> None:
        self.session = session
        self.session_platform = parse_share(self.link_var.get()).platform if parse_share(
            self.link_var.get()
        ) else None
        self.nav_stack = []
        self.files = files
        self._render_files()
        self._persist_refreshed()
        title = session.title or "分享内容"
        self.set_status(f"解析成功：{title}（{len(files)} 项）")
        self.hint_label.configure(text=f"分享标题：{title}")

    def _on_parse_failed(self, message: str) -> None:
        self.set_status(f"解析失败：{message}")
        messagebox.showerror("解析失败", message, parent=self)

    def _persist_refreshed(self) -> None:
        if self.session_platform is None:
            return
        client = get_client(self.session_platform)
        refreshed = getattr(client, "refreshed_credential", None)
        if refreshed:
            self.config_store.set_credential(self.session_platform, refreshed)
            self.config_store.save()
            client.refreshed_credential = None

    # ------------------------------------------------------------------
    # 文件列表
    # ------------------------------------------------------------------
    def _render_files(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._row_tags = {}
        self._hover_row = ""
        folders = [f for f in self.files if f.is_dir]
        plain = [f for f in self.files if not f.is_dir]
        for index, item in enumerate(folders + plain):
            tags = (
                "dir" if item.is_dir else "file",
                "odd" if index % 2 else "even",
            )
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    ("📁 " if item.is_dir else "📄 ") + item.name,
                    "-" if item.is_dir else human_size(item.size),
                    item.kind_text,
                ),
                tags=tags,
            )
            self._row_tags[str(index)] = tags
        self._ordered = folders + plain
        path = " / ".join([name for _fid, name in self.nav_stack]) or "分享根目录"
        self.path_label.configure(text=f"当前位置：{path}")
        total_size = sum(f.size for f in plain)
        if self.files:
            self.file_footer.configure(
                text=f"共 {len(folders)} 个文件夹、{len(plain)} 个文件，合计 {human_size(total_size)}"
            )
        else:
            self.file_footer.configure(text="此目录为空")
        self._update_selection_hint()

    def _on_tree_motion(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if row == self._hover_row:
            return
        self._clear_hover_row()
        if row:
            self._hover_row = row
            base = self._row_tags.get(row, ())
            self.tree.item(row, tags=base + ("hover",))

    def _clear_hover_row(self) -> None:
        row, self._hover_row = self._hover_row, ""
        if row and self.tree.exists(row):
            self.tree.item(row, tags=self._row_tags.get(row, ()))

    def _update_selection_hint(self) -> None:
        files = self._selected_files()
        if not files:
            self.file_footer.configure(
                text=self.file_footer.cget("text") if self.files else "还没有解析结果"
            )
            return
        total = sum(f.size for f in files)
        self.file_footer.configure(
            text=f"已选中 {len(files)} 项，合计 {human_size(total)}（双击文件夹可进入）"
        )

    def _select_all(self) -> None:
        self.tree.selection_set(self.tree.get_children())

    def _selected_files(self) -> list[PanFile]:
        result = []
        for iid in self.tree.selection():
            try:
                result.append(self._ordered[int(iid)])
            except (ValueError, IndexError):
                continue
        return result

    def _on_tree_double_click(self, _event) -> None:
        selected = self._selected_files()
        if len(selected) == 1 and selected[0].is_dir:
            self._enter_dir(selected[0])

    def _enter_dir(self, item: PanFile) -> None:
        if self.session is None or self.session_platform is None or self._busy:
            return
        platform = self.session_platform
        credential = self.config_store.credential(platform)
        session = self.session
        self._set_busy(True, f"正在打开「{item.name}」…")

        def work() -> None:
            try:
                files = get_client(platform).list_files(session, item.fid, credential)
                self.post(lambda: self._on_dir_loaded(item, files))
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or exc.__class__.__name__
                self.post(lambda: self.set_status(f"打开目录失败：{message}"))
            finally:
                self.post(lambda: self._set_busy(False, None))

        threading.Thread(target=work, daemon=True).start()

    def _on_dir_loaded(self, item: PanFile, files: list[PanFile]) -> None:
        self.nav_stack.append((item.fid, item.name))
        self.files = files
        self._render_files()
        self.set_status(f"已进入「{item.name}」")

    def _go_up(self) -> None:
        if not self.nav_stack or self.session is None or self.session_platform is None:
            return
        self.nav_stack.pop()
        dir_id = self.nav_stack[-1][0] if self.nav_stack else "0"
        platform = self.session_platform
        credential = self.config_store.credential(platform)
        session = self.session
        self._set_busy(True, "正在返回上级目录…")

        def work() -> None:
            try:
                files = get_client(platform).list_files(session, dir_id, credential)
                self.post(lambda: self._on_up_loaded(files))
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or exc.__class__.__name__
                self.post(lambda: self.set_status(f"返回失败：{message}"))
            finally:
                self.post(lambda: self._set_busy(False, None))

        threading.Thread(target=work, daemon=True).start()

    def _on_up_loaded(self, files: list[PanFile]) -> None:
        self.files = files
        self._render_files()
        self.set_status("已返回上级目录")

    def _reload_dir(self) -> None:
        if self.session is None or self.session_platform is None or self._busy:
            return
        if not self.nav_stack:
            self._on_parse()
            return
        dir_id = self.nav_stack[-1][0]
        platform = self.session_platform
        credential = self.config_store.credential(platform)
        session = self.session
        self._set_busy(True, "正在刷新…")

        def work() -> None:
            try:
                files = get_client(platform).list_files(session, dir_id, credential)
                self.post(lambda: self._on_up_loaded(files))
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or exc.__class__.__name__
                self.post(lambda: self.set_status(f"刷新失败：{message}"))
            finally:
                self.post(lambda: self._set_busy(False, None))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # 下载
    # ------------------------------------------------------------------
    def _download_selected(self) -> None:
        files = [f for f in self._selected_files() if not f.is_dir]
        if not files:
            messagebox.showinfo("提示", "请先选中至少一个文件（文件夹请双击进入）", parent=self)
            return
        self._resolve_and_download(files)

    def _copy_links(self) -> None:
        files = [f for f in self._selected_files() if not f.is_dir]
        if not files:
            messagebox.showinfo("提示", "请先选中至少一个文件", parent=self)
            return
        self._resolve_and_download(files, copy_only=True)

    def _resolve_and_download(self, files: list[PanFile], copy_only: bool = False) -> None:
        if self.session is None or self.session_platform is None:
            messagebox.showinfo("提示", "请先解析一个分享链接", parent=self)
            return
        platform = self.session_platform
        client = get_client(platform)
        session = self.session
        credential = self.config_store.credential(platform)
        if platform is Platform.XUNLEI:
            client.refresh_token = self.config_store.get("xunlei_refresh_token", "")
        save_dir = self.config_store.download_dir()
        threads = self.config_store.threads(platform)
        collected: list[str] = []

        self._set_busy(True, f"正在获取 {len(files)} 个文件的下载直链…")

        def work() -> None:
            ok = 0
            failed = 0
            for index, item in enumerate(files, start=1):
                self.log(f"[{index}/{len(files)}] 解析 {item.name} …")
                try:
                    link = client.fetch_download(session, item, credential, self.log)
                    headers = client.download_headers(credential)
                    link.headers = {**headers, **(link.headers or {})}
                    if not link.filename:
                        link.filename = item.name
                    if copy_only:
                        collected.append(f"{link.filename}\n{link.url}")
                    else:
                        self.post(
                            lambda l=link, it=item: self._enqueue(
                                l, save_dir, threads, platform, session, it
                            )
                        )
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    message = str(exc) or exc.__class__.__name__
                    self.log(f"  失败：{item.name} — {message}")
                    if isinstance(exc, ApiError):
                        self.post(lambda m=message: messagebox.showerror("取链失败", m, parent=self))
            if copy_only and collected:
                text = "\n\n".join(collected)
                self.post(lambda: self._copy_to_clipboard(text, len(collected)))
            summary = f"直链获取完成：成功 {ok} 个"
            if failed:
                summary += f"，失败 {failed} 个"
            self.post(lambda: self.set_status(summary))
            self.post(self._persist_refreshed)
            self.post(lambda: self._set_busy(False, None))

        threading.Thread(target=work, daemon=True).start()

    def _copy_to_clipboard(self, text: str, count: int) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status(f"已复制 {count} 个直链到剪贴板（可粘贴到 IDM / 迅雷等工具）")

    def _enqueue(
        self,
        link,
        save_dir: str,
        threads: int,
        platform: Platform,
        session: ShareSession | None = None,
        source_file: PanFile | None = None,
    ) -> None:
        task = Download(
            task_id=f"t{len(self.tasks) + 1}_{int(os.times().elapsed * 1000) % 100000}",
            link=link,
            save_dir=save_dir,
            threads=threads,
            limiter=self.limiter,
            on_event=lambda t: self.post(lambda: self._refresh_card(t)),
        )
        task.cleanup_platform = platform  # type: ignore[attr-defined]
        task.source = (platform, session, source_file)  # type: ignore[attr-defined]
        self.tasks[task.id] = task
        self._add_task_card(task)
        self.queue.add(task)
        self.set_status(f"已加入下载队列：{task.filename}")

    def _add_task_card(self, task: Download) -> None:
        """创建任务卡片（重建界面时也复用）。"""
        card = TaskCard(
            self.dl_scroll.body,
            task,
            on_pause=self._pause_task,
            on_resume=self._resume_task,
            on_cancel=self._cancel_task,
            on_remove=self._remove_task,
        )
        card.pack(fill="x", pady=4)
        self.cards[task.id] = card
        self.empty_hint.pack_forget()
        card.refresh()

    def _refresh_card(self, task: Download) -> None:
        card = self.cards.get(task.id)
        if card is not None:
            card.refresh()

    def _pause_task(self, task: Download) -> None:
        task.pause()
        self._refresh_card(task)

    def _resume_task(self, task: Download) -> None:
        source = getattr(task, "source", None)
        if task.state in (DlState.FAILED, DlState.CANCELED) and source and source[2] is not None:
            self._refetch_and_start(task, source)
            return
        task.start()
        self._refresh_card(task)

    def _refetch_and_start(self, task: Download, source) -> None:
        """重试失败任务：先重新取一次直链，避免复用已失效的地址。"""
        platform, session, source_file = source
        if session is None or source_file is None:
            task.start()
            self._refresh_card(task)
            return
        client = get_client(platform)
        credential = self.config_store.credential(platform)
        if platform is Platform.XUNLEI:
            client.refresh_token = self.config_store.get("xunlei_refresh_token", "")
        self.set_status(f"正在重新获取直链：{task.filename} …")

        def work() -> None:
            try:
                link = client.fetch_download(session, source_file, credential, self.log)
                headers = client.download_headers(credential)
                link.headers = {**headers, **(link.headers or {})}
                if not link.filename:
                    link.filename = source_file.name

                def apply() -> None:
                    task.link = link
                    if link.size:
                        task.total = int(link.size)
                    task.start()
                    self._refresh_card(task)
                    self.set_status(f"已重新取链并开始下载：{task.filename}")

                self.post(apply)
            except Exception as exc:  # noqa: BLE001
                message = str(exc) or exc.__class__.__name__

                def mark_failed() -> None:
                    task.state = DlState.FAILED
                    task.message = message
                    task._notify(force=True)  # noqa: SLF001

                self.post(mark_failed)
                self.post(lambda: self.set_status(f"重新取链失败：{message}"))
            finally:
                self.post(self._persist_refreshed)

        threading.Thread(target=work, daemon=True).start()

    def _cancel_task(self, task: Download) -> None:
        task.cancel()
        self._refresh_card(task)

    def _remove_task(self, task: Download) -> None:
        task.cancel()
        card = self.cards.pop(task.id, None)
        if card is not None:
            card.destroy()
        self.tasks.pop(task.id, None)
        if task.state != DlState.COMPLETED:
            task.remove_files()
        if not self.tasks:
            self.empty_hint.pack(pady=20)
        self.set_status("已移除任务")

    def _resume_all(self) -> None:
        for task in self.tasks.values():
            if not task.is_active() and task.state in (DlState.PAUSED, DlState.FAILED):
                task.start()
        self.set_status("已继续所有暂停的任务")

    def _clear_finished(self) -> None:
        for task_id in [tid for tid, t in self.tasks.items() if t.state == DlState.COMPLETED]:
            self._remove_task(self.tasks[task_id])

    def _after_complete(self, task: Download) -> None:
        platform = getattr(task, "cleanup_platform", None)
        if platform is None or not task.link.cleanup_dir_fid:
            return
        client = get_client(platform)
        credential = self.config_store.credential(platform)
        session = self.session
        link = task.link

        def work() -> None:
            try:
                client.cleanup(session, link, credential)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, message: str | None) -> None:
        self._busy = busy
        self.parse_button.set_enabled(not busy)
        self.parse_button.set_busy(busy)
        self.parse_button.set_text("解析中…" if busy else "解析")
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        if message:
            self.set_status(message)

    def _prompt_credentials(self, platform: Platform) -> None:
        dialog = CredentialDialog(self, self.config_store)
        self.wait_window(dialog)
        if not self.config_store.credential(platform):
            messagebox.showinfo(
                "提示",
                f"{platform.label} 需要先登录才能解析下载。\n\n"
                "请在「账号与凭证」里点击「网页登录」，"
                "在打开的官方登录页完成登录后，程序会自动保存凭证。",
                parent=self,
            )

    def _open_credentials(self) -> None:
        dialog = CredentialDialog(self, self.config_store)
        self.wait_window(dialog)
        self.set_status("凭证已更新")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.config_store)
        self.wait_window(dialog)
        if dialog.changed:
            set_proxy(self.config_store.get("proxy", ""))
            self.limiter.set_rate(self.config_store.speed_limit())
            self.queue.set_max_concurrent(self.config_store.max_tasks())
            if getattr(dialog, "theme_changed", False):
                theme.set_palette(self.config_store.get("theme", "dark"))
                self._rebuild_ui()
                self.set_status("已切换为「%s」" % theme.THEME_LABELS.get(
                    theme.palette_name(), theme.palette_name()))
            else:
                self.set_status("设置已保存")

    def _rebuild_ui(self) -> None:
        """切换配色后重建整个界面（tkinter 控件颜色无法逐个刷新）。"""
        link_text = self.link_var.get()
        pwd_text = self.pwd_var.get()
        status = self.status_label.cget("text")
        tasks = list(self.tasks.values())

        for child in self.winfo_children():
            child.destroy()
        self.cards.clear()
        self.fonts = theme.apply_theme(self)
        self._build_ui()

        self.link_var.set(link_text)
        self.pwd_var.set(pwd_text)
        self._on_link_changed()
        self._render_files()
        for task in tasks:
            self._add_task_card(task)
        if not tasks:
            self.empty_hint.pack(pady=20)
        self.set_status(status or "就绪")

    def _show_details(self) -> None:
        from .details import DetailsDialog

        dialog = DetailsDialog(self, self.config_store)
        self.wait_window(dialog)

    def _show_help(self) -> None:
        text = (
            "使用步骤\n"
            "1. 点右上角「账号与凭证」→ 选平台 → 点「网页登录」，在弹出的官方登录页里\n"
            "   登录你的账号，程序会自动读取并保存凭证（无需手动找 Cookie）；\n"
            "2. 复制网盘分享链接（或整段分享文案，含提取码也行），粘贴到顶部输入框；\n"
            "3. 点「解析」，稍等片刻即可看到文件列表；\n"
            "4. 勾选文件（按住 Ctrl / Shift 可多选），点「下载选中」开始多线程下载；\n"
            "   - 双击文件夹可进入子目录，用「返回上级」回到上一级；\n"
            "   - 「复制直链」可拿到下载地址，粘贴到 IDM / 迅雷等工具里使用。\n\n"
            "关于登录\n"
            "· 登录窗口使用系统自带的 WebView2 内核打开官方页面，账号密码只提交给官方；\n"
            "· 登录窗口采用无痕模式，不会在本机残留浏览器登录状态；\n"
            "· 提取到的凭证只保存在本机配置文件里，不会上传到任何服务器；\n"
            "· 如果某个平台自动提取失败，也可以在「账号与凭证」里手动粘贴 Cookie / token。\n\n"
            "下载说明\n"
            "· 采用 Range 分片 + 多线程 + 断点续传，暂停后可继续；\n"
            "· 若服务器不支持分片会自动回退单线程；\n"
            "· 线程数、同时下载任务数、限速、代理都能在「设置」里调整；\n"
            "· 夸克/迅雷/百度取直链时会在你的网盘里建一个「亦析临时转存」目录，"
            "下载完成后会自动清理。\n\n"
            "说明\n"
            "· 本工具只做解析与下载加速，请勿用于传播侵权内容；\n"
            "· 凭证只保存在本机配置文件里，不会上传到任何服务器。"
        )
        messagebox.showinfo("使用说明", text, parent=self)

    def _on_close(self) -> None:
        try:
            from ..weblogin import get_login_service

            get_login_service().shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.config_store.set(
            "window",
            {
                "width": self.winfo_width(),
                "height": self.winfo_height(),
                "x": self.winfo_x(),
                "y": self.winfo_y(),
            },
        )
        self.config_store.save()
        self.queue.stop()
        for task in list(self.tasks.values()):
            task.cancel()
        self.destroy()
