"""继续定位迅雷网盘 token 的存储键名。"""

from __future__ import annotations

import glob
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

PATTERNS = {
    "getFetchCredentials 定义": r"getFetchCredentials[^}]{0,400}",
    "cookie 读取": r"document\.cookie.{0,160}",
    "xlpan 常量表": r"xlpan[\w\-]*['\"]?\s*[:=][^,;}]{0,60}",
    "Authorization 上下文": r".{140}Authorization.{200}",
    "cookie 读取": r"document\.cookie.{0,160}",
    "xlpan*": r"xlpan[\w\-]{0,30}",
    "token 字面量": r"['\"]([\w\-]{3,40}[tT]oken[\w\-]{0,20})['\"]",
    "access_token 定义": r"access_token\s*[:=]\s*[^,;)}]{0,60}",
    "getItem 变量键": r"getItem\(([A-Za-z_$][\w$]*\.[\w$]+)\)",
    "键常量定义": r"([A-Za-z_$][\w$]*\.[A-Za-z_$]{1,3})\s*=\s*['\"]([\w\-]{2,40})['\"]",
}


def main() -> int:
    for path in sorted(glob.glob(os.path.join(BASE, "xjs_*.js"))):
        js = open(path, encoding="utf-8").read()
        name = os.path.basename(path)
        for label, pattern in PATTERNS.items():
            hits = re.findall(pattern, js)
            if not hits:
                continue
            flat = sorted({h if isinstance(h, str) else "|".join(h) for h in hits})
            if len(flat) > 40:
                flat = flat[:40]
            print(f"=== {name} :: {label}")
            for item in flat:
                print("   ", item[:140])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
