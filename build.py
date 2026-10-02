"""打包脚本：生成单文件 exe（含图标与 WebView2 登录组件）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
NAME = "亦析PC"

ARGS = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name",
    NAME,
    "--icon",
    os.path.join(BASE, "app.ico"),
    "--add-data",
    f"{os.path.join(BASE, 'app.ico')}{os.pathsep}.",
    "--add-data",
    f"{os.path.join(BASE, 'icon.png')}{os.pathsep}.",
    "--add-data",
    f"{os.path.join(BASE, 'assets', 'reward_qr.png')}{os.pathsep}assets",
    "--collect-submodules",
    "yunx",
    "--collect-all",
    "webview",
    "--collect-all",
    "clr_loader",
    "--hidden-import",
    "clr",
    "--distpath",
    os.path.join(BASE, "dist"),
    "--workpath",
    os.path.join(BASE, "build"),
    os.path.join(BASE, "app.py"),
]


def main() -> int:
    for name in ("app.ico", "icon.png"):
        if not os.path.exists(os.path.join(BASE, name)):
            print(f"缺少资源 {name}，请先运行 make_icon.py 生成图标")
            return 1
    if shutil.which("pyinstaller") is None:
        pass  # 用 python -m PyInstaller，无需 PATH 上有命令
    print("开始打包…")
    return subprocess.call(ARGS, cwd=BASE)


if __name__ == "__main__":
    raise SystemExit(main())
