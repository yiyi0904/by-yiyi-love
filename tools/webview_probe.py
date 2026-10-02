"""验证 pywebview 能否在真实站点上读写 Cookie / localStorage。"""

from __future__ import annotations

import json
import os
import sys
import traceback

import webview

OUT = os.path.join(os.environ.get("TEMP", "."), "yunx_webview_probe.json")
report: dict = {}


def run(window) -> None:
    try:
        import time

        for _ in range(60):
            url = window.get_current_url() or ""
            if "baidu.com" in url:
                break
            time.sleep(0.5)
        report["url"] = window.get_current_url()
        time.sleep(1.5)

        # 1) JS 能执行吗
        report["eval_title"] = window.evaluate_js("document.title")

        # 2) 写入一个非 HttpOnly cookie，看能否稳定读回
        window.evaluate_js("document.cookie='yxtest=hello123;path=/'")
        counts = []
        pairs: list[tuple[str, str]] = []
        for _ in range(8):
            time.sleep(1.0)
            raw = window.get_cookies() or []
            got: list[tuple[str, str]] = []
            for sc in raw:
                try:
                    for k, m in sc.items():
                        got.append((k, m.value))
                except Exception:  # noqa: BLE001
                    pass
            counts.append(len(got))
            if got:
                pairs = got
        report["cookie_counts"] = counts
        report["cookie_count"] = len(pairs)
        report["sample"] = pairs[:12]
        report["yxtest"] = [v for k, v in pairs if k == "yxtest"]

        # 3) localStorage 读写
        window.evaluate_js("localStorage.setItem('yxtoken','tok-abc')")
        time.sleep(0.3)
        report["localstorage"] = window.evaluate_js("localStorage.getItem('yxtoken')")
    except Exception:  # noqa: BLE001
        report["error"] = traceback.format_exc()
    finally:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        window.destroy()


if __name__ == "__main__":
    win = webview.create_window("probe", "https://pan.baidu.com/", width=900, height=640)
    webview.start(run, win, gui="edgechromium", private_mode=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
