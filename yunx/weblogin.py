"""内置网页登录：在应用内打开官方登录页，登录后自动提取凭证。

主路径是**同进程**运行：pywebview（Windows 上使用系统自带的 WebView2）要求
在主线程调用 `start()`，而主线程被 tkinter 占用，所以在一个后台线程里
伪装线程名 + 屏蔽 signal 注册后常驻运行，登录窗口按需创建 / 销毁。

这样不依赖重新启动自身，程序被移动 / 重命名也不会失效；
若同进程方案初始化失败，才回退到 `--weblogin` 子进程方案。
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Callable

from .models import ApiError, Platform
from .platforms import get_client
from .util import asset_path

JWT_RE = re.compile(r"^ey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}$")

# 139 只保留关键字段（与安卓版一致，避免 Cookie 过长被网关拒绝）
C139_KEEP_KEYS = {
    "Os_SSo_Sid", "RMKEY", "UserData", "Login_UserNumber",
    "_139_index_isLoginType", "UUIDToken", "JSESSIONID",
    "areaCode8011", "provCode8011",
    "authorization", "auth_token", "token", "ud_id",
    "ORCHES-I-ACCOUNT-SIMPLIFY", "ORCHES-I-ACCOUNT-ENCRYPT", "nation_code",
    "platform", "cutover_status", "isUserDomainError", "a_k", "skey", "WT_FPC",
}


@dataclass
class LoginSpec:
    platform: Platform
    url: str
    hint: str
    kind: str = "cookie"  # cookie | localstorage
    keep_keys: set[str] | None = None
    ls_keys: tuple[str, ...] = ()
    cookie_uris: tuple[str, ...] = ()


SPECS: dict[Platform, LoginSpec] = {
    Platform.QUARK: LoginSpec(
        platform=Platform.QUARK,
        url="https://pan.quark.cn/?fr=pc&platform=pc",
        hint="请用夸克网盘的扫码 / 手机号方式登录",
        cookie_uris=("https://pan.quark.cn/", "https://drive-pc.quark.cn/"),
    ),
    Platform.UC: LoginSpec(
        platform=Platform.UC,
        url="https://drive.uc.cn/",
        hint="请用 UC 网盘账号登录",
        cookie_uris=("https://drive.uc.cn/", "https://pc-api.uc.cn/"),
    ),
    Platform.BAIDU: LoginSpec(
        platform=Platform.BAIDU,
        url="https://pan.baidu.com/",
        hint="请用百度账号登录（可能需要短信验证）",
        cookie_uris=("https://pan.baidu.com/",),
    ),
    Platform.C139: LoginSpec(
        platform=Platform.C139,
        url="https://yun.139.com/",
        hint="请用中国移动手机号登录（和彩云 / 移动云盘）",
        keep_keys=C139_KEEP_KEYS,
        cookie_uris=("https://yun.139.com/", "https://mail.10086.cn/"),
    ),
    Platform.PAN123: LoginSpec(
        platform=Platform.PAN123,
        url="https://yun.123pan.cn/",
        hint="请用 123 云盘账号登录；登录后停留在网盘页面，程序会自动读取 authorToken",
        kind="localstorage",
        ls_keys=("authorToken", "token", "Authorization", "access_token"),
        cookie_uris=("https://yun.123pan.cn/", "https://www.123pan.com/"),
    ),
    Platform.XUNLEI: LoginSpec(
        platform=Platform.XUNLEI,
        url="https://pan.xunlei.com/",
        hint="请在页面上登录（支持迅雷 App 扫码 / 账号密码 / 短信验证码）",
        kind="oauth",
        cookie_uris=("https://pan.xunlei.com/", "https://xluser-ssl.xunlei.com/"),
    ),
}


# --------------------------------------------------------------------------
# Cookie / localStorage 读取
# --------------------------------------------------------------------------
def cookies_for_uri(window, uri: str, timeout: float = 6.0) -> list[tuple[str, str]]:
    """向 WebView2 的 CookieManager 查询指定域名的 Cookie（含 HttpOnly）。

    必须从非 UI 线程调用；解析 Cookie 字段需要回到 UI 线程（WebView2 的 COM 限制）。
    """
    try:
        import clr  # noqa: F401
        from threading import Semaphore

        from System import Action, Func, Type
        from System.Threading.Tasks import Task
    except Exception:  # noqa: BLE001
        return []

    form = getattr(window, "native", None)
    browser = getattr(form, "browser", None)
    view = getattr(browser, "webview", None)
    if form is None or view is None:
        return []

    raw: list = []
    out: list[tuple[str, str]] = []
    semaphore = Semaphore(0)

    def parse() -> None:
        try:
            for item in raw:
                out.append((str(item.Name), str(item.Value)))
        except Exception:  # noqa: BLE001
            pass
        finally:
            semaphore.release()

    def callback(task) -> None:
        try:
            raw.extend(task.Result)
            form.Invoke(Func[Type](parse))
        except Exception:  # noqa: BLE001
            semaphore.release()

    def start() -> None:
        try:
            view.CoreWebView2.CookieManager.GetCookiesAsync(uri).ContinueWith(
                Action[Task](callback)
            )
        except Exception:  # noqa: BLE001
            semaphore.release()

    try:
        form.Invoke(Func[Type](start))
    except Exception:  # noqa: BLE001
        return []
    semaphore.acquire(timeout=timeout)
    return out


def _read_cookies(window) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        raw = window.get_cookies() or []
    except Exception:  # noqa: BLE001
        return result
    for item in raw:
        try:
            entries = item.items()
        except Exception:  # noqa: BLE001
            continue
        for name, morsel in entries:
            try:
                result.setdefault(name, morsel.value)
            except Exception:  # noqa: BLE001
                continue
    return result


def read_all_cookies(window, spec: LoginSpec) -> dict[str, str]:
    """优先按域名精确读取，失败时回退到当前页面 URL 的 Cookie。"""
    merged: dict[str, str] = {}
    for uri in spec.cookie_uris:
        for name, value in cookies_for_uri(window, uri):
            merged.setdefault(name, value)
    if not merged:
        merged = _read_cookies(window)
    return merged


_LS_DUMP_JS = (
    "JSON.stringify((()=>{const o={};try{for(let i=0;i<localStorage.length;i++)"
    "{const k=localStorage.key(i);o[k]=localStorage.getItem(k);}}catch(e){}return o;})())"
)


def _read_local_storage(window) -> dict[str, str]:
    try:
        raw = window.evaluate_js(_LS_DUMP_JS)
    except Exception:  # noqa: BLE001
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    return {}


def _cookie_header(cookies: dict[str, str], spec: LoginSpec) -> str:
    if spec.keep_keys is not None:
        cookies = {k: v for k, v in cookies.items() if k in spec.keep_keys}
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


def _clean_token(value: str) -> str:
    value = (value or "").strip().strip('"').strip("'")
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def _is_jwt(value: str) -> bool:
    return bool(JWT_RE.match(value or ""))


def _token_expired(token: str) -> bool:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8", "ignore"))
        exp = float(data.get("exp") or 0)
        return bool(exp and exp < time.time())
    except Exception:  # noqa: BLE001
        return False


def extract_candidates(window, spec: LoginSpec) -> list[tuple[str, str]]:
    """返回 [(credential, refresh_token), ...]，按优先级排序。"""
    candidates: list[tuple[str, str]] = []
    platform = spec.platform

    if spec.kind == "cookie":
        header = _cookie_header(read_all_cookies(window, spec), spec)
        if header:
            candidates.append((header, ""))
        return candidates

    store = _read_local_storage(window)
    try:
        cookie_values = read_all_cookies(window, spec)
    except Exception:  # noqa: BLE001
        cookie_values = {}

    if platform is Platform.PAN123:
        for key in spec.ls_keys:
            value = _clean_token(store.get(key, ""))
            if value:
                candidates.append((value, ""))
        for bucket in (store, cookie_values):
            for _key, value in bucket.items():
                value = _clean_token(value)
                if _is_jwt(value) and all(value != c[0] for c in candidates):
                    candidates.append((value, ""))
        return candidates

    if platform is Platform.XUNLEI:
        refresh = ""
        for key, value in {**cookie_values, **store}.items():
            if "refresh" in key.lower() and _is_jwt(_clean_token(value)):
                refresh = _clean_token(value)
                break
        fresh: list[str] = []
        stale: list[str] = []
        seen: set[str] = set()
        for bucket in (store, cookie_values):
            for key, raw_value in bucket.items():
                value = _clean_token(raw_value)
                if not _is_jwt(value) or value in seen:
                    continue
                if "refresh" in key.lower() or value == refresh:
                    continue
                seen.add(value)
                (stale if _token_expired(value) else fresh).append(value)
        for value in fresh + stale:
            candidates.append((value, refresh))
        return candidates

    return candidates


def validate(platform: Platform, credential: str, refresh_token: str = "") -> str | None:
    """用平台接口验证凭证，成功返回昵称。"""
    client = get_client(platform)
    if platform is Platform.XUNLEI and refresh_token:
        client.refresh_token = refresh_token
    nickname = client.check_credential(credential)
    if platform is Platform.XUNLEI:
        # 光能查到账号还不够：还得确认它能调下载接口（验证码 client_id 必须匹配）
        try:
            client.verify_pan_access()
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                f"该凭证无法用于下载接口（{exc}）。请改用「账号密码登录」。"
            ) from exc
    return nickname


# --------------------------------------------------------------------------
# 页面内的顶部横幅
# --------------------------------------------------------------------------
_BANNER_ID = "yixi-login-bar"


def _banner_script(spec: LoginSpec, status: str, ready: bool) -> str:
    color = "#1a7f37" if ready else "#1f6feb"
    text = json.dumps(spec.hint, ensure_ascii=False)
    state_text = json.dumps(status, ensure_ascii=False)
    button = json.dumps("保存凭证并返回", ensure_ascii=False)
    return f"""
(function(){{
  var old = document.getElementById({json.dumps(_BANNER_ID)});
  if (old) old.remove();
  var bar = document.createElement('div');
  bar.id = {json.dumps(_BANNER_ID)};
  bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;'
    + 'background:{color};color:#fff;font:13px/1.6 "Microsoft YaHei",sans-serif;'
    + 'padding:8px 14px;display:flex;align-items:center;gap:14px;'
    + 'box-shadow:0 2px 10px rgba(0,0,0,.35)';
  var msg = document.createElement('span');
  msg.textContent = {text};
  var st = document.createElement('span');
  st.textContent = {state_text};
  st.style.cssText = 'opacity:.92';
  var btn = document.createElement('button');
  btn.textContent = {button};
  btn.style.cssText = 'margin-left:auto;background:#fff;color:{color};border:0;'
    + 'border-radius:4px;padding:6px 14px;font-size:13px;font-weight:700;cursor:pointer';
  btn.onclick = function(){{
    btn.disabled = true;
    btn.textContent = '正在保存…';
    if (window.pywebview && window.pywebview.api) {{
      window.pywebview.api.save_credential();
    }}
  }};
  bar.appendChild(msg); bar.appendChild(st); bar.appendChild(btn);
  document.documentElement.appendChild(bar);
}})();
"""


def _apply_form_icon(window) -> None:
    """把程序图标设置到 WebView2 窗体的标题栏 / 任务栏。"""
    ico = asset_path("app.ico")
    if not os.path.exists(ico):
        return
    try:
        from System import Func, Type
        from System.Drawing import Icon
    except Exception:  # noqa: BLE001
        return
    form = getattr(window, "native", None)
    if form is None:
        return

    def set_icon() -> None:
        try:
            form.Icon = Icon(ico)
        except Exception:  # noqa: BLE001
            pass

    try:
        form.Invoke(Func[Type](set_icon))
    except Exception:  # noqa: BLE001
        pass


NOT_FOUND_MESSAGE = (
    "尚未检测到有效登录。可以重新点「网页登录」，或在「账号与凭证」里手动粘贴凭证"
)


class LoginSession:
    """一次登录窗口会话：轮询登录状态、提取凭证、交付结果（只交付一次）。"""

    def __init__(self, platform: Platform, deliver: Callable[[dict], None]) -> None:
        self.platform = platform
        self.spec = SPECS[platform]
        self.deliver = deliver
        self.window = None
        self.ready = False
        self.saved = False
        self.done = False
        self.delivered = False
        self.saw_candidates = False
        self.credential = ""
        self.refresh_token = ""
        self.nickname = ""
        self.user_code = ""
        self._started = False
        self._lock = threading.Lock()

    # -- 供页面按钮调用（js_api） -------------------------------------------
    def save_credential(self) -> bool:
        if not self.ready:
            return False
        self.saved = True
        self.done = True
        self._deliver(True)
        return True

    def close_window(self) -> bool:
        self._destroy()
        return True

    # -- 绑定窗口 -----------------------------------------------------------
    def bind(self, window) -> None:
        self.window = window
        try:
            window.events.loaded += self._on_loaded
            window.events.closing += self._on_closing
        except Exception:  # noqa: BLE001
            pass

    def _on_loaded(self) -> None:
        # loaded 事件会随页面跳转 / load_html 多次触发，只处理第一次
        if self._started:
            return
        self._started = True
        time.sleep(0.3)
        _apply_form_icon(self.window)
        if self.spec.kind == "oauth":
            threading.Thread(target=self._oauth_flow, daemon=True).start()
            return
        if self.spec.kind == "device":
            threading.Thread(target=self._device_flow, daemon=True).start()
            return
        self._set_banner("等待登录…", False)
        threading.Thread(target=self._poll, daemon=True).start()

    # -- 扫码 / 设备码授权（迅雷） ------------------------------------------
    def _oauth_flow(self) -> None:
        """网页登录：打开官方授权页，用户自己登录，我们拿授权码换 token。"""
        import secrets

        from .platforms.xunlei import (
            build_authorize_url,
            exchange_authorization_code,
            make_pkce,
        )

        verifier, challenge = make_pkce()
        state = "state-" + secrets.token_urlsafe(9)
        url = build_authorize_url(challenge, state)
        self._set_banner("正在打开迅雷登录页…", False)
        try:
            self.window.load_url(url)
        except Exception as exc:  # noqa: BLE001
            self._set_banner(f"打开登录页失败：{exc}", False)
            return
        self._set_banner("请在页面上登录（扫码 / 账号密码 / 短信均可）", False)

        deadline = time.time() + 15 * 60
        last_code = ""
        while not self.done and time.time() < deadline:
            time.sleep(0.5)
            if self.done:
                return
            try:
                # 用页面里的 location.href，SPA 路由跳转也能第一时间看到
                current = self.window.evaluate_js("location.href") or ""
                if "code=" not in current:
                    current = self.window.get_current_url() or current
            except Exception:  # noqa: BLE001
                continue
            code = ""
            if "code=" in current:
                query = urllib.parse.urlparse(current).query
                code = urllib.parse.parse_qs(query).get("code", [""])[0]
            if not code or code == last_code:
                continue
            last_code = code
            self._set_banner("已获取授权，正在换取凭证…", False)
            result = exchange_authorization_code(code, verifier)
            if not result.get("ok"):
                self._set_banner(f"换取凭证失败：{result.get('message')}", False)
                continue
            self.credential = result.get("access_token", "")
            self.refresh_token = result.get("refresh_token", "")
            try:
                self.nickname = validate(
                    self.platform, self.credential, self.refresh_token
                ) or ""
            except Exception as exc:  # noqa: BLE001
                # 凭证拿到了但不能用（例如 client_id 不匹配），立刻告诉用户
                self.credential = ""
                self.refresh_token = ""
                self._set_banner(f"✖ {exc}", False)
                return
            self.ready = True
            suffix = f"（{self.nickname}）" if self.nickname else ""
            self._set_banner(f"✔ 登录成功{suffix}，点击右侧按钮保存", True)
            return
        if not self.done:
            self._set_banner("等待登录超时，请重新点击「网页登录」", False)

    def _device_flow(self) -> None:
        from .platforms.xunlei import poll_device_token, request_device_code

        self._set_banner("正在申请登录二维码…", False)
        try:
            info = request_device_code()
        except Exception as exc:  # noqa: BLE001
            self._set_banner(f"申请登录二维码失败：{exc}", False)
            return
        self.user_code = info.get("user_code") or ""
        self._set_banner("请用手机「迅雷」App 扫描二维码完成授权", False)
        self._show_device_page(info)

        interval = int(info.get("interval") or 2)
        deadline = time.time() + int(info.get("expires_in") or 120)
        while not self.done and time.time() < deadline:
            time.sleep(interval)
            if self.done:
                return
            remaining = int(deadline - time.time())
            self._set_banner(
                f"等待手机迅雷 App 确认授权…（剩余 {remaining}s）", False
            )
            try:
                result = poll_device_token(info["device_code"])
            except Exception:  # noqa: BLE001
                continue
            if result.get("ok"):
                self.credential = result.get("access_token", "")
                self.refresh_token = result.get("refresh_token", "")
                try:
                    self.nickname = validate(
                        self.platform, self.credential, self.refresh_token
                    ) or ""
                except Exception as exc:  # noqa: BLE001
                    self.credential = ""
                    self.refresh_token = ""
                    self._set_banner(f"✖ {exc}", False)
                    return
                self.ready = True
                suffix = f"（{self.nickname}）" if self.nickname else ""
                self._set_banner(f"✔ 登录成功{suffix}，点击右侧按钮保存", True)
                return
            if not result.get("pending"):
                self._set_banner(f"授权失败：{result.get('message')}", False)
                return
        if not self.done:
            self._set_banner("二维码已过期，请重新点击「扫码登录」", False)

    def _show_device_page(self, info: dict) -> None:
        """在窗口里显示我们自己渲染的授权页（二维码 + 授权码）。"""
        from .device_page import device_page

        html = device_page(
            info,
            title="迅雷网盘 · 扫码登录",
            subtitle="用手机「迅雷」App 扫码并在手机上确认授权",
            steps=(
                "<li>打开手机 <b>迅雷 App</b>，进入 <b>我的 → 扫一扫</b>，扫描上方二维码；</li>"
                "<li>若无法扫码，可在迅雷 App 内输入上面的 <b>授权码</b>；</li>"
                "<li>确认后稍等 1–2 秒，顶部横幅会变成绿色提示登录成功。</li>"
            ),
            tip="扫码不方便？关掉本窗口，回「账号与凭证」点「账号密码登录」即可。",
        )
        try:
            self.window.load_html(html, "https://pan.xunlei.com/")
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            import base64

            self.window.load_url(
                "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode()
            )
        except Exception:  # noqa: BLE001
            pass

    def _on_closing(self) -> bool:
        self.done = True
        if self.saved or self.delivered:
            return True
        if self.ready:
            self._deliver(True, destroy=False)
        else:
            self._deliver(False, error=NOT_FOUND_MESSAGE if self.saw_candidates
                          else "已取消登录", destroy=False)
        return True

    # -- 轮询 ---------------------------------------------------------------
    def _poll(self) -> None:
        deadline = time.time() + 30 * 60
        last_state = ""
        while time.time() < deadline and not self.done:
            time.sleep(2.0)
            if self.done:
                return
            try:
                candidates = extract_candidates(self.window, self.spec)
            except Exception:  # noqa: BLE001
                candidates = []
            if not candidates:
                if last_state != "waiting":
                    last_state = "waiting"
                    self._set_banner("等待登录…", False)
                continue
            self.saw_candidates = True

            for credential, refresh_token in candidates[:6]:
                if self.done:
                    return
                try:
                    nickname = validate(self.platform, credential, refresh_token)
                except Exception:  # noqa: BLE001
                    last_state = "invalid"
                    # 未登录时站点也会下发匿名 Cookie，这里不能直接报错
                    self._set_banner("等待登录…（已读取到会话信息，正在校验）", False)
                    continue
                self.credential = credential
                self.refresh_token = refresh_token
                self.nickname = nickname or ""
                self.ready = True
                suffix = f"（{self.nickname}）" if self.nickname else ""
                self._set_banner(f"✔ 登录成功{suffix}，点击右侧按钮保存", True)
                return

    def _set_banner(self, status: str, ready: bool) -> None:
        try:
            self.window.evaluate_js(_banner_script(self.spec, status, ready))
        except Exception:  # noqa: BLE001
            pass

    # -- 结果交付 -----------------------------------------------------------
    def _deliver(self, ok: bool, error: str = "", destroy: bool = True) -> None:
        with self._lock:
            if self.delivered:
                return
            self.delivered = True
        payload = {
            "ok": ok,
            "platform": self.platform.value,
            "credential": self.credential,
            "refresh_token": self.refresh_token,
            "nickname": self.nickname,
            "error": error,
        }
        try:
            self.deliver(payload)
        except Exception:  # noqa: BLE001
            pass
        if destroy:
            self._destroy()

    def _destroy(self) -> None:
        self.done = True
        if self.window is None:
            # 窗口还没建起来就被取消
            self._deliver(False, error="已取消登录", destroy=False)
            return
        try:
            self.window.destroy()
        except Exception:  # noqa: BLE001
            pass


class LoginApi:
    """暴露给网页的接口。

    只能是这一个瘦包装：pywebview 会递归反射 js_api 的所有公开属性，
    直接传 LoginSession 会一路反射到 .NET 窗口对象，既慢又会刷一堆递归报错。
    """

    def __init__(self, session: LoginSession) -> None:
        self._session = session

    def save_credential(self) -> bool:
        return self._session.save_credential()

    def close_window(self) -> bool:
        return self._session.close_window()


# --------------------------------------------------------------------------
# 常驻的同进程 WebView 服务
# --------------------------------------------------------------------------
#: 保存原始实现：patch 之后 signal.signal 指向 _safe_signal，不能再通过模块属性调用，
#: 否则会无限递归。
_ORIGINAL_SIGNAL = signal.signal


def _safe_signal(*args, **kwargs):
    """后台线程里注册信号不合法，直接忽略（必须调用保存下来的原始实现）。"""
    try:
        return _ORIGINAL_SIGNAL(*args, **kwargs)
    except ValueError:
        return None


class WebLoginService:
    """每次登录开一个独立的 WebView 会话（在同一进程的后台线程里跑）。

    这样不依赖重新启动自身：程序被移动、重命名、放到桌面都不影响。
    """

    def __init__(self) -> None:
        self._session_lock = threading.Lock()
        self._active: LoginSession | None = None
        self._active_lock = threading.RLock()
        self._last_error = ""
        self._fallback_proc = None
        self._fallback_queue: queue.Queue | None = None
        self._threads: list[threading.Thread] = []

    @property
    def last_error(self) -> str:
        return self._last_error

    def is_running(self) -> bool:
        with self._active_lock:
            return self._active is not None

    # -- 打开登录窗口 -------------------------------------------------------
    def open(self, platform: Platform) -> queue.Queue:
        """打开登录窗口，返回结果队列（结果 dict 只会放入一次）。"""
        result: queue.Queue = queue.Queue()
        thread = threading.Thread(target=self._begin, args=(platform, result), daemon=True)
        self._threads.append(thread)
        thread.start()
        return result

    def _begin(self, platform: Platform, result: queue.Queue) -> None:
        if not self._session_lock.acquire(blocking=False):
            result.put({"ok": False, "error": "已经打开了一个登录窗口，请先关闭它"})
            return
        try:
            self._run_session(platform, result)
        finally:
            self._session_lock.release()

    def _run_session(self, platform: Platform, result: queue.Queue) -> None:
        session = LoginSession(platform, deliver=lambda payload: result.put(payload))
        with self._active_lock:
            self._active = session
        current = threading.current_thread()
        original_name = current.name
        original_signal = signal.signal
        try:
            import webview

            spec = SPECS[platform]
            window = webview.create_window(
                f"亦析 · 登录{platform.label}",
                spec.url,
                width=1020,
                height=760,
                min_size=(720, 520),
                js_api=LoginApi(session),
            )
            if window is None:
                raise RuntimeError("WebView 窗口创建失败")
            session.bind(window)
            # pywebview 只校验线程名；后台线程里注册 signal 不合法，临时屏蔽
            current.name = "MainThread"
            signal.signal = _safe_signal  # type: ignore[assignment]
            webview.start(gui="edgechromium", private_mode=True)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            # 同进程方案不可用 → 回退到子进程
            fallback = open_via_subprocess(platform)
            if fallback is not None:
                self._fallback_proc = getattr(fallback, "proc", None)
                self._fallback_queue = fallback
                try:
                    result.put(fallback.get(timeout=60 * 30))
                except queue.Empty:
                    result.put({"ok": False, "error": "登录窗口超时未返回结果"})
                finally:
                    self._fallback_proc = None
                    self._fallback_queue = None
            else:
                result.put({"ok": False, "error": f"无法打开登录窗口：{self._last_error}"})
        finally:
            signal.signal = original_signal  # type: ignore[assignment]
            current.name = original_name
            # pywebview 的 windows 是全局列表且不会自动清理，
            # 残留的已销毁窗口会让下一次 start() 误判为多窗口会话。
            try:
                import webview as _webview

                _webview.windows.clear()
            except Exception:  # noqa: BLE001
                pass
            with self._active_lock:
                self._active = None
            # 窗口关闭但没交付结果（例如被外部销毁）→ 兜底交付
            if not session.delivered:
                session._deliver(  # noqa: SLF001
                    False,
                    error=NOT_FOUND_MESSAGE if session.saw_candidates else "已取消登录",
                )

    def close_active(self) -> None:
        with self._active_lock:
            session = self._active
        if session is not None:
            session._destroy()  # noqa: SLF001
        proc = self._fallback_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._fallback_proc = None

    def shutdown(self) -> None:
        """关闭登录窗口并等待 WebView 会话线程退出（避免退出时 .NET 侧报错）。"""
        self.close_active()
        for thread in list(self._threads):
            if thread.is_alive():
                thread.join(timeout=8)
        self._threads = [t for t in self._threads if t.is_alive()]


_SERVICE: WebLoginService | None = None
_SERVICE_LOCK = threading.Lock()


def get_login_service() -> WebLoginService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = WebLoginService()
        return _SERVICE


# --------------------------------------------------------------------------
# 回退方案：独立子进程（亦析PC.exe --weblogin <平台> --out <结果文件>）
# --------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write_result(out_path: str, payload: dict) -> None:
    tmp = out_path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, out_path)
    except OSError:
        pass


def read_result(out_path: str) -> dict | None:
    if not os.path.exists(out_path):
        return None
    try:
        with open(out_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def cleanup_result(out_path: str) -> None:
    for path in (out_path, out_path + ".tmp"):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def spawn_login(platform: Platform) -> tuple[subprocess.Popen, str]:
    """启动子进程登录窗口（仅在 exe 路径仍然有效时可用）。"""
    out_path = os.path.join(
        tempfile.gettempdir(),
        f"yixi_login_{platform.value}_{os.getpid()}_{int(time.time())}.json",
    )
    cleanup_result(out_path)
    executable = sys.executable
    if getattr(sys, "frozen", False):
        if not executable or not os.path.isfile(executable):
            raise FileNotFoundError(
                f"程序文件已被移动或重命名（{executable}），请重新启动程序后再使用网页登录"
            )
        cmd = [executable, "--weblogin", platform.value, "--out", out_path]
    else:
        cmd = [
            executable,
            os.path.join(_BASE_DIR, "app.py"),
            "--weblogin",
            platform.value,
            "--out",
            out_path,
        ]
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.Popen(cmd, creationflags=flags, env=env)
    return proc, out_path


def open_via_subprocess(platform: Platform) -> queue.Queue | None:
    """用子进程打开登录窗口，返回结果队列；无法启动时返回 None。"""
    try:
        proc, out_path = spawn_login(platform)
    except Exception:  # noqa: BLE001
        return None
    result: queue.Queue = queue.Queue()

    def watch() -> None:
        while True:
            payload = read_result(out_path)
            if payload is not None:
                cleanup_result(out_path)
                result.put(payload)
                return
            if proc.poll() is not None:
                result.put({"ok": False, "error": "登录窗口已关闭，未获取到凭证"})
                return
            time.sleep(0.5)

    threading.Thread(target=watch, daemon=True).start()
    result.proc = proc  # type: ignore[attr-defined]
    result.out_path = out_path  # type: ignore[attr-defined]
    return result


def run_login_window(platform_name: str, out_path: str) -> int:
    """子进程入口：运行登录窗口并把结果写入文件。"""
    import webview

    try:
        platform = Platform(platform_name)
    except ValueError:
        _write_result(out_path, {"ok": False, "error": f"未知平台：{platform_name}"})
        return 2

    spec = SPECS[platform]
    session = LoginSession(platform, deliver=lambda payload: _write_result(out_path, payload))
    window = webview.create_window(
        f"亦析 · 登录{platform.label}",
        spec.url,
        width=1020,
        height=760,
        min_size=(720, 520),
        js_api=LoginApi(session),
    )
    session.bind(window)

    autoclose = os.environ.get("YIXI_LOGIN_AUTOCLOSE")
    if autoclose:
        # 仅用于自动化测试 / 排障：到点自动关窗
        def _auto_close() -> None:
            time.sleep(float(autoclose))
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_auto_close, daemon=True).start()

    def final_check() -> None:
        if not session.delivered:
            if session.ready:
                session._deliver(True)  # noqa: SLF001
            else:
                session._deliver(  # noqa: SLF001
                    False,
                    error=NOT_FOUND_MESSAGE if session.saw_candidates else "已取消登录",
                )

    webview.start(gui="edgechromium", private_mode=True)
    final_check()
    return 0


def parse_weblogin_args(argv: list[str]) -> tuple[str, str] | None:
    if "--weblogin" not in argv:
        return None
    index = argv.index("--weblogin")
    if index + 1 >= len(argv):
        return None
    platform = argv[index + 1]
    out_path = ""
    if "--out" in argv:
        out_index = argv.index("--out")
        if out_index + 1 < len(argv):
            out_path = argv[out_index + 1]
    if not out_path:
        out_path = os.path.join(tempfile.gettempdir(), "yixi_login_result.json")
    return platform, out_path
