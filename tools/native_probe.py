"""探测 pywebview 窗口能否直接访问 WebView2 CookieManager（按任意 URI 读 Cookie）。"""

from __future__ import annotations

import json
import os
import time

import webview

OUT = os.path.join(os.environ.get("TEMP", "."), "yunx_native_probe.json")
report: dict = {}


def run(window) -> None:
    try:
        time.sleep(3)
        native = getattr(window, "native", None)
        report["native_type"] = type(native).__name__
        report["native_attrs"] = [a for a in dir(native) if not a.startswith("_")][:40]

        core = None
        browser = getattr(native, "browser", None)
        report["browser_type"] = type(browser).__name__ if browser is not None else None
        if browser is not None:
            wv = getattr(browser, "webview", None)
            report["wv_type"] = type(wv).__name__ if wv is not None else None

        # 走 UI 线程 + ContinueWith + Semaphore（与 pywebview 内部一致的写法）
        from System import Action, Func, Type
        from System.Threading.Tasks import Task
        from threading import Semaphore

        form = native
        wv = form.browser.webview
        got = {}
        for uri in (
            "https://pan.quark.cn/",
            "https://pan.baidu.com/",
            "https://pan.xunlei.com/",
            "https://yun.139.com/",
        ):
            holder: list = []
            sem = Semaphore(0)

            def start(uri=uri, holder=holder, sem=sem):
                raw: list = []

                def parse():
                    try:
                        for c in raw:
                            holder.append(f"{c.Name}={c.Value}")
                    except Exception as exc:  # noqa: BLE001
                        holder.append(f"ERR {exc}")
                    finally:
                        sem.release()

                def callback(task):
                    try:
                        raw.extend(task.Result)
                        form.Invoke(Func[Type](parse))
                    except Exception as exc:  # noqa: BLE001
                        holder.append(f"ERR {exc}")
                        sem.release()

                wv.CoreWebView2.CookieManager.GetCookiesAsync(uri).ContinueWith(
                    Action[Task](callback)
                )

            form.Invoke(Func[Type](start))
            sem.acquire(timeout=6)
            got[uri] = holder[:8]
        report["by_uri"] = got
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
    print(open(OUT, encoding="utf-8").read())
