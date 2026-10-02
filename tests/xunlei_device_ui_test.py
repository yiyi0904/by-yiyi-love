"""验证迅雷「网页登录」：设备码申请、官方授权页加载、轮询等待授权。"""

from __future__ import annotations

import os
import queue
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.models import Platform
from yunx.weblogin import get_login_service


def main() -> int:
    service = get_login_service()
    result = service.open(Platform.XUNLEI)
    deadline = time.time() + 60
    while time.time() < deadline and not service.is_running():
        time.sleep(0.3)
    assert service.is_running(), "登录会话没建立"
    print("登录窗口已创建")

    session = service._active  # noqa: SLF001
    # 等设备码申请 + 页面跳转
    for _ in range(40):
        time.sleep(0.5)
        if getattr(session, "user_code", ""):
            break
    print("授权码:", getattr(session, "user_code", "(空)"))
    assert session.user_code, "没有拿到授权码"

    time.sleep(4)
    window = session.window
    print("当前页面:", (window.get_current_url() or "")[:80])
    title = window.evaluate_js("document.title")
    text = (window.evaluate_js("document.body ? document.body.innerText.slice(0,200) : ''") or "")
    images = window.evaluate_js(
        "document.querySelectorAll('img.qr').length"
    )
    print("页面标题:", title)
    print("页面内容:", text.replace("\n", " ")[:160])
    print("二维码图片数量:", images)
    assert "扫码登录" in (title or ""), title
    assert images == 1, images
    assert session.user_code in text, "页面上没有授权码"

    service.close_active()
    try:
        payload = result.get(timeout=30)
    except queue.Empty:
        print("FAILED: 没收到结果")
        return 1
    print("结果:", payload.get("ok"), "/", payload.get("error"))
    service.shutdown()
    print("XUNLEI WEB LOGIN TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
