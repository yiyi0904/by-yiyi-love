"""下载迅雷网盘网页版全部 JS，定位 access_token 的来源（localStorage / cookie / 接口）。"""

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
HOME = "https://pan.xunlei.com/"


def fetch(url: str) -> str:
    return api_request("GET", url, headers={"User-Agent": UA}).text or ""


def main() -> int:
    home = fetch(HOME)
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', home)
    sources: list[tuple[str, str]] = []
    for src in scripts:
        url = "https:" + src if src.startswith("//") else src
        text = fetch(url)
        name = os.path.basename(url.split("?")[0])
        sources.append((name, text))

    seen: set[str] = set()
    for name, js in sources:
        for match in re.finditer(r"access_token", js):
            start = max(0, match.start() - 320)
            snippet = js[start : match.end() + 200].replace("\n", " ")
            key = snippet[:80]
            if key in seen:
                continue
            seen.add(key)
            print(f"--- {name} ---")
            print("   ", snippet[:460])

    print("\n==== 关键字扫描 ====")
    joined = "\n".join(js for _n, js in sources)
    for pattern, label in (
        (r"setItem\(['\"]([^'\"]+)['\"]", "localStorage.setItem 字面量"),
        (r"token['\"]?\s*[:=]\s*['\"]([^'\"]{6,80})['\"]", "token 字面量赋值"),
        (r"[\w\-]*token[\w\-]*", "含 token 的标识符"),
    ):
        hits = sorted({h for h in re.findall(pattern, joined) if h})
        print(f"-- {label}: {len(hits)}")
        for hit in hits[:40]:
            print("   ", hit[:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
