"""列出迅雷网页版调用的所有接口路径。"""

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


def fetch(url: str) -> str:
    return api_request("GET", url, headers={"User-Agent": UA}).text or ""


def main() -> int:
    home = fetch("https://pan.xunlei.com/")
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', home)
    joined = ""
    for src in scripts:
        joined += fetch("https:" + src if src.startswith("//") else src) + "\n"

    paths = sorted(
        {
            p
            for p in re.findall(r"['\"`](/[\w\-/\.]*(?:v1|auth|token|user|login)[\w\-/\.]*)['\"`]", joined)
            if len(p) < 70
        }
    )
    print("接口路径候选：")
    for path in paths:
        print("  ", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
