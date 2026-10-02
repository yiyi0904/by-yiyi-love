"""定位迅雷网页版获取 access_token 的那个函数（看它调了哪些接口）。"""

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
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', home)
    target = ""
    for src in scripts:
        url = "https:" + src if src.startswith("//") else src
        js = fetch(url)
        if "setCurUser" in js and "access_token" in js:
            print("命中脚本:", url)
            target = js
            break
    if not target:
        print("没找到")
        return 1

    index = target.find("accessToken:n.access_token")
    if index < 0:
        index = target.find("setCurUser")

    # 往前找该 webpack 模块的头部，看 h 是哪个模块
    head = target.rfind("function(e,t,r){", 0, index)
    if head < 0:
        head = max(0, index - 1500)
    print("===== 模块头部（含 require 映射）=====")
    print(target[head : head + 1200])

    print("\n===== 该模块内的 http 调用 =====")
    for match in re.finditer(
        r"[A-Za-z_$][\w$]*\.(get|post|put|delete)\(([^)]{0,140})", target[head:index]
    ):
        print("  ", match.group(0)[:200].replace("\n", " "))

    # h 的模块号
    imports = dict(re.findall(r"([A-Za-z_$][\w$]*)\s*=\s*r\((\d+)\)", target[head:index]))
    print("\n===== require 映射 =====")
    print(imports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
