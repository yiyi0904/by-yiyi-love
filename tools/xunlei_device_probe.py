"""验证迅雷设备码登录（device code）接口是否可用。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.net import api_request
from yunx.platforms.xunlei import (
    APP_UA,
    AUTH_BASE,
    CLIENT_ID,
    CLIENT_SECRET,
    CLIENT_VERSION,
    build_captcha_sign,
    _load_device_id,
)


def main() -> int:
    device_id = _load_device_id()
    print("device_id:", device_id, flush=True)
    ts = str(int(time.time() * 1000))
    captcha_body = {
        "client_id": CLIENT_ID,
        "action": "POST:/v1/auth/device/code",
        "device_id": device_id,
        "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
        "meta": {
            "client_version": CLIENT_VERSION,
            "package_name": "com.xunlei.downloadprovider",
            "timestamp": ts,
            "captcha_sign": build_captcha_sign(device_id, ts),
            "user_id": "",
        },
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
        data=json.dumps(captcha_body),
    )
    cap = resp.json()
    print("captcha/init:", resp.status_code, json.dumps(cap, ensure_ascii=False)[:220], flush=True)
    captcha_token = cap.get("captcha_token", "")

    body = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "scope": ""}
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/auth/device/code",
        headers={
            "User-Agent": APP_UA,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json",
            "X-Client-Id": CLIENT_ID,
            "X-Device-Id": device_id,
            "X-Client-Version": CLIENT_VERSION,
            "X-Captcha-Token": captcha_token,
        },
        data=json.dumps(body),
    )
    print("device/code:", resp.status_code, flush=True)
    print(resp.text[:600], flush=True)

    info = resp.json()
    print("\nverification_uri_complete:", info.get("verification_uri_complete"), flush=True)
    print("short_uri_complete:", info.get("short_uri_complete"), flush=True)

    token_body = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "device_code": info["device_code"],
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/auth/device/token",
        headers={
            "User-Agent": APP_UA,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json",
            "X-Client-Id": CLIENT_ID,
            "X-Device-Id": device_id,
            "X-Client-Version": CLIENT_VERSION,
        },
        data=json.dumps(token_body),
    )
    print("\ndevice/token（未授权时应为 pending）:", resp.status_code, resp.text[:300], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
