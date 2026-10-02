"""用更完整的浏览器请求头抓设备码验证页，并找轮询接口。"""

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
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://pan.xunlei.com/",
}

URLS = [
    "https://xluser-ssl.xunlei.com/__/auth/device/?client_id=Xp6vsxz_7IYVw2BB",
    "https://xluser-ssl.xunlei.com/__/auth/device/",
    "https://xluser-ssl.xunlei.com/api/v1/reurl?action=scan&code=testcode",
]


def main() -> int:
    for url in URLS:
        try:
            resp = api_request("GET", url, headers=HEADERS, allow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            print(url, "-> 异常", exc)
            continue
        body = resp.text or ""
        print(f"\n=== {url}\n    HTTP {resp.status_code}, {len(body)} 字节, 最终 {resp.url}")
        if resp.status_code == 200 and len(body) > 200:
            for pattern in (
                r"<title>([^<]{0,80})</title>",
                r'(?:src|href)="([^"]+\.js[^"]*)"',
                r"/[\w\-/]*(?:token|device|poll|query)[\w\-/]*",
            ):
                hits = re.findall(pattern, body)
                if hits:
                    print("   ", pattern, "->", sorted(set(hits))[:8])
        else:
            print("    ", body[:200].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
