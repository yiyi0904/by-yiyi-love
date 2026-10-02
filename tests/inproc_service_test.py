"""测试同进程登录服务：开窗口 → 关闭 → 结果回传 → 再开一次。"""

from __future__ import annotations

import os
import queue
import sys
import time
import faulthandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.models import Platform
from yunx.weblogin import get_login_service


def wait_window_titles(timeout: float = 40.0) -> list[str]:
    import webview

    deadline = time.time() + timeout
    while time.time() < deadline:
        titles = [w.title for w in webview.windows]
        if any("登录" in t for t in titles):
            return titles
        time.sleep(0.5)
    return [w.title for w in webview.windows]


def main() -> int:
    faulthandler.dump_traceback_later(50, exit=True)
    service = get_login_service()

    for round_index in (1, 2):
        result_queue = service.open(Platform.QUARK)
        deadline = time.time() + 60
        while time.time() < deadline and not service.is_running():
            time.sleep(0.3)
        assert service.is_running(), "登录会话没有建立"
        titles = wait_window_titles()
        print(f"round {round_index}: windows = {titles}")
        assert any("登录" in t for t in titles), "登录窗口没有出现"
        time.sleep(6)
        service.close_active()
        try:
            payload = result_queue.get(timeout=20)
        except queue.Empty:
            print("round", round_index, "FAILED: 没有收到结果")
            return 1
        print(f"round {round_index}: result = {payload.get('ok')} / {payload.get('error')}")
        assert payload.get("ok") is False, payload
        time.sleep(1)

    service.shutdown()
    print("SERVICE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
