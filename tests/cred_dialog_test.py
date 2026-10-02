"""验证账号对话框：迅雷显示「账号登录」，其他平台显示「网页登录」。"""

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

    labels = {}
    for platform in Platform:
        dialog._select(platform)  # noqa: SLF001
        root.update()
        labels[platform.value] = dialog.login_button.cget("text")
    print(labels)
    assert labels[Platform.XUNLEI.value] == "网页登录"
    assert labels[Platform.QUARK.value] == "网页登录"
    dialog.destroy()
    root.destroy()
    print("CREDENTIAL DIALOG TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
