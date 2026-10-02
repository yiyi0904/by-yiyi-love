"""打印迅雷 pan 动作的 captcha/init 原始响应，定位「验证码无效」。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.config import Config
from yunx.models import Platform
from yunx.net import api_request
from yunx.platforms.xunlei import (
    APP_UA,
    AUTH_BASE,
    CLIENT_ID,
    CLIENT_VERSION,
    PACKAGE_NAME,
    build_captcha_sign,
    jwt_claims,
)


def main() -> int:
    token = Config().credential(Platform.XUNLEI)
    claims = jwt_claims(token)
    user_id = str(claims.get("sub") or "")
    device = json.load(open(os.path.join(os.environ["APPDATA"], "YiXi-PC", "xunlei_device.json")))
    device_id = device["device_id"]
    print("user_id:", user_id, "device_id:", device_id)

    for action, with_user in (
        ("GET:/drive/v1/files", True),
        ("GET:/drive/v1/files", False),
        ("GET:/drive/v1/about", True),
    ):
        ts = str(int(time.time() * 1000))
        meta = {
            "client_version": CLIENT_VERSION,
            "package_name": PACKAGE_NAME,
            "timestamp": ts,
            "captcha_sign": build_captcha_sign(device_id, ts),
        }
        if with_user:
            meta["user_id"] = user_id
        body = {
            "client_id": CLIENT_ID,
            "action": action,
            "device_id": device_id,
            "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
            "meta": meta,
            "captcha_token": "",
        }
        resp = api_request(
            "POST",
            f"{AUTH_BASE}/v1/shield/captcha/init",
            headers={
                "User-Agent": APP_UA,
                "Accept": "application/json;charset=UTF-8",
                "Content-Type": "application/json",
                "X-Client-Id": CLIENT_ID,
                "X-Device-Id": device_id,
                "X-Client-Version": CLIENT_VERSION,
            },
            data=json.dumps(body),
        )
        text = (resp.text or "")[:220].replace("\n", " ")
        print(f"\n[{action} user_id={'有' if with_user else '无'}] -> {resp.status_code} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
