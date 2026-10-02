"""验证迅雷短信登录接口的请求格式（用无效手机号，不会真的发短信）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.platforms.xunlei import (
    _load_device_id,
    exchange_access_token,
    login_captcha_token,
    send_sms_code,
    sms_login,
)


def main() -> int:
    device_id = _load_device_id()
    print("device_id:", device_id)
    captcha = login_captcha_token(device_id, "10000000000")
    print("captcha_token:", (captcha[:24] + "...") if captcha else "(空)")

    result = send_sms_code("1", device_id)
    print("sendsms(无效号码):", result)

    result = sms_login("1", "0000", "", "", device_id)
    print("smslogin(无效):", result)

    result = exchange_access_token("invalid-session", device_id, captcha)
    print("exchange(无效 session):", {k: v for k, v in result.items() if k != "access_token"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
