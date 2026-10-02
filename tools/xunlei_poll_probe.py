"""暴力探测设备码轮询接口（正确的那个会返回 authorization_pending 而不是 404）。"""

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
    _load_device_id,
    login_captcha_token,
)

CANDIDATES = [
    ("POST", "/v1/auth/device/token"),
    ("GET", "/v1/auth/device/token"),
    ("POST", "/v1/auth/device/code/query"),
    ("POST", "/v1/auth/device/query"),
    ("POST", "/v1/auth/token"),
    ("POST", "/v1/auth/device/code/token"),
    ("GET", "/v1/auth/device/code/token"),
    ("POST", "/api/v1/auth/device/token"),
    ("GET", "/api/v1/auth/device/token"),
    ("POST", "/v1/auth/device/result"),
    ("GET", "/v1/auth/device/result"),
    ("POST", "/v1/auth/signin/device/token"),
    ("POST", "/v1/auth/signin/token"),
]


def request_device_code(device_id: str) -> dict:
    captcha = login_captcha_token(device_id, "")
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
            "X-Captcha-Token": captcha,
        },
        data=json.dumps(body),
    )
    return resp.json() or {}


def main() -> int:
    device_id = _load_device_id()
    info = request_device_code(device_id)
    device_code = info.get("device_code", "")
    print("device_code:", device_code[:16], "…  verification:", info.get("short_uri_complete"))

    headers = {
        "User-Agent": APP_UA,
        "Accept": "application/json;charset=UTF-8",
        "Content-Type": "application/json",
        "X-Client-Id": CLIENT_ID,
        "X-Device-Id": device_id,
        "X-Client-Version": CLIENT_VERSION,
    }
    body = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    for method, path in CANDIDATES:
        url = f"{AUTH_BASE}{path}"
        try:
            if method == "GET":
                resp = api_request(
                    "GET", url, headers=headers, params={"client_id": CLIENT_ID, "device_code": device_code}
                )
            else:
                resp = api_request("POST", url, headers=headers, data=json.dumps(body))
            text = resp.text[:150].replace("\n", " ")
        except Exception as exc:  # noqa: BLE001
            text = f"异常 {exc}"
            resp = None
        status = resp.status_code if resp is not None else "-"
        mark = "  <== 候选" if resp is not None and resp.status_code != 404 else ""
        print(f"{method:4} {path:34} -> {status} {text}{mark}")
        time.sleep(0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
