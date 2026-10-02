"""验证同一进程内能否先后多次调用 webview.start()（每次一个窗口）。"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webview

from yunx.weblogin import cookies_for_uri

OUT = os.path.join(os.environ.get("TEMP", "."), "yixi_seq.json")
report: dict = {}
_signal_lock = threading.Lock()


def run_session(index: int) -> None:
    current = threading.current_thread()
    original_name = current.name
    current.name = "MainThread"
    original_signal = signal.signal

    def safe_signal(*args, **kwargs):
        try:
            return original_signal(*args, **kwargs)
        except ValueError:
            return None

    with _signal_lock:
        signal.signal = safe_signal  # type: ignore[assignment]
    try:
        window = webview.create_window(
            f"会话{index}", "https://pan.baidu.com/", width=600, height=420
        )

        def after_start(win) -> None:
            try:
                time.sleep(4)
                report[f"session{index}_url"] = win.get_current_url()
                report[f"session{index}_js"] = win.evaluate_js("3*4")
                report[f"session{index}_cookies"] = len(
                    cookies_for_uri(win, "https://pan.baidu.com/", timeout=8)
                )
            except Exception as exc:  # noqa: BLE001
                report[f"session{index}_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                win.destroy()

        webview.start(after_start, window, gui="edgechromium", private_mode=True)
        report[f"session{index}_started"] = True
    except Exception as exc:  # noqa: BLE001
        import traceback

        report[f"session{index}_fatal"] = traceback.format_exc()
    finally:
        with _signal_lock:
            signal.signal = original_signal  # type: ignore[assignment]
        current.name = original_name
        report[f"session{index}_done"] = True


def main() -> int:
    for index in (1, 2, 3):
        thread = threading.Thread(target=run_session, args=(index,))
        thread.start()
        thread.join(timeout=90)
        if thread.is_alive():
            report[f"session{index}_timeout"] = True
            break
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
