"""检查程序正常关闭时的退出码：普通启动关闭 / 跑完完整自检（含登录组件）后退出。"""

from __future__ import annotations

import subprocess
import sys
import time

import os

import win32con
import win32gui
import win32process

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WM_CLOSE = 0x0010


def scan_windows(prefix: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []

    def visit(handle, _acc):
        if win32gui.IsWindowVisible(handle):
            title = win32gui.GetWindowText(handle)
            if title.startswith(prefix):
                _tid, pid = win32process.GetWindowThreadProcessId(handle)
                result.append((handle, pid, win32gui.GetClassName(handle)))
        return True

    win32gui.EnumWindows(visit, None)
    return result


def find_window(prefix: str, exclude_pids: set[int], timeout: float = 60.0) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for handle, pid, cls in scan_windows(prefix):
            if pid not in exclude_pids and cls == "TkTopLevel":
                return handle
        time.sleep(0.5)
    return 0


def run_gui_case(exe: str) -> None:
    use_source = not exe
    before = {pid for _h, pid, _c in scan_windows("亦析 PC")}
    if use_source:
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE, "app.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    else:
        proc = subprocess.Popen([exe])
    hwnd = find_window("亦析 PC", exclude_pids=before)
    print(f"普通启动: hwnd={hwnd}", flush=True)
    if not hwnd:
        proc.kill()
        return
    time.sleep(3)
    win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)
    try:
        code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "TIMEOUT(被强杀)"
        if use_source and proc.stdout:
            print("--- 子进程输出 ---")
            print(proc.stdout.read().decode("utf-8", "ignore")[-3000:])
    print(f"普通启动关闭: exit code = {code}", flush=True)


def run_script_case(exe: str, flag: str) -> None:
    proc = subprocess.Popen([exe, flag])
    try:
        code = proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "TIMEOUT(被强杀)"
    print(f"{flag}: exit code = {code}", flush=True)


def main() -> int:
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        BASE, "dist", "亦析PC.exe"
    )
    run_gui_case(exe)
    run_script_case(exe, "--selftest")
    run_script_case(exe, "--spawntest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
