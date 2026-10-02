"""最小用例：主线程 start()（不带 func），外部线程 destroy()。"""

from __future__ import annotations

import threading
import time

import webview


def main() -> int:
    window = webview.create_window("最小用例", "https://example.com", width=600, height=400)

    def closer() -> None:
        time.sleep(6)
        print("shown:", window.events.shown.is_set(), flush=True)
        try:
            window.destroy()
            print("destroy ok", flush=True)
        except Exception as exc:  # noqa: BLE001
            print("destroy raised:", type(exc).__name__, exc, flush=True)

    threading.Thread(target=closer, daemon=True).start()
    webview.start(gui="edgechromium", private_mode=True)
    print("start returned", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
