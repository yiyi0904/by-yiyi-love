"""打印用网页客户端 ID 申请验证码的原始响应。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    token = Config().credential(Platform.XUNLEI)
    claims = jwt_claims(token)
    user_id = str(claims.get("sub") or "")
    web_client = str(claims.get("aud") or "")
    device = json.load(open(os.path.join(os.environ["APPDATA"], "YiXi-PC", "xunlei_device.json")))
    device_id = device["device_id"]

    combos = [
        (web_client, CLIENT_VERSION, PACKAGE_NAME, APP_UA),
        (web_client, "1.93.6", "pan.xunlei.com", WEB_UA),
        (web_client, "8.31.0.9726", PACKAGE_NAME, WEB_UA),
        (CLIENT_ID, CLIENT_VERSION, PACKAGE_NAME, APP_UA),
    ]
    for client_id, version, package, ua in combos:
        ts = str(int(time.time() * 1000))
        body = {
            "client_id": client_id,
            "action": "GET:/drive/v1/files",
            "device_id": device_id,
            "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
            "meta": {
                "client_version": version,
                "package_name": package,
                "timestamp": ts,
                "captcha_sign": build_captcha_sign(device_id, ts),
                "user_id": user_id,
            },
            "captcha_token": "",
        }
        resp = api_request(
            "POST",
            f"{AUTH_BASE}/v1/shield/captcha/init",
            headers={
                "User-Agent": ua,
                "Accept": "application/json;charset=UTF-8",
                "Content-Type": "application/json",
                "X-Client-Id": client_id,
                "X-Device-Id": device_id,
                "X-Client-Version": version,
            },
            data=json.dumps(body),
        )
        text = (resp.text or "")[:230].replace("\n", " ")
        print(f"\nclient_id={client_id} version={version} package={package} ua={'app' if ua==APP_UA else 'web'}")
        print(f"  -> {resp.status_code} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
