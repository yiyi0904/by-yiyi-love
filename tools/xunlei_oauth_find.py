"""在迅雷网页 JS 里找 OAuth 换 token 的接口和 PKCE 处理。"""

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
    try:
        return api_request("GET", url, headers={"User-Agent": UA}, timeout=(10, 40)).text or ""
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    home = fetch("https://pan.xunlei.com/")
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', home)
    joined = ""
    for src in scripts:
        joined += fetch("https:" + src if src.startswith("//") else src) + "\n"

    for pattern, label in (
        (r".{200}code_verifier.{260}", "code_verifier"),
        (r".{200}code_challenge.{260}", "code_challenge"),
        (r".{160}oauth.{240}", "oauth"),
        (r".{140}grant_type.{240}", "grant_type"),
        (r".{120}sign_in_in_iframe.{200}", "sso_sign_in_in_iframe"),
        (r"https?://[\w\.\-]*(?:xunlei|i\.xunlei)[\w\.\-]*/[\w\-/\.]{0,60}", "迅雷 URL"),
    ):
        print(f"\n===== {label} =====")
        seen: set[str] = set()
        count = 0
        for match in re.finditer(pattern, joined):
            snippet = match.group(0).replace("\n", " ")
            if snippet[:50] in seen:
                continue
            seen.add(snippet[:50])
            print("  ", snippet[:420])
            count += 1
            if count >= 5:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
