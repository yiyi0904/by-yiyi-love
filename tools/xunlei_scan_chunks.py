"""扫描迅雷网页版所有 JS 分包，找同时出现 access_token / refresh_token 的代码。"""

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
        return api_request("GET", url, headers={"User-Agent": UA}, timeout=(10, 30)).text or ""
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    home = fetch("https://pan.xunlei.com/")
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', home)
    runtime_url = "https:" + scripts[0] if scripts[0].startswith("//") else scripts[0]
    runtime = fetch(runtime_url)
    names = sorted({n for n in re.findall(r'"([\w\.\-]{3,60}\.js)"', runtime)})
    names += [os.path.basename(s) for s in scripts if s.endswith(".js")]
    names = sorted(set(names))
    print("候选分包:", len(names))

    hits = 0
    for name in names:
        js = fetch(f"https://static-pan.xunlei.com/_nuxt/dist/client/{name}")
        if "refresh_token" not in js and "access_token" not in js:
            continue
        hits += 1
        print(f"\n===== {name} ({len(js)} bytes) =====")
        for keyword in ("access_token", "refresh_token"):
            for match in re.finditer(re.escape(keyword), js):
                start = max(0, match.start() - 400)
                print(f"  [{keyword}]", js[start : match.end() + 120].replace("\n", " ")[-460:])
                break
        for url in sorted(set(re.findall(r"['\"`](/[\w\-/\.]{4,60})['\"`]", js))):
            if any(k in url for k in ("auth", "token", "user", "login")):
                print("   path:", url)
    print("\n命中分包数:", hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
