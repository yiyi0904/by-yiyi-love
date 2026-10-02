"""检查账号对话框：每个平台下底部按钮都要完整可见（不被挤出窗口）。"""

from __future__ import annotations

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.config import Config
from yunx.models import Platform
from yunx.ui import theme
from yunx.ui.dialogs import CredentialDialog


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    theme.apply_theme(root)
    dialog = CredentialDialog(root, Config())
    root.update()

    dialog_h = dialog.winfo_height()
    dialog_w = dialog.winfo_width()
    print(f"对话框尺寸: {dialog_w}x{dialog_h}")
    print(
        "对话框状态: mapped=%s viewable=%s state=%s"
        % (dialog.winfo_ismapped(), dialog.winfo_viewable(), dialog.state())
    )
    dialog.deiconify()
    dialog.update()
    print(
        "deiconify 后: mapped=%s viewable=%s 按钮 mapped=%s"
        % (dialog.winfo_ismapped(), dialog.winfo_viewable(), dialog.login_button.winfo_ismapped())
    )
    for platform in Platform:
        dialog._select(platform)  # noqa: SLF001
        dialog.update_idletasks()
        dialog.update()
        button = dialog.login_button
        assert button.winfo_ismapped(), f"{platform.value}: 登录按钮没有显示"
        top = button.winfo_rooty() - dialog.winfo_rooty()
        bottom = top + button.winfo_height()
        left = button.winfo_rootx() - dialog.winfo_rootx()
        right = left + button.winfo_width()
        ok = 0 <= top and bottom <= dialog.winfo_height() and right <= dialog.winfo_width()
        print(
            f"  {platform.value:8s} 按钮位置 x={left}..{right} y={top}..{bottom} "
            f"{'OK' if ok else '越界!'}"
        )
        assert ok, f"{platform.value}: 按钮超出可视区 (bottom={bottom}, h={dialog.winfo_height()})"
        # 备用按钮只在迅雷显示
        if platform is Platform.XUNLEI:
            assert dialog.alt_button.winfo_ismapped(), "迅雷缺少账号密码登录按钮"

    dialog.destroy()
    root.destroy()
    print("DIALOG LAYOUT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
