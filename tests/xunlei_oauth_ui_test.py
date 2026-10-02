"""验证迅雷「网页登录」：打开官方授权页，页面上有真实登录入口。"""

from __future__ import annotations

import os
import queue
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.models import Platform
from yunx.weblogin import get_login_service

PROBE = r"""
(function(){
  function count(sel){ try { return document.querySelectorAll(sel).length; } catch(e){ return -1; } }
  var iframes = [];
  try { iframes = Array.from(document.querySelectorAll('iframe')).map(function(f){ return (f.src||'').slice(0,120); }); } catch(e){}
  return JSON.stringify({
    url: location.href.slice(0,160),
    title: document.title,
    inputs: count('input'),
    iframes: iframes,
    text: (document.body ? document.body.innerText.slice(0,200) : '')
  });
})();
"""


def main() -> int:
    service = get_login_service()
    result = service.open(Platform.XUNLEI)
    deadline = time.time() + 60
    while time.time() < deadline and not service.is_running():
        time.sleep(0.3)
    assert service.is_running(), "登录会话没建立"
    session = service._active  # noqa: SLF001

    time.sleep(14)
    window = session.window
    import json

    info = json.loads(window.evaluate_js(PROBE) or "{}")
    print("URL:", info.get("url"))
    print("标题:", info.get("title"))
    print("input 数量:", info.get("inputs"))
    print("iframe:", info.get("iframes"))
    print("页面文字:", (info.get("text") or "").replace("\n", " ")[:160])

    assert "i.xunlei.com" in (info.get("url") or ""), info
    has_login = (info.get("inputs") or 0) > 0 or info.get("iframes")
    assert has_login, "页面上没有登录入口"

    service.close_active()
    try:
        payload = result.get(timeout=30)
    except queue.Empty:
        print("FAILED: 没收到结果")
        return 1
    print("结果:", payload.get("ok"), "/", payload.get("error"))
    service.shutdown()
    print("XUNLEI WEB LOGIN(OAUTH) TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
