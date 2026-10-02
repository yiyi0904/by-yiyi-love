"""用迅雷 PC 客户端（thunderx）凭据试设备码，看授权页是否存在。"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.net import api_request
from yunx.platforms.xunlei import AUTH_BASE, _load_device_id, build_captcha_sign

PC_CLIENT_ID = "ZQL_zwA4qhHcoe_2"
PC_CLIENT_SECRET = "Og9Vr1L8Ee6bh0olFxFDRg"
PC_CLIENT_VERSION = "1.06.0.2132"
PC_PACKAGE = "com.thunder.downloader"
PC_UA = (
    "ANDROID-com.thunder.downloader/1.06.0.2132 netWorkType/5G appid/40 "
    "deviceName/Xiaomi_M2004j7ac deviceModel/M2004J7AC OSVersion/12 protocolVersion/301 "
    "platformVersion/10 sdkVersion/512000 Oauth2Client/0.9 (Linux 4_14_186) (JAVA 0)"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    device_id = _load_device_id()
    ts = str(int(time.time() * 1000))
    sign = "1."
    value = PC_CLIENT_ID + PC_CLIENT_VERSION + PC_PACKAGE + device_id + ts
    import hashlib

    for salt in __import__("yunx.platforms.xunlei", fromlist=["CAPTCHA_SALTS"]).CAPTCHA_SALTS:
        value = hashlib.md5((value + salt).encode()).hexdigest()
    sign = "1." + value

    captcha_body = {
        "client_id": PC_CLIENT_ID,
        "action": "POST:/v1/auth/device/code",
        "device_id": device_id,
        "redirect_uri": "xlaccsdk01://xunlei.com/callback?state=harbor",
        "meta": {
            "client_version": PC_CLIENT_VERSION,
            "package_name": PC_PACKAGE,
            "timestamp": ts,
            "captcha_sign": sign,
            "user_id": "",
        },
    }
    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/shield/captcha/init",
        headers={
            "User-Agent": PC_UA,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json",
            "X-Client-Id": PC_CLIENT_ID,
            "X-Device-Id": device_id,
            "X-Client-Version": PC_CLIENT_VERSION,
        },
        data=json.dumps(captcha_body),
    )
    captcha = (resp.json() or {}).get("captcha_token", "")
    print("captcha:", resp.status_code, "token:", (captcha[:20] + "…") if captcha else "(空)")

    resp = api_request(
        "POST",
        f"{AUTH_BASE}/v1/auth/device/code",
        headers={
            "User-Agent": PC_UA,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json",
            "X-Client-Id": PC_CLIENT_ID,
            "X-Device-Id": device_id,
            "X-Client-Version": PC_CLIENT_VERSION,
            "X-Captcha-Token": captcha,
        },
        data=json.dumps(
            {"client_id": PC_CLIENT_ID, "client_secret": PC_CLIENT_SECRET, "scope": ""}
        ),
    )
    print("device/code:", resp.status_code)
    print(resp.text[:500])
    info = resp.json() if resp.status_code == 200 else {}
    for key in ("verification_uri_complete", "verification_url", "short_uri_complete"):
        url = info.get(key)
        if not url:
            continue
        r = api_request("GET", url, headers={"User-Agent": UA}, allow_redirects=False)
        print(f"\n{key} -> HTTP {r.status_code} Location={r.headers.get('Location','')[:120]}")
        if r.status_code == 200:
            print("   body:", (r.text or "")[:260].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
