"""在 app.js / commons 里找 webpack 模块 98 的定义。"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.net import api_request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
BASE = os.path.dirname(os.path.abspath(__file__))


def fetch(url: str) -> str:
    return api_request("GET", url, headers={"User-Agent": UA}).text or ""


def main() -> int:
    home = fetch("https://pan.xunlei.com/")
    scripts = [s for s in re.findall(r'<script[^>]*src="([^"]+)"', home)]
    for src in scripts:
        url = "https:" + src if src.startswith("//") else src
        name = os.path.basename(url)
        js = fetch(url)
        with open(os.path.join(BASE, "xjs2_" + name), "w", encoding="utf-8") as fh:
            fh.write(js)
        for pattern in ("98:function", '"98":function', "98:(e,t"):
            index = js.find(pattern)
            if index >= 0:
                print("=== 命中", name, pattern)
                print(js[max(0, index - 300) : index + 2400])
                return 0
    print("app.js 系里没找到模块 98，看看 runtime 的 chunk 映射：")
    runtime_name = os.path.basename(scripts[0])
    runtime = open(os.path.join(BASE, "xjs2_" + runtime_name), encoding="utf-8").read()
    print(runtime[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
