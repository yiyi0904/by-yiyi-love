"""分享链接 / 分享文案解析（与安卓版 ShareLinkParser 行为一致）。"""

from __future__ import annotations

import re

from .models import ParsedShare, Platform

_URL_RE = re.compile(r"https?://[^\s]+")

_QUARK_RE = re.compile(r"pan\.quark\.cn/s/([A-Za-z0-9]+)", re.I)
_UC_RE = re.compile(r"drive\.uc\.cn/s/([A-Za-z0-9]+)", re.I)
_XUNLEI_RE = re.compile(r"pan\.xunlei\.com/s/([A-Za-z0-9_-]+)", re.I)
_BAIDU_RE = re.compile(r"pan\.baidu\.com/s/(1[A-Za-z0-9_-]+)", re.I)
_C139_RE = re.compile(r"yun\.139\.com/shareweb/.*?/w/i/([A-Za-z0-9_-]+)", re.I)
_PAN123_RE = re.compile(
    r"123(?:865|pan)\.(?:com|cn)/s/([A-Za-z0-9]+-[A-Za-z0-9]+)", re.I
)
_PAN123_SUB_RE = re.compile(r"share\.123pan\.cn/123pan/([A-Za-z0-9-]+)", re.I)
_PAN123_SRR_RE = re.compile(r"api/srr\?sk=([A-Za-z0-9-]+)", re.I)

_PWD_IN_URL_RE = re.compile(r"[?&]pwd=([A-Za-z0-9]+)")
_PWD_IN_TEXT_RE = re.compile(r"(?:提取码|访问码|密码|pwd)[：:\s]\s*([A-Za-z0-9]{4,8})")

_TRAILING = "。，,；;)]}\"'"


def _extract_pwd(url: str, text: str) -> str | None:
    m = _PWD_IN_URL_RE.search(url)
    if m:
        return m.group(1)
    m = _PWD_IN_TEXT_RE.search(text)
    if m:
        return m.group(1)
    return None


def parse_share(text: str) -> ParsedShare | None:
    """从链接或整段分享文案中解析出 share_id、提取码与平台。"""
    if not text:
        return None
    text = text.strip()
    m = _URL_RE.search(text)
    if not m:
        return None
    url = m.group(0).rstrip(_TRAILING)

    for regex, platform in (
        (_QUARK_RE, Platform.QUARK),
        (_UC_RE, Platform.UC),
        (_XUNLEI_RE, Platform.XUNLEI),
    ):
        hit = regex.search(url)
        if hit:
            return ParsedShare(hit.group(1), _extract_pwd(url, text), platform)

    hit = _BAIDU_RE.search(url)
    if hit:
        # 百度 surl 不含开头的 "1"
        return ParsedShare(hit.group(1)[1:], _extract_pwd(url, text), Platform.BAIDU)

    hit = _C139_RE.search(url)
    if hit:
        return ParsedShare(hit.group(1), _extract_pwd(url, text), Platform.C139)

    for regex in (_PAN123_RE, _PAN123_SUB_RE, _PAN123_SRR_RE):
        hit = regex.search(url)
        if hit:
            return ParsedShare(hit.group(1), _extract_pwd(url, text), Platform.PAN123)

    return None


def detect_platform(text: str) -> Platform | None:
    parsed = parse_share(text)
    return parsed.platform if parsed else None
