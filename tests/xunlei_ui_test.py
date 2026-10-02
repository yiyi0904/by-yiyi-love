"""测试迅雷登录对话框的界面与失败分支（不涉及真实账号）。"""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.platforms.xunlei import XunleiClient
from yunx.ui import theme
from yunx.ui.xunlei_login import XunleiLoginDialog


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    theme.apply_theme(root)

    client = XunleiClient()
    dialog = XunleiLoginDialog(root, client)
    root.update()
    print("对话框已创建:", dialog.title())

    # 空账号点登录 → 提示
    dialog._submit()  # noqa: SLF001
    root.update()
    print("空输入提示:", dialog.status.cget("text"))
    assert "账号" in dialog.status.cget("text")

    # 假账号登录 → 服务端返回错误
    dialog.user_var.set("10000000000")
    dialog.pwd_var.set("definitely-wrong-password")
    dialog._submit()  # noqa: SLF001
    deadline = time.time() + 40
    while time.time() < deadline and dialog._busy:  # noqa: SLF001
        root.update()
        time.sleep(0.1)
    root.update()
    print("假账号结果:", dialog.status.cget("text"))
    assert dialog.access_token == ""
    assert "错误" in dialog.status.cget("text") or "失败" in dialog.status.cget("text")

    dialog.destroy()
    root.destroy()
    print("XUNLEI UI TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
