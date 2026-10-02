"""逐步排查同进程登录会话的结果交付。"""

from __future__ import annotations

import os
import queue
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.models import Platform
from yunx.weblogin import get_login_service


def main() -> int:
    service = get_login_service()
    result = service.open(Platform.QUARK)

    for _ in range(300):
        if service.is_running():
            break
        time.sleep(0.1)
    print("active:", service.is_running(), flush=True)
    time.sleep(8)

    session = service._active  # noqa: SLF001
    window = getattr(session, "window", None)
    print("window:", window, flush=True)
    print("shown event:", window.events.shown.is_set(), "uid:", window.uid, flush=True)
    print("done/delivered:", getattr(session, "done", None), getattr(session, "delivered", None), flush=True)

    import webview
    from webview.platforms import winforms

    print("webview.windows:", len(webview.windows), flush=True)
    print("BrowserView.instances:", list(winforms.BrowserView.instances), flush=True)

    try:
        window.destroy()
        print("direct destroy ok", flush=True)
    except Exception as exc:  # noqa: BLE001
        print("direct destroy raised:", type(exc).__name__, exc, flush=True)
    time.sleep(3)
    print("after destroy, windows:", len(webview.windows),
          "instances:", list(winforms.BrowserView.instances), flush=True)
    service.close_active()
    print("close_active returned", flush=True)
    try:
        payload = result.get(timeout=25)
        print("result:", payload, flush=True)
    except queue.Empty:
        print("NO RESULT in 25s", flush=True)
        print("session state:", getattr(session, "done", None),
              getattr(session, "delivered", None), flush=True)
    service.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
