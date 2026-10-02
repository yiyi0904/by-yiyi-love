"""找出 webpack 模块 98（迅雷网页版用它换取 access_token）。"""

from __future__ import annotations

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.net import api_request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
BASE = os.path.dirname(os.path.abspath(__file__))


def fetch(url: str) -> str:
    return api_request("GET", url, headers={"User-Agent": UA}).text or ""


def main() -> int:
    # 1) 已有文件里找
    for path in sorted(glob.glob(os.path.join(BASE, "xjs_*.js"))):
        js = open(path, encoding="utf-8").read()
        index = js.find("98:function")
        if index >= 0:
            print("在缓存文件中找到:", os.path.basename(path))
            print(js[index : index + 2600])
            return 0

    # 2) 下载所有 chunk 再找
    home = fetch("https://pan.xunlei.com/")
    runtime_url = re.findall(r'<script[^>]*src="([^"]+)"', home)[0]
    runtime = fetch("https:" + runtime_url if runtime_url.startswith("//") else runtime_url)
    chunks = sorted(set(re.findall(r'"([\w\.\-]+\.js)"', runtime)))
    print("runtime 中列出的 chunk 数:", len(chunks))
    for name in chunks:
        url = f"https://static-pan.xunlei.com/_nuxt/dist/client/{name}"
        js = fetch(url)
        index = js.find("98:function")
        if index >= 0:
            print("找到于:", url)
            print(js[max(0, index - 200) : index + 3000])
            return 0
    print("未找到模块 98")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
