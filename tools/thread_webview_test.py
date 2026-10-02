"""验证 pywebview 能否与 tkinter 主循环共存（子线程 + 线程名伪装）。"""

from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
import traceback

import webview

OUT = os.path.join(os.environ.get("TEMP", "."), "yunx_thread_webview.json")
report: dict = {}


def run_login(root: tk.Tk) -> None:
    def work() -> None:
        try:
            current = threading.current_thread()
            original = current.name
            current.name = "MainThread"
            try:
                window = webview.create_window(
                    "登录测试", "https://pan.baidu.com/", width=900, height=640
                )
                webview.start(lambda w: on_ready(w), window, gui="edgechromium", private_mode=True)
            finally:
                current.name = original
        except Exception:  # noqa: BLE001
            report["error"] = traceback.format_exc()
            with open(OUT, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)

    def on_ready(window) -> None:
        try:
            time.sleep(3)
            report["url"] = window.get_current_url()
            report["title"] = window.evaluate_js("document.title")
            raw = window.get_cookies() or []
            names = []
            for sc in raw:
                try:
                    names.extend(sc.keys())
                except Exception:  # noqa: BLE001
                    pass
            report["cookies"] = names
            report["tk_alive"] = bool(root.winfo_exists())
        except Exception:  # noqa: BLE001
            report["error2"] = traceback.format_exc()
        finally:
            window.destroy()
            with open(OUT, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
            root.after(0, root.destroy)

    threading.Thread(target=work, daemon=True).start()


def main() -> int:
    root = tk.Tk()
    root.title("tk 主窗口")
    root.geometry("420x220")
    tk.Label(root, text="tkinter 主窗口：登录窗口应能同时打开").pack(pady=40)
    root.after(300, lambda: run_login(root))

    def tick() -> None:
        if root.winfo_exists():
            root.after(200, tick)

    tick()
    root.mainloop()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
