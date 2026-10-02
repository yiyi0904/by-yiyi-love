"""联网连通性检查：用无效凭证请求各平台接口，验证请求构造与错误处理。"""

from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.platforms.baidu import BaiduClient
from yunx.platforms.c139 import C139Client
from yunx.platforms.pan123 import Pan123Client
from yunx.platforms.quark import QuarkClient
from yunx.platforms.uc import UCClient


def probe(name: str, func) -> None:
    try:
        result = func()
        print(f"[{name}] 未报错，返回：{result}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] {type(exc).__name__}: {exc}")


def main() -> int:
    probe("quark", lambda: QuarkClient().check_credential("__pus=abc; __puus=def"))
    probe("uc", lambda: UCClient().check_credential("__pus=abc; __puus=def"))
    probe("baidu", lambda: BaiduClient().check_credential("BDUSS=invalid"))
    probe("pan123", lambda: Pan123Client().check_credential("eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.x"))
    probe("c139", lambda: C139Client().check_credential("Login_UserNumber=13800000000"))
    # 无效分享链接也验证一次（应给出业务错误而不是崩溃）
    probe(
        "baidu-list",
        lambda: BaiduClient().open_session("https://pan.baidu.com/s/1aaaaaaaa", None, "BDUSS=x"),
    )
    probe(
        "pan123-list",
        lambda: Pan123Client().open_session("https://www.123pan.com/s/aaaa-bbbb", "", ""),
    )
    probe(
        "c139-general",
        lambda: C139Client().open_session(
            "https://yun.139.com/shareweb/#/w/i/xxxxxxxx", None, "Login_UserNumber=13800000000"
        ),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(1)
