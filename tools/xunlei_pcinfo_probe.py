"""探测迅雷的 /user_info/pc_info 接口（网页版用它换 access_token）。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.net import api_request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    for url in (
        "https://pan.xunlei.com/user_info/pc_info",
        "https://api-pan.xunlei.com/user_info/pc_info",
        "https://pan.xunlei.com/user_info",
    ):
        try:
            resp = api_request(
                "GET",
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://pan.xunlei.com/",
                    "Origin": "https://pan.xunlei.com",
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(url, "-> 请求异常", exc)
            continue
        print(url, "->", resp.status_code)
        print("   ", resp.text[:400].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
