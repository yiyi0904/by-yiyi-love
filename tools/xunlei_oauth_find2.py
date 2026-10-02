"""定位 grantToken 的请求地址（token endpoint）。"""

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


def fetch(url: str) -> str:
    try:
        return api_request("GET", url, headers={"User-Agent": UA}, timeout=(10, 40)).text or ""
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    home = fetch("https://pan.xunlei.com/")
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', home)
    all_js: list[tuple[str, str]] = []
    for src in scripts:
        url = "https:" + src if src.startswith("//") else src
        all_js.append((os.path.basename(url), fetch(url)))
    joined = "\n".join(js for _n, js in all_js)

    print("===== grantToken 定义 =====")
    for match in re.finditer(r"grantToken\s*[:=]\s*function[^}]{0,400}", joined):
        print("  ", match.group(0)[:420].replace("\n", " "))
    for match in re.finditer(r"grantToken[^;]{0,200}", joined):
        print("  *", match.group(0)[:240].replace("\n", " "))

    print("\n===== 含 oauth / token 的 URL 字面量 =====")
    for name, js in all_js:
        for match in sorted(set(re.findall(r"['\"`](https?://[^'\"`\s]{6,110})['\"`]", js))):
            if any(k in match for k in ("oauth", "xluser", "i.xunlei", "auth", "token")):
                print(f"  [{name}] {match}")

    print("\n===== signKey / algVersion 配置 =====")
    for match in re.finditer(r"\{[^{}]{0,80}clientId[^{}]{0,300}\}", joined):
        text = match.group(0)
        if "authorizePage" in text or "signKey" in text:
            print("  ", text[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
