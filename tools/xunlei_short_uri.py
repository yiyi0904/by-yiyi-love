"""看设备码返回的 short_uri_complete 到底跳到哪里（是否是真正的扫码页）。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.net import api_request
from yunx.platforms.xunlei import request_device_code

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    info = request_device_code()
    print(json.dumps({k: v for k, v in info.items() if k != "device_code"}, ensure_ascii=False))
    for key in ("short_uri_complete", "verification_uri_complete", "verification_url"):
        url = info.get(key)
        if not url:
            continue
        try:
            resp = api_request(
                "GET", url, headers={"User-Agent": UA}, allow_redirects=False
            )
            location = resp.headers.get("Location", "")
            print(f"\n{key}: {url}\n   -> HTTP {resp.status_code} Location={location}")
            if resp.status_code == 200:
                print("   body:", (resp.text or "")[:200].replace("\n", " "))
            if location:
                follow = api_request(
                    "GET", location, headers={"User-Agent": UA}, allow_redirects=True
                )
                print(f"   跟随后: HTTP {follow.status_code} 最终 {follow.url}")
                print("   body:", (follow.text or "")[:300].replace("\n", " "))
        except Exception as exc:  # noqa: BLE001
            print(f"{key} -> 异常 {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
