"""最小复现：captcha/init 后立刻调用 pan 接口，打印原始响应并试几种组合。"""

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
    PAN_BASE,
    build_captcha_sign,
    jwt_claims,
)

WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def captcha(
    device_id: str,
    action: str,
    user_id: str,
    old: str = "",
    client_id: str = CLIENT_ID,
    client_version: str = CLIENT_VERSION,
    package: str = PACKAGE_NAME,
) -> str:
    ts = str(int(time.time() * 1000))
    body = {
        "client_id": client_id,
        "action": action,
        "device_id": device_id,
        "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
        "meta": {
            "client_version": client_version,
            "package_name": package,
            "timestamp": ts,
            "captcha_sign": build_captcha_sign(device_id, ts),
            "user_id": user_id,
        },
        "captcha_token": old,
    }
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/shield/captcha/init",
        headers={
            "User-Agent": APP_UA,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json",
            "X-Client-Id": client_id,
            "X-Device-Id": device_id,
            "X-Client-Version": CLIENT_VERSION,
        },
        data=json.dumps(body),
    )
    return (resp.json() or {}).get("captcha_token", "")


def main() -> int:
    token = Config().credential(Platform.XUNLEI)
    claims = jwt_claims(token)
    user_id = str(claims.get("sub") or "")
    web_client = str(claims.get("aud") or "")
    print("aud(client_id):", web_client)
    device = json.load(open(os.path.join(os.environ["APPDATA"], "YiXi-PC", "xunlei_device.json")))
    device_id = device["device_id"]

    url = f"{PAN_BASE}/drive/v1/files?parent_id=&limit=100&with_audit=true"
    headers_base = {
        "User-Agent": WEB_UA,
        "Authorization": f"Bearer {token}",
        "X-Device-Id": device_id,
        "X-Client-Version": CLIENT_VERSION,
        "Content-Type": "application/json",
        "Origin": "https://pan.xunlei.com",
        "Referer": "https://pan.xunlei.com/",
    }

    print("== A) captcha 用 token 里的 client_id（aud）==")
    cap = captcha(device_id, "GET:/drive/v1/files", user_id, client_id=web_client)
    resp = api_request("GET", url, headers={**headers_base, "X-Captcha-Token": cap})
    try:
        payload = resp.json()
        for item in payload.get("error_details", []) or []:
            print("   detail:", item.get("detail"))
        print("   error:", payload.get("error"), payload.get("error_description"))
    except Exception:  # noqa: BLE001
        print(resp.status_code, (resp.text or "")[:300])

    print("\n== B) aud + 网页版 client_version/package ==")
    for version, package in (("1.93.6", "pan.xunlei.com"), ("2.0.0", "pan.xunlei.com")):
        cap2 = captcha(
            device_id, "GET:/drive/v1/files", user_id,
            client_id=web_client, client_version=version, package=package,
        )
        resp = api_request("GET", url, headers={**headers_base, "X-Captcha-Token": cap2})
        print(f"  [{version}/{package}] {resp.status_code} {(resp.text or '')[:160]}".replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
