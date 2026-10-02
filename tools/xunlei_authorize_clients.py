"""分别用「网页客户端 ID」和「安卓客户端 ID」打开授权页，看哪个能正常登录。"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview

OUT = os.path.join(os.environ.get("TEMP", "."), "xunlei_authorize_clients.json")
AUTHORIZE = "https://i.xunlei.com/center/account/personal/oauth/"
REDIRECT = "https://pan.xunlei.com/login/?sso_sign_in_in_iframe="
PROBE = r"""
(function(){
  function count(sel){ try { return document.querySelectorAll(sel).length; } catch(e){ return -1; } }
  return JSON.stringify({
    url: location.href.slice(0,200),
    title: document.title,
    inputs: count('input'),
    text: (document.body ? document.body.innerText.slice(0,220) : '')
  });
})();
"""


def url_for(client_id: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "scope": "profile offline pan sso user",
            "state": "state-probe",
            "response_type": "code",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE}?{query}"


def main() -> int:
    targets = {
        "web": "Xqp0kJBXWhwaTpB6",
        "app": "Xp6vsxz_7IYVw2BB",
    }
    report: dict = {}
    windows = []
    for name, client in targets.items():
        windows.append(
            (name, webview.create_window(f"probe-{name}", url_for(client), width=900, height=700))
        )

    def run() -> None:
        time.sleep(14)
        for name, window in windows:
            try:
                report[name] = json.loads(window.evaluate_js(PROBE) or "{}")
            except Exception as exc:  # noqa: BLE001
                report[name] = {"error": str(exc)}
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

    webview.start(run, gui="edgechromium", private_mode=True)
    data = json.load(open(OUT, encoding="utf-8"))
    for name, info in data.items():
        print(f"\n=== {name} client ({targets[name]}) ===")
        print("  标题:", info.get("title"))
        print("  输入框:", info.get("inputs"))
        print("  地址:", (info.get("url") or "")[:150])
        print("  内容:", (info.get("text") or "").replace("\n", " ")[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
