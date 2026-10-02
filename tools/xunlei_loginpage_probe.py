"""检查迅雷官方登录页在 WebView2 里到底渲染出了什么（有没有登录入口）。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview

OUT = os.path.join(os.environ.get("TEMP", "."), "xunlei_loginpage.json")

PROBE_JS = r"""
(function(){
  function count(sel){ try { return document.querySelectorAll(sel).length; } catch(e){ return -1; } }
  var frames = [];
  try {
    frames = Array.from(document.querySelectorAll('iframe')).map(function(f){
      return {src: f.src, w: f.clientWidth, h: f.clientHeight};
    });
  } catch(e){}
  var imgs = [];
  try {
    imgs = Array.from(document.querySelectorAll('img')).slice(0,8).map(function(i){
      return {src: (i.src||'').slice(0,90), w: i.naturalWidth, h: i.naturalHeight};
    });
  } catch(e){}
  var btns = [];
  try {
    btns = Array.from(document.querySelectorAll('button,a,div[class*=login],div[class*=Login]'))
      .slice(0,25).map(function(b){ return (b.innerText||'').trim().slice(0,20); }).filter(Boolean);
  } catch(e){}
  return JSON.stringify({
    url: location.href,
    title: document.title,
    htmlLen: (document.documentElement.outerHTML||'').length,
    textLen: (document.body ? document.body.innerText.length : 0),
    textHead: (document.body ? document.body.innerText.slice(0,300) : ''),
    iframes: frames,
    inputs: count('input'),
    canvases: count('canvas'),
    images: imgs,
    buttons: btns
  });
})();
"""


def run(window) -> None:
    report: dict = {}
    try:
        time.sleep(12)
        raw = window.evaluate_js(PROBE_JS)
        report = json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        import traceback

        report["error"] = traceback.format_exc()
    finally:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        window.destroy()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://pan.xunlei.com/login/"
    win = webview.create_window("probe", target, width=1000, height=720)
    webview.start(run, win, gui="edgechromium", private_mode=True)
    print(json.dumps(json.load(open(OUT, encoding="utf-8")), ensure_ascii=False, indent=2)[:2000])
