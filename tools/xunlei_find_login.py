"""定位迅雷网页版用 cookie 换 token 的接口。"""

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
    joined = ""
    for src in scripts:
        url = "https:" + src if src.startswith("//") else src
        joined += fetch(url) + "\n"

    for pattern, label in (
        (r".{160}sessionid.{200}", "sessionid 上下文"),
        (r".{140}signin/token.{160}", "signin/token 上下文"),
        (r".{140}getCookie.{160}", "getCookie 上下文"),
        (r".{120}refresh_token.{200}", "refresh_token 上下文"),
        (r"https?://[\w\.\-]*xluser[\w\.\-]*/[^\s'\"`]{0,80}", "xluser 接口"),
    ):
        print(f"\n===== {label} =====")
        seen: set[str] = set()
        count = 0
        for match in re.finditer(pattern, joined):
            snippet = match.group(0).replace("\n", " ")
            if snippet[:60] in seen:
                continue
            seen.add(snippet[:60])
            print("  ", snippet[:380])
            count += 1
            if count >= 6:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
