"""抓取迅雷网盘网页，找出登录态 / token 的存放方式。"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.net import api_request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    resp = api_request("GET", "https://pan.xunlei.com/", headers={"User-Agent": UA})
    print("home:", resp.status_code, len(resp.text))
    with open(os.path.join(OUT, "xunlei_home.html"), "w", encoding="utf-8") as fh:
        fh.write(resp.text)

    scripts = re.findall(r'<script[^>]*src="([^"]+)"', resp.text)
    for src in scripts:
        print("  script:", src)

    keys: set[str] = set()
    for src in scripts[:6]:
        if src.startswith("http"):
            url = src
        elif src.startswith("//"):
            url = "https:" + src
        else:
            url = "https://pan.xunlei.com" + src
        try:
            js = api_request("GET", url, headers={"User-Agent": UA}).text
        except Exception as exc:  # noqa: BLE001
            print("  fetch fail", url, exc)
            continue
        print(f"  {url} -> {len(js)} bytes")
        for pattern in (
            r"localStorage\.(?:setItem|getItem)\(['\"]([^'\"]{2,60})['\"]",
            r"sessionStorage\.(?:setItem|getItem)\(['\"]([^'\"]{2,60})['\"]",
            r"document\.cookie\s*=\s*['\"]([^='\"]{2,60})=",
        ):
            for key in re.findall(pattern, js):
                keys.add(key)
        for token in ("access_token", "refresh_token", "Authorization", "Bearer"):
            if token in js:
                keys.add(f"<contains {token}>")
    print("\n发现的键：")
    for key in sorted(keys):
        print("  ", key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
