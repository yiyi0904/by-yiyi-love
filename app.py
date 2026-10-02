"""亦析 PC 启动入口。"""

from __future__ import annotations

import os
import sys


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    _enable_dpi_awareness()
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YiXi.PC")
        except Exception:  # noqa: BLE001
            pass

    if "--selftest" in sys.argv:
        return _selftest()

    if "--spawntest" in sys.argv:
        return _spawntest()

    from yunx.weblogin import parse_weblogin_args, run_login_window

    login_args = parse_weblogin_args(sys.argv)
    if login_args is not None:
        return run_login_window(login_args[0], login_args[1])

    from yunx.ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()
    return 0


def _selftest() -> int:
    """打包后自检：校验依赖与界面能否正常初始化，结果写入临时文件。"""
    import tempfile
    import traceback

    lines: list[str] = []
    code = 0
    try:
        from yunx.platforms import all_clients
        from yunx.platforms.c139 import decrypt_body, encrypt_body
        from yunx.platforms.pan123 import make_sign

        payload = "selftest"
        assert decrypt_body(encrypt_body(payload)) == payload
        assert make_sign("/b/api/x")[1]
        lines.append(f"platforms: {', '.join(p.value for p in all_clients())}")

        from yunx.ui.main_window import MainWindow

        app = MainWindow()
        app.update_idletasks()
        app.update()
        lines.append(f"gui ok: {app.winfo_width()}x{app.winfo_height()}")

        # 账号对话框：确认底部按钮在任何平台都完整可见
        from yunx.config import Config
        from yunx.models import Platform as _Platform
        from yunx.ui.dialogs import CredentialDialog

        dialog = CredentialDialog(app, Config())
        dialog.deiconify()
        for _p in _Platform:
            dialog._select(_p)  # noqa: SLF001
            dialog.update_idletasks()
            dialog.update()
            button = dialog.login_button
            top = button.winfo_rooty() - dialog.winfo_rooty()
            bottom = top + button.winfo_height()
            assert button.winfo_ismapped(), f"{_p.value}: 登录按钮不可见"
            assert bottom <= dialog.winfo_height(), f"{_p.value}: 按钮越界 {bottom}"
        lines.append(f"credential dialog ok: {dialog.winfo_width()}x{dialog.winfo_height()}")
        dialog.destroy()
        app._on_close()

        lines.append(_selftest_webview())
    except Exception:  # noqa: BLE001
        code = 1
        lines.append(traceback.format_exc())

    report = os.path.join(tempfile.gettempdir(), "yunx_pc_selftest.txt")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return code


def _spawntest() -> int:
    """验收测试：程序文件被移动后，网页登录是否仍能正常打开（不再依赖重启自身）。"""
    import json
    import queue
    import tempfile
    import time
    import sys

    from yunx.models import Platform
    from yunx.weblogin import get_login_service

    info: dict = {
        "sys.executable": sys.executable,
        "sys.frozen": getattr(sys, "frozen", False),
        "executable_exists_at_start": os.path.isfile(sys.executable),
    }
    platform = Platform.XUNLEI
    for arg in sys.argv:
        if arg in ("quark", "xunlei", "uc", "baidu", "pan123", "c139"):
            platform = Platform(arg)
            break
    info["platform"] = platform.value
    service = get_login_service()
    result_queue = service.open(platform)
    deadline = time.time() + 90
    while time.time() < deadline and not service.is_running():
        time.sleep(0.5)
    info["window_opened"] = service.is_running()
    # 给外部脚本留出「移动 exe」的时间窗口
    time.sleep(6)
    session = service._active  # noqa: SLF001
    if session is not None and platform.value == "xunlei":
        time.sleep(12)
        try:
            window = session.window
            info["page_url"] = (window.evaluate_js("location.href") or "")[:120]
            info["page_title"] = window.evaluate_js("document.title")
            info["login_inputs"] = window.evaluate_js(
                "document.querySelectorAll('input').length"
            )
        except Exception as exc:  # noqa: BLE001
            info["page_error"] = str(exc)
    time.sleep(8)
    info["executable_exists_after_move"] = os.path.isfile(sys.executable)
    service.close_active()
    try:
        payload = result_queue.get(timeout=40)
    except queue.Empty:
        payload = {"ok": None, "error": "超时未返回结果"}
    info["result_ok"] = payload.get("ok")
    info["result_error"] = payload.get("error")
    # 与正常关闭流程一致：等 WebView 会话线程退出，避免退出时 .NET 侧报错
    service.shutdown()
    report = os.path.join(tempfile.gettempdir(), "yixi_spawntest.json")
    with open(report, "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=2)
    return 0


def _selftest_webview() -> str:
    """校验打包后的 WebView2 链路：窗口、JS、按域名读 Cookie。"""
    import json
    import time
    import traceback

    import webview

    from yunx.weblogin import cookies_for_uri, read_all_cookies

    result: dict = {}

    def run(window) -> None:
        try:
            for _ in range(40):
                if (window.get_current_url() or ""):
                    break
                time.sleep(0.25)
            time.sleep(3)
            result["url"] = window.get_current_url()
            result["js"] = window.evaluate_js("1+1")
            from yunx.models import Platform
            from yunx.weblogin import SPECS

            spec = SPECS[Platform.BAIDU]
            result["by_uri"] = len(cookies_for_uri(window, "https://pan.baidu.com/", timeout=8))
            result["merged"] = len(read_all_cookies(window, spec))
        except Exception:  # noqa: BLE001
            result["error"] = traceback.format_exc()
        finally:
            window.destroy()

    window = webview.create_window(
        "自检", "https://pan.baidu.com/", width=760, height=520, hidden=True
    )
    webview.start(run, window, gui="edgechromium", private_mode=True)
    return "webview ok: " + json.dumps(result, ensure_ascii=False)[:400]


if __name__ == "__main__":
    raise SystemExit(main())
