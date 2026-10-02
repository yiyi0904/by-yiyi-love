"""HTTP 客户端封装：统一代理、重试、Cookie 合并。"""

from __future__ import annotations

import threading
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter

DEFAULT_TIMEOUT = (15, 60)

_proxy_lock = threading.Lock()
_proxy_url: str | None = None


def set_proxy(proxy: str | None) -> None:
    """设置全局 HTTP 代理（形如 http://127.0.0.1:7890），None/空串表示直连。"""
    global _proxy_url
    with _proxy_lock:
        _proxy_url = (proxy or "").strip() or None


def get_proxy() -> str | None:
    with _proxy_lock:
        return _proxy_url


def proxies() -> dict[str, str] | None:
    proxy = get_proxy()
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def make_session(pool_size: int = 32) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=max(pool_size, 8),
        pool_maxsize=max(pool_size, 8),
        max_retries=0,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.trust_env = False
    return session


API_SESSION = make_session(16)


def api_request(method: str, url: str, *, timeout=DEFAULT_TIMEOUT, **kwargs) -> requests.Response:
    """普通 API 请求（走全局代理）。"""
    kwargs.setdefault("allow_redirects", True)
    return API_SESSION.request(method, url, timeout=timeout, proxies=proxies(), **kwargs)


def request_json(method: str, url: str, *, timeout=DEFAULT_TIMEOUT, **kwargs):
    resp = api_request(method, url, timeout=timeout, **kwargs)
    try:
        return resp.json()
    except ValueError as exc:  # pragma: no cover - 服务端异常时才会出现
        raise RuntimeError(f"接口返回不是 JSON（HTTP {resp.status_code}）") from exc


# --------------------------------------------------------------------------
# Cookie 工具（夸克 / UC 的 __puus 保持新鲜）
# --------------------------------------------------------------------------

def set_cookies(response) -> list[str]:
    """取出响应里的全部 Set-Cookie（requests 的 headers 不支持 getlist）。"""
    raw = getattr(response, "raw", None)
    headers = getattr(raw, "headers", None)
    if headers is not None and hasattr(headers, "getlist"):
        try:
            return list(headers.getlist("Set-Cookie"))
        except Exception:  # noqa: BLE001
            pass
    value = response.headers.get("Set-Cookie")
    return [value] if value else []

_TRACKED_COOKIES = ("__puus", "__pus")


def _set_cookie(cookie: str, name: str, value: str) -> str:
    parts = [p.strip() for p in cookie.split(";") if p.strip()]
    for i, part in enumerate(parts):
        if part.startswith(f"{name}="):
            parts[i] = f"{name}={value}"
            break
    else:
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def merge_set_cookies(cookie: str, set_cookies: Iterable[str]) -> str:
    """把响应里的 __puus / __pus 合并回原 Cookie。"""
    merged = cookie
    for raw in set_cookies:
        kv = raw.split(";", 1)[0].strip()
        if "=" not in kv:
            continue
        name, _, value = kv.partition("=")
        if name in _TRACKED_COOKIES:
            merged = _set_cookie(merged, name, value)
    return merged


def drop_puus(cookie: str) -> str:
    """去掉 __puus，触发服务端重新下发。"""
    return "; ".join(
        p.strip() for p in cookie.split(";") if p.strip() and not p.strip().startswith("__puus=")
    )


def cookie_value(cookie: str, name: str) -> str | None:
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith(f"{name}="):
            value = part[len(name) + 1 :]
            if value:
                return value
    return None


def ensure_cookie(cookie: str, name: str, value: str) -> str:
    if cookie_value(cookie, name):
        return cookie
    value = (value or "").strip()
    if not value:
        return cookie
    return f"{cookie}; {name}={value}" if cookie.strip() else f"{name}={value}"
