"""内置网页登录的自动化测试：提取逻辑（桩）+ 真实窗口打开与结果落盘。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.models import Platform
from yunx.weblogin import (
    SPECS,
    extract_candidates,
    parse_weblogin_args,
    read_result,
)

BASE = os.path.dirname(os.path.abspath(__file__))


class FakeMorsel:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeCookie:
    def __init__(self, pairs: dict[str, str]) -> None:
        self._pairs = pairs

    def items(self):
        return [(k, FakeMorsel(v)) for k, v in self._pairs.items()]


class FakeWindow:
    def __init__(self, cookies: dict[str, str], store: dict[str, str] | None = None) -> None:
        self._cookies = cookies
        self._store = store or {}

    def get_cookies(self):
        return [FakeCookie({k: v}) for k, v in self._cookies.items()]

    def evaluate_js(self, script: str):
        return json.dumps(self._store)


def test_cookie_extraction() -> None:
    window = FakeWindow(
        {
            "__pus": "p1",
            "__puus": "p2",
            "b-user-id": "u1",
        }
    )
    candidates = extract_candidates(window, SPECS[Platform.QUARK])
    assert len(candidates) == 1, candidates
    header = candidates[0][0]
    assert "__pus=p1" in header and "__puus=p2" in header, header
    print("quark cookie extraction ok")

    c139 = FakeWindow(
        {
            "authorization": "Basic abc",
            "Login_UserNumber": "13800000000",
            "ORCHES-I-ACCOUNT-ENCRYPT": "MTM4MDAwMDAwMDA=",
            "irrelevant_cookie": "x",
        }
    )
    candidates = extract_candidates(c139, SPECS[Platform.C139])
    header = candidates[0][0]
    assert "authorization=Basic abc" in header, header
    assert "irrelevant_cookie" not in header, header
    print("c139 cookie filtering ok")


def test_localstorage_extraction() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdef"
    window = FakeWindow({}, {"authorToken": jwt, "other": "x"})
    candidates = extract_candidates(window, SPECS[Platform.PAN123])
    assert candidates and candidates[0][0] == jwt, candidates
    print("pan123 localstorage extraction ok")

    expired = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI5IiwiZXhwIjoxfQ.abcdef"
    window = FakeWindow(
        {},
        {
            "access_token": jwt,
            "refresh_token": expired,
            "someFlag": "true",
        },
    )
    candidates = extract_candidates(window, SPECS[Platform.XUNLEI])
    assert candidates and candidates[0][0] == jwt, candidates
    assert candidates[0][1] == expired, candidates
    print("xunlei token extraction ok")


def test_args() -> None:
    parsed = parse_weblogin_args(["app.exe", "--weblogin", "quark", "--out", "C:/x.json"])
    assert parsed == ("quark", "C:/x.json"), parsed
    assert parse_weblogin_args(["app.exe"]) is None
    print("arg parsing ok")


def test_real_window() -> None:
    """真开一次登录窗口（迅雷），3 秒后自动关闭，检查结果文件落盘。"""
    out_path = os.path.join(tempfile.gettempdir(), "yixi_login_e2e.json")
    if os.path.exists(out_path):
        os.remove(out_path)
    env = dict(os.environ)
    env["YIXI_LOGIN_AUTOCLOSE"] = "6"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "app.py"), "--weblogin", "xunlei", "--out", out_path],
        env=env,
    )
    deadline = time.time() + 90
    result = None
    while time.time() < deadline:
        result = read_result(out_path)
        if result is not None:
            break
        if proc.poll() is not None and result is None:
            break
        time.sleep(0.5)
    if proc.poll() is None:
        proc.kill()
    assert result is not None, "登录窗口没有写出结果文件"
    assert result.get("ok") is False, result
    print("real login window ok:", result.get("error"))


if __name__ == "__main__":
    test_args()
    test_cookie_extraction()
    test_localstorage_extraction()
    test_real_window()
    print("WEBLOGIN TESTS PASSED")
