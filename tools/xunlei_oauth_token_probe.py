"""测试迅雷 web OAuth 的 authorization_code 换 token 接口。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.net import api_request

WEB_CLIENT_ID = "Xqp0kJBXWhwaTpB6"
WEB_CLIENT_SECRET = "Xqp0kC5LIQcyGSdKPYSzshgLKHxo"
REDIRECT_URI = "https://pan.xunlei.com/login/?sso_sign_in_in_iframe="
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CANDIDATES = [
    ("POST", "https://xluser-ssl.xunlei.com/v1/auth/token"),
    ("POST", "https://xluser-ssl.xunlei.com/v1/auth/grant/token"),
    ("POST", "https://xluser-ssl.xunlei.com/v1/auth/oauth/token"),
    ("POST", "https://i.xunlei.com/center/account/personal/oauth/token"),
    ("POST", "https://i.xunlei.com/center/account/personal/oauth/api/token"),
]


def main() -> int:
    base = {
        "grant_type": "authorization_code",
        "code": "bogus-code-for-probe",
        "client_id": WEB_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": "probe-verifier-1234567890",
    }
    variants = {
        "网页客户端 + 假 code": dict(base),
        "安卓客户端 + 假 code": dict(base, client_id="Xp6vsxz_7IYVw2BB"),
        "安卓客户端 + 安卓 deep link 回调": dict(
            base,
            client_id="Xp6vsxz_7IYVw2BB",
            redirect_uri="xlaccsdk01://xunlei.com/callback?state=harbor",
        ),
    }
    for label, body in variants.items():
        url = "https://xluser-ssl.xunlei.com/v1/auth/token"
        try:
            resp = api_request(
                "POST",
                url,
                headers={
                    "User-Agent": UA,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://pan.xunlei.com",
                    "Referer": "https://pan.xunlei.com/",
                },
                data=json.dumps(body),
            )
            text = (resp.text or "")[:180].replace("\n", " ")
            print(f"[{label}] -> {resp.status_code} {text}\n")
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] -> 异常 {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
