"""用本机已保存的迅雷凭证验证登录态与 pan 接口是否可用。"""

from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.config import Config
from yunx.models import Platform
from yunx.platforms.xunlei import XunleiClient, jwt_claims


def main() -> int:
    config = Config()
    token = config.credential(Platform.XUNLEI)
    refresh = config.get("xunlei_refresh_token", "")
    print("token 长度:", len(token), " refresh 长度:", len(refresh))
    if not token:
        print("没有迅雷凭证")
        return 1
    claims = jwt_claims(token)
    print("JWT sub:", claims.get("sub"), " exp 剩余秒:", int(claims.get("exp", 0) - __import__("time").time()))

    client = XunleiClient()
    client.refresh_token = refresh
    print("\n== 1) 校验凭证 ==")
    try:
        print("昵称:", client.check_credential(token))
    except Exception as exc:  # noqa: BLE001
        print("校验失败:", type(exc).__name__, exc)
        traceback.print_exc()
        return 1

    print("\n== 2) 列个人网盘根目录 ==")
    try:
        files = client._list_cloud("")  # noqa: SLF001
        for item in files[:10]:
            print(f"  {'DIR ' if item.is_dir else 'FILE'} {item.name} {item.size}")
        print("  共", len(files), "项")
    except Exception as exc:  # noqa: BLE001
        print("列目录失败:", type(exc).__name__, exc)
        traceback.print_exc()
        return 1
    print("\n迅雷凭证可用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
