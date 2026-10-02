"""验证 weblogin.cookies_for_uri 在真实 WebView2 会话里能按域名读到 Cookie。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webview

from yunx.models import Platform
from yunx.weblogin import SPECS, cookies_for_uri, read_all_cookies

OUT = os.path.join(os.environ.get("TEMP", "."), "yixi_cookie_uri_probe.json")


def run(window) -> None:
    report: dict = {}
    try:
        time.sleep(4)
        report["current_url"] = window.get_current_url()
        report["by_uri"] = {
            uri: cookies_for_uri(window, uri, timeout=6)
            for uri in SPECS[Platform.BAIDU].cookie_uris
        }
        report["merged"] = read_all_cookies(window, SPECS[Platform.BAIDU])
        report["fallback_current"] = [c for c in (window.get_cookies() or [])]
        report["fallback_count"] = len(report["fallback_current"])
    except Exception as exc:  # noqa: BLE001
        import traceback

        report["error"] = traceback.format_exc()
    finally:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        window.destroy()


if __name__ == "__main__":
    win = webview.create_window("probe", "https://pan.baidu.com/", width=800, height=600)
    webview.start(run, win, gui="edgechromium", private_mode=True)
    data = json.load(open(OUT, encoding="utf-8"))
    print(json.dumps({k: v for k, v in data.items() if k != "fallback_current"},
                     ensure_ascii=False, indent=2)[:1200])
