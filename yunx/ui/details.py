"""详细信息窗口：应用介绍、支持平台、功能特性、技术说明、项目仓库与免责声明。

内容参照安卓版「关于云析」页（AboutScreen）整理，并补充了电脑端的信息。
"""

from __future__ import annotations

import tkinter as tk
import webbrowser

from .. import APP_NAME, __version__
from ..config import Config
from ..util import apply_window_icon, asset_path
from . import theme
from .dialogs import _BaseDialog
from .widgets import AnimatedButton, ScrollableFrame

UI = "Microsoft YaHei UI"

WECHAT_ID = "lonely0411"
CONTACT_MAIL = "3260254728@qq.com"

SUPPORTED_PLATFORMS = ("夸克网盘", "UC 网盘", "迅雷网盘", "百度网盘", "移动云盘(139)", "123 云盘")

FEATURES = (
    ("一键解析分享链接", "夸克 / UC / 迅雷 / 百度 / 139 / 123 分享链接与提取码自动识别"),
    ("高速分片下载", "多线程并发 + 断点续传，支持暂停 / 继续 / 重试，服务端不支持分片时自动回退单线程"),
    ("内置网页登录", "在程序内打开官方登录页扫码/验证码登录，凭证自动保存与续期"),
    ("取链不占空间", "夸克直接取链无需转存；迅雷/百度的临时转存目录下载后自动清理"),
    ("下载任务管理", "进度、速度、剩余时间、线程数实时显示，支持全局限速与代理"),
    ("界面风格切换", "蓝色风格 / 白色风格一键切换"),
)

STACK = (
    ("运行环境", "Windows 10 / 11（单文件 exe，免安装）"),
    ("界面", "Python + tkinter（自绘圆角动画控件）"),
    ("内置浏览器", "系统自带 WebView2（扫码登录 / 凭证读取）"),
    ("接口实现", "移植自开源项目 YunX（云析）的解析与下载逻辑"),
)


def _repo_url(config: Config) -> str:
    return str(config.get("repo_url", "") or "").strip()


class DetailsDialog(_BaseDialog):
    """详细信息（关于）窗口。"""

    def __init__(self, master, config: Config) -> None:
        super().__init__(master, f"{APP_NAME} · 详细信息", 660, 640)
        self.config_store = config

        head = tk.Frame(self.body, bg=theme.BG)
        head.pack(fill="x", padx=22, pady=(18, 4))
        tk.Label(
            head, text=APP_NAME, bg=theme.BG, fg=theme.TEXT,
            font=(UI, 16, "bold"),
        ).pack(side="left")
        tk.Label(
            head, text=f"v{__version__}  ·  网盘链接解析与高速下载", bg=theme.BG,
            fg=theme.TEXT_FAINT, font=(UI, 9),
        ).pack(side="left", padx=(10, 0), pady=(6, 0))
        AnimatedButton(
            head, "关闭", self.destroy, kind="quiet", parent_bg=theme.BG
        ).pack(side="right")

        panel = tk.Frame(self.body, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.BORDER)
        panel.pack(fill="both", expand=True, padx=22, pady=(6, 18))
        self.scroll = ScrollableFrame(panel, bg=theme.PANEL)
        self.scroll.pack(fill="both", expand=True, padx=4, pady=4)
        body = self.scroll.body

        self._section(body, "应用简介",
                      f"{APP_NAME} 是一款网盘分享链接解析与高速下载工具："
                      "粘贴分享链接、在程序内登录网盘账号后，即可浏览分享内容并多线程高速下载文件。"
                      "解析与下载逻辑移植自开源安卓应用 YunX（云析）。")

        tk.Label(
            body, text="支持平台", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 2))
        chips = tk.Frame(body, bg=theme.PANEL)
        chips.pack(fill="x", padx=16, pady=(0, 4))
        for name in SUPPORTED_PLATFORMS:
            tk.Label(
                chips, text=name, bg=theme.PANEL_ALT, fg=theme.ACCENT,
                font=(UI, 9), padx=10, pady=4,
            ).pack(side="left", padx=(0, 8), pady=3)
        tk.Label(
            body, text="共 6 个网盘，均支持分享解析与多线程下载", bg=theme.PANEL,
            fg=theme.TEXT_FAINT, font=(UI, 9), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 10))

        tk.Label(
            body, text="功能特性", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(6, 4))
        for title, desc in FEATURES:
            row = tk.Frame(body, bg=theme.PANEL)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(
                row, text="•", bg=theme.PANEL, fg=theme.ACCENT,
                font=(UI, 10, "bold"),
            ).pack(side="left", padx=(0, 6))
            holder = tk.Frame(row, bg=theme.PANEL)
            holder.pack(side="left", fill="x", expand=True)
            tk.Label(
                holder, text=title, bg=theme.PANEL, fg=theme.TEXT,
                font=(UI, 10, "bold"), anchor="w",
            ).pack(fill="x")
            tk.Label(
                holder, text=desc, bg=theme.PANEL, fg=theme.TEXT_DIM,
                font=(UI, 9), anchor="w", justify="left", wraplength=520,
            ).pack(fill="x")
        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=16, pady=12)

        tk.Label(
            body, text="技术说明", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 4))
        for key, value in STACK:
            holder = tk.Frame(body, bg=theme.PANEL)
            holder.pack(fill="x", padx=16, pady=2)
            tk.Label(
                holder, text=key, bg=theme.PANEL, fg=theme.TEXT_DIM,
                font=(UI, 9), width=10, anchor="w",
            ).pack(side="left")
            tk.Label(
                holder, text=value, bg=theme.PANEL, fg=theme.TEXT,
                font=(UI, 9), anchor="w", justify="left", wraplength=440,
            ).pack(side="left", fill="x", expand=True)
        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=16, pady=12)

        # ---------- 项目仓库 ----------
        tk.Label(
            body, text="项目仓库", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 4))
        repo = _repo_url(config)
        self.repo_label = tk.Label(
            body,
            text=repo or "尚未设置 —— 可在「设置 → 项目仓库」里填写",
            bg=theme.PANEL, fg=theme.ACCENT if repo else theme.TEXT_FAINT,
            font=(UI, 9), anchor="w", justify="left", wraplength=520,
        )
        self.repo_label.pack(fill="x", padx=16)
        repo_row = tk.Frame(body, bg=theme.PANEL)
        repo_row.pack(fill="x", padx=16, pady=(6, 4))
        if repo:
            AnimatedButton(
                repo_row, "打开仓库", lambda: webbrowser.open(repo),
                kind="accent", parent_bg=theme.PANEL,
            ).pack(side="left")
            AnimatedButton(
                repo_row, "复制地址", lambda: self._copy(repo),
                kind="ghost", parent_bg=theme.PANEL,
            ).pack(side="left", padx=8)
        tk.Label(
            body, text="上游项目：https://github.com/CYQawa/YunX（AGPL-3.0）",
            bg=theme.PANEL, fg=theme.TEXT_FAINT, font=(UI, 9), anchor="w",
        ).pack(fill="x", padx=16)
        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=16, pady=12)

        self._section(
            body, "免责声明",
            "本工具仅用于个人学习与合法的文件传输，解析与下载能力依赖各网盘官方接口；"
            "请勿用于传播盗版、侵权或违法内容，使用产生的后果由使用者自行承担。\n"
            "本程序基于 GNU AGPL-3.0 协议开源，接口逻辑版权归原项目 CYQawa/YunX 所有。",
            pady_bottom=16,
        )

        # ---------- 制作声明 ----------
        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(
            body, text="制作声明", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(
            body,
            text=(
                f"{APP_NAME} 由 亦亦 制作与维护，基于开源项目 YunX（云析）二次开发。\n"
                "本程序完全免费开源，仅在本人的代码仓库发布；"
                "如果你是通过付费购买得到它的，那一定是被坑了，请及时退款。\n"
                "欢迎提 Issue 反馈问题，也欢迎点个 Star 支持一下。"
            ),
            bg=theme.PANEL, fg=theme.TEXT_DIM, font=(UI, 9),
            anchor="w", justify="left", wraplength=520,
        ).pack(fill="x", padx=16, pady=(0, 10))

        # ---------- 赞赏支持 ----------
        tk.Label(
            body, text="赞赏支持", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(6, 2))
        tk.Label(
            body, text="如果这个工具帮到了你，可以请我喝杯奶茶 ☕ 谢谢支持！",
            bg=theme.PANEL, fg=theme.TEXT_DIM, font=(UI, 9), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 8))
        try:
            self._reward_image = tk.PhotoImage(file=asset_path("assets/reward_qr.png"))
            holder = tk.Frame(body, bg=theme.PANEL)
            holder.pack(pady=(0, 6))
            tk.Label(holder, image=self._reward_image, bg=theme.PANEL, bd=0).pack()
            tk.Label(
                body, text="微信扫码赞赏 · 亦亦 的赞赏码", bg=theme.PANEL,
                fg=theme.TEXT_FAINT, font=(UI, 9),
            ).pack(pady=(0, 18))
        except Exception:  # noqa: BLE001
            tk.Label(
                body, text="（赞赏码图片缺失）", bg=theme.PANEL,
                fg=theme.TEXT_FAINT, font=(UI, 9),
            ).pack(pady=(0, 18))

        # ---------- 反馈与联系 ----------
        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(
            body, text="反馈与联系", bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(
            body, text="遇到问题、想提建议，或者只是想聊两句，都可以找我：",
            bg=theme.PANEL, fg=theme.TEXT_DIM, font=(UI, 9), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 8))

        for label, value in (("微信", WECHAT_ID), ("邮箱", CONTACT_MAIL)):
            row = tk.Frame(body, bg=theme.PANEL)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(
                row, text=label, bg=theme.PANEL, fg=theme.TEXT_DIM,
                font=(UI, 9), width=6, anchor="w",
            ).pack(side="left")
            tk.Label(
                row, text=value, bg=theme.PANEL, fg=theme.ACCENT,
                font=(UI, 10, "bold"), anchor="w",
            ).pack(side="left")
            AnimatedButton(
                row, "复制", (lambda v=value: self._copy(v)), kind="quiet",
                parent_bg=theme.PANEL, height=26, padx=12,
            ).pack(side="left", padx=8)
            if label == "邮箱":
                AnimatedButton(
                    row, "发邮件", (lambda v=value: self._mailto(v)), kind="ghost",
                    parent_bg=theme.PANEL, height=26, padx=12,
                ).pack(side="left")
        tk.Label(
            body, text="（也可以直接在仓库提 Issue，我会尽快看）",
            bg=theme.PANEL, fg=theme.TEXT_FAINT, font=(UI, 9), anchor="w",
        ).pack(fill="x", padx=16, pady=(8, 18))

        apply_window_icon(self)

    # -- 小工具 -------------------------------------------------------------
    def _mailto(self, address: str) -> None:
        try:
            webbrowser.open(f"mailto:{address}")
        except Exception:  # noqa: BLE001
            pass

    def _copy(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:  # noqa: BLE001
            pass

    def _section(self, parent, title: str, body_text: str, pady_bottom: int = 10) -> None:
        tk.Label(
            parent, text=title, bg=theme.PANEL, fg=theme.TEXT,
            font=(UI, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(
            parent, text=body_text, bg=theme.PANEL, fg=theme.TEXT_DIM,
            font=(UI, 9), anchor="w", justify="left", wraplength=520,
        ).pack(fill="x", padx=16, pady=(0, pady_bottom))
