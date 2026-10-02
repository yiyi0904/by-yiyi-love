"""在迅雷网盘的 JS 里定位 token 的存取位置。"""

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
SCRIPTS = [
    "//static-pan.xunlei.com/_nuxt/dist/client/2c540d0.js",
    "//static-pan.xunlei.com/_nuxt/dist/client/pages/index.40020855287e52a9e6d1.js",
    "//static-pan.xunlei.com/_nuxt/dist/client/utils-async.5a2e575a1e7f4a298060.js",
    "//static-pan.xunlei.com/_nuxt/dist/client/102.1521905302829436a3a5.js",
    "//static-pan.xunlei.com/_nuxt/dist/client/4.d2aae00adb61e83e4302.js",
    "//static-pan.xunlei.com/_nuxt/dist/client/utils-initial.f800c7326181a3f081fe.js",
]


def fetch(url: str) -> str:
    return api_request("GET", "https:" + url, headers={"User-Agent": UA}).text


def main() -> int:
    for url in SCRIPTS:
        js = fetch(url)
        name = os.path.basename(url)
        with open(os.path.join(BASE, "xjs_" + name), "w", encoding="utf-8") as fh:
            fh.write(js)
        for keyword in ("access_token", "refresh_token", "captcha_token"):
            for match in re.finditer(re.escape(keyword), js):
                start = max(0, match.start() - 220)
                snippet = js[start : match.end() + 160].replace("\n", " ")
                print(f"--- {name} :: {keyword} ---")
                print("   ", snippet[:380])
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
