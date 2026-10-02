"""定位：后台线程里 start() 卡住，是线程名伪装还是 signal 补丁造成的。

用法：python thread_start_test.py <spoof|nospoof> <patch|nopatch>
"""

from __future__ import annotations

import signal
import sys
import threading
import time

import webview


_ORIGINAL_SIGNAL = signal.signal


def safe_signal(*args, **kwargs):
    try:
        return _ORIGINAL_SIGNAL(*args, **kwargs)
    except ValueError:
        return None


def main() -> int:
    spoof = len(sys.argv) > 1 and sys.argv[1] == "spoof"
    patch = len(sys.argv) > 2 and sys.argv[2] == "patch"
    print(f"spoof={spoof} patch={patch}", flush=True)

    def run() -> None:
        current = threading.current_thread()
        original_name = current.name
        original_signal = signal.signal
        if spoof:
            current.name = "MainThread"
        if patch:
            signal.signal = safe_signal  # type: ignore[assignment]
        try:
            window = webview.create_window("测试", "https://example.com", width=600, height=400)

            def closer() -> None:
                time.sleep(6)
                print("  shown:", window.events.shown.is_set(), flush=True)
                from webview.platforms import winforms

                print("  instances:", list(winforms.BrowserView.instances), flush=True)
                try:
                    window.destroy()
                    print("  destroy ok", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print("  destroy raised:", type(exc).__name__, exc, flush=True)

            threading.Thread(target=closer, daemon=True).start()
            webview.start(gui="edgechromium", private_mode=True)
            print("  start returned", flush=True)
        finally:
            if patch:
                signal.signal = original_signal  # type: ignore[assignment]
            if spoof:
                current.name = original_name

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(45)
    print("thread alive:", thread.is_alive(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
