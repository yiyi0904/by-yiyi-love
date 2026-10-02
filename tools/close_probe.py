"""列出被测进程的顶层窗口（标题 + 类名），并向 TkTopLevel 发 WM_CLOSE。"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

import win32con
import win32gui
import win32process

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def windows_of(pid: int) -> list[tuple[int, str, str]]:
    result: list[tuple[int, str, str]] = []

    def visit(handle, _acc):
        _tid, win_pid = win32process.GetWindowThreadProcessId(handle)
        if win_pid == pid:
            result.append(
                (handle, win32gui.GetWindowText(handle), win32gui.GetClassName(handle))
            )
        return True

    win32gui.EnumWindows(visit, None)
    return result


def main() -> int:
    exe = sys.argv[1] if len(sys.argv) > 1 else ""
    if exe:
        proc = subprocess.Popen([exe])
    else:
        proc = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py")])
    time.sleep(12)

    pid = proc.pid
    # 单文件 exe 会再起一个子进程承载界面
    kids = subprocess.run(
        ["wmic", "process", "where", f"ParentProcessId={pid}", "get", "ProcessId"],
        capture_output=True,
        text=True,
    ).stdout
    pids = {pid}
    for token in kids.split():
        if token.isdigit():
            pids.add(int(token))

    found = []
    for candidate in pids:
        found.extend(windows_of(candidate))
    print("窗口列表：")
    for handle, title, cls in found:
        print(f"  hwnd={handle} class={cls!r} title={title!r}")

    target = next((h for h, t, c in found if c == "TkTopLevel"), 0)
    print("发送 WM_CLOSE 到：", target)
    if target:
        ctypes.windll.user32.PostMessageW(target, win32con.WM_CLOSE, 0, 0)
    try:
        code = proc.wait(timeout=30)
        print("退出码：", code)
    except subprocess.TimeoutExpired:
        print("未退出（超时）")
        win32gui.EnumWindows(
            lambda h, _a: print("  仍存在:", h, repr(win32gui.GetWindowText(h)))
            if win32gui.GetWindowText(h).startswith("亦析")
            else True,
            None,
        )
        proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
