"""在真实迅雷网页里挂 fetch/XHR 监听，打开登录弹窗，抓出网页登录用到的接口。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview

from yunx.weblogin import _safe_signal  # noqa: F401  (复用）

OUT = os.path.join(os.environ.get("TEMP", "."), "xunlei_web_hook.json")

HOOK_JS = r"""
(function(){
  if (window.__hooked) return "already";
  window.__hooked = true;
  window.__reqs = [];
  function rec(method, url, body){
    try { window.__reqs.push({m: method, u: String(url).slice(0,300), b: body ? String(body).slice(0,200) : ""}); } catch(e){}
  }
  var of = window.fetch;
  if (of) {
    window.fetch = function(input, init){
      try {
        var url = (typeof input === "string") ? input : (input && input.url);
        rec((init && init.method) || "GET", url, init && init.body);
      } catch(e){}
      return of.apply(this, arguments);
    };
  }
  var oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, u){ rec(m, u, ""); return oo.apply(this, arguments); };
  var os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(b){ try{ if(b) window.__reqs.push({m:"BODY", u:"", b:String(b).slice(0,200)}); }catch(e){} return os.apply(this, arguments); };
  return "hooked";
})();
"""


def run(window) -> None:
    report: dict = {}
    try:
        time.sleep(6)
        report["hook"] = window.evaluate_js(HOOK_JS)
        time.sleep(10)
        report["clicked"] = window.evaluate_js(
            r"""
            (function(){
              var nodes = Array.from(document.querySelectorAll('a,button,div,span,li'));
              var hit = nodes.find(function(n){
                var t=(n.innerText||'').trim();
                return t==='扫码登录'||t==='二维码登录'||t==='微信登录';
              });
              if (hit) { hit.click(); return hit.innerText.trim(); }
              return '';
            })();
            """
        )
        time.sleep(8)
        report["url"] = window.get_current_url()
        report["title"] = window.evaluate_js("document.title")
        reqs = window.evaluate_js("JSON.stringify(window.__reqs||[])")
        report["requests"] = json.loads(reqs) if reqs else []
        text = window.evaluate_js("document.body ? document.body.innerText.slice(0,300) : ''")
        report["page_text"] = text
    except Exception as exc:  # noqa: BLE001
        import traceback

        report["error"] = traceback.format_exc()
    finally:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        window.destroy()


if __name__ == "__main__":
    win = webview.create_window(
        "hook", "https://pan.xunlei.com/login/", width=1000, height=700
    )
    webview.start(run, win, gui="edgechromium", private_mode=True)
    data = json.load(open(OUT, encoding="utf-8"))
    print("clicked:", data.get("clicked"))
    print("url:", data.get("url"))
    print("页面文字:", (data.get("page_text") or "").replace("\n", " ")[:200])
    print("\n捕获到的请求：")
    for item in data.get("requests", [])[:60]:
        print("  ", item.get("m"), item.get("u")[:150], item.get("b", "")[:80])
