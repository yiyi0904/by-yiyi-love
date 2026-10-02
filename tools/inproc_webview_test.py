"""验证：在 tkinter 主循环之外的后台线程里常驻运行 pywebview，并按需开关窗口。"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webview

from yunx.weblogin import cookies_for_uri

OUT = os.path.join(os.environ.get("TEMP", "."), "yixi_inproc.json")
report: dict = {}


def fake_main_thread() -> None:
    """pywebview 只检查线程名，用它骗过主线程校验。"""
    threading.current_thread().name = "MainThread"


def start_notifier() -> None:
    fake_main_thread()
    original_signal = signal.signal

    def safe_signal(*args, **kwargs):
        try:
            return original_signal(*args, **kwargs)
        except ValueError:
            return None

    signal.signal = safe_signal  # type: ignore[assignment]
    try:
        keeper = webview.create_window("keeper", html="<html></html>", hidden=True,
                                       width=1, height=1)
        webview.start(on_started, keeper, gui="edgechromium", private_mode=True)
    except Exception as exc:  # noqa: BLE001
        report["start_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.signal = original_signal  # type: ignore[assignment]
        report["start_returned"] = True
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)


def on_started(keeper) -> None:
    report["keeper_ok"] = True
    thread = threading.Thread(target=round_trip, daemon=True)
    thread.start()


def round_trip() -> None:
    """模拟两次「打开登录窗口 → 读 Cookie → 关闭」的完整流程。"""
    for index in (1, 2):
        try:
            window = webview.create_window(
                f"登录测试 {index}", "https://pan.baidu.com/", width=700, height=500
            )
            report[f"window{index}_created"] = window is not None
            time.sleep(5)
            report[f"window{index}_url"] = window.get_current_url()
            report[f"window{index}_js"] = window.evaluate_js("6*7")
            report[f"window{index}_cookies"] = len(
                cookies_for_uri(window, "https://pan.baidu.com/", timeout=8)
            )
            window.destroy()
            time.sleep(1)
        except Exception as exc:  # noqa: BLE001
            import traceback

            report[f"window{index}_error"] = traceback.format_exc()
    report["tk_alive"] = report.get("tk_checked")


def main() -> int:
    root = tk.Tk()
    root.title("tk 主窗口")
    root.geometry("400x200")
    tk.Label(root, text="tkinter 主窗口（应当全程可用）").pack(pady=30)
    tk.Button(root, text="点我", command=lambda: report.update(tk_clicked=True)).pack()

    def watch() -> None:
        try:
            report["tk_checked"] = bool(root.winfo_exists())
        except Exception:  # noqa: BLE001
            report["tk_checked"] = False
        root.after(500, watch)

    watch()
    threading.Thread(target=start_notifier, daemon=True).start()

    def quit_later() -> None:
        time.sleep(22)
        report["tk_checked"] = report.get("tk_checked")
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        root.after(0, root.destroy)

    threading.Thread(target=quit_later, daemon=True).start()
    root.mainloop()

    for window in list(webview.windows):
        try:
            window.destroy()
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
