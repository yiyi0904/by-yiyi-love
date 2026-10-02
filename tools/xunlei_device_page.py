"""抓取迅雷设备码验证页面，找出轮询 token 的真实接口。"""

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
BASE = os.path.dirname(os.path.abspath(__file__))
URL = (
    "https://xluser-ssl.xunlei.com/__/auth/device/?client_id=Xp6vsxz_7IYVw2BB"
    "&scope=offline%20user%20verified%20pan%20sync%20profile%20sso%20auth"
)


def main() -> int:
    resp = api_request("GET", URL, headers={"User-Agent": UA})
    print("page:", resp.status_code, len(resp.text))
    with open(os.path.join(BASE, "xunlei_device_page.html"), "w", encoding="utf-8") as fh:
        fh.write(resp.text)
    for match in re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', resp.text):
        print("  script:", match)
    for match in re.findall(r'(/[\w\-/]+(?:token|device)[\w\-/]*)', resp.text):
        print("  path:", match)
    for match in re.findall(r'https?://[\w\.\-]+/[\w\-/]*(?:token|device)[\w\-/]*', resp.text):
        print("  url:", match)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
