"""123 云盘（匿名列目录 + 签名取下载直链）。"""

from __future__ import annotations

import base64
import json
import random
import time
import urllib.parse
import uuid
import zlib
from datetime import datetime, timedelta, timezone

from ..link_parser import parse_share
from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession
from ..net import api_request
from .base import Logger, PanClient

API_BASE = "https://yun.123pan.cn"
DOWNLOAD_BASE = "https://www.123865.com"
REFERER = "https://yun.123pan.cn/"

WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)
DART_UA = "Dart/3.12 (dart:io)"

SIGN_TABLE = "adefghlmyijnopkqrstubcvwsz"
SIGN_OFFSET_SECONDS = 57600  # +16h


def _crc32_hex(text: str) -> str:
    return format(zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF, "x")


def make_sign(path: str, ts: int | None = None) -> tuple[str, str]:
    """生成 123 云盘 auth-key / auth-value。"""
    ts = int(ts if ts is not None else time.time())
    moment = datetime.fromtimestamp(ts + SIGN_OFFSET_SECONDS, tz=timezone.utc)
    stamp = moment.strftime("%Y%m%d%H%M")
    substituted = "".join(SIGN_TABLE[int(ch)] for ch in stamp)
    auth_key = _crc32_hex(substituted)
    rand = random.randint(0, 9_999_999)
    data = f"{ts}|{rand}|{path}|web|3|{auth_key}"
    return auth_key, f"{ts}-{rand}-{_crc32_hex(data)}"


def decode_download_url(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        try:
            text = base64.b64decode(raw).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            return None
        return text if text.lower().startswith("http") else None
    idx = raw.find("params=")
    if idx < 0:
        return None
    params = raw[idx + len("params=") :].split("&", 1)[0]
    normalized = params.replace("-", "+").replace("_", "/")
    padding = "=" * (-len(normalized) % 4)
    try:
        return base64.b64decode(normalized + padding).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return None


class Pan123Client(PanClient):
    platform = Platform.PAN123
    cred_kind = "token"
    cred_title = "authorToken"
    cred_help = (
        "推荐：点下方「网页登录」，在弹出的官方页面登录，程序会自动读取 authorToken 并保存。\n\n"
        "手动方式：浏览器登录 https://yun.123pan.cn/ 后按 F12 → Application → "
        "Local Storage → https://yun.123pan.cn，复制 authorToken 的值（形如 eyJ...）。\n"
        "注意：浏览分享目录无需登录，只有「取下载直链」需要。"
    )

    def __init__(self) -> None:
        super().__init__()
        self.loginuuid = uuid.uuid4().hex

    # -- 凭证 ---------------------------------------------------------------
    def check_credential(self, credential: str) -> str | None:
        token = self.require_credential(credential)
        payload = self._get_auth(f"{API_BASE}/b/api/user/info", "/b/api/user/info", token)
        self._check(payload, "获取用户信息失败")
        return ((payload.get("data") or {}).get("Nickname")) or None

    # -- 请求 ---------------------------------------------------------------
    def _auth_headers(
        self, path: str, token: str, platform: str = "web", app_version: str = "3"
    ) -> dict[str, str]:
        auth_key, auth_value = make_sign(path)
        return {
            "platform": platform,
            "app-version": app_version,
            "authorization": f"Bearer {token}",
            "loginuuid": self.loginuuid,
            "auth-key": auth_key,
            "auth-value": auth_value,
            "User-Agent": WEB_UA,
            "Accept": "application/json, text/plain, */*",
        }

    def _get_auth(self, url: str, path: str, token: str) -> dict:
        resp = api_request("GET", url, headers=self._auth_headers(path, token))
        return self._parse(resp)

    def _post_auth(
        self,
        url: str,
        path: str,
        body: dict,
        token: str,
        platform: str = "web",
        app_version: str = "3",
    ) -> dict:
        headers = self._auth_headers(path, token, platform, app_version)
        headers["Content-Type"] = "application/json;charset=UTF-8"
        resp = api_request("POST", url, headers=headers, data=json.dumps(body))
        return self._parse(resp)

    @staticmethod
    def _parse(resp) -> dict:
        try:
            return resp.json()
        except ValueError:
            raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")

    @staticmethod
    def _check(payload: dict, fallback: str) -> None:
        code = payload.get("code")
        if code == 0:
            return
        message = payload.get("message") or fallback
        raise ApiError(f"{message}（code={code}）")

    # -- 分享解析 -----------------------------------------------------------
    def open_session(self, link: str, pwd: str | None, credential: str) -> ShareSession:
        parsed = parse_share(link)
        if parsed is None:
            raise ApiError("无法识别 123 云盘分享链接")
        share_pwd = (pwd or "").strip() or (parsed.pwd or "")
        files = self._share_list(parsed.share_id, share_pwd, "0", "0", 1)
        title = files[0].name if files else parsed.share_id
        return ShareSession(
            share_id=parsed.share_id,
            token=share_pwd,
            title=title,
            extra={"parent": "0"},
        )

    def _share_list(
        self, share_key: str, share_pwd: str, parent_id: str, next_cursor: str, page: int
    ) -> list[PanFile]:
        params = {
            "limit": "100",
            "next": next_cursor,
            "orderBy": "file_name",
            "orderDirection": "asc",
            "shareKey": share_key,
            "ParentFileId": parent_id,
            "Page": str(page),
        }
        if share_pwd:
            params["SharePwd"] = share_pwd
        url = f"{API_BASE}/b/api/share/get?" + urllib.parse.urlencode(params)
        resp = api_request("GET", url, headers={"User-Agent": DART_UA})
        payload = self._parse(resp)
        self._check(payload, "获取文件列表失败")
        data = payload.get("data") or {}
        if data.get("Expired"):
            raise ApiError("分享已失效")
        return self._parse_info_list(data)

    @staticmethod
    def _parse_info_list(data: dict) -> list[PanFile]:
        result = []
        for item in data.get("InfoList") or []:
            size = int(item.get("Size") or 0)
            result.append(
                PanFile(
                    fid=str(item.get("FileId") or ""),
                    name=item.get("FileName") or "",
                    size=size,
                    is_dir=int(item.get("Type") or 0) == 1,
                    parent_fid=str(item.get("ParentFileId") or ""),
                    fid_token="|".join(
                        [
                            str(item.get("S3KeyFlag") or ""),
                            str(item.get("Etag") or ""),
                            str(item.get("StorageNode") or ""),
                        ]
                    ),
                    modify_time=str(item.get("UpdateAt") or ""),
                )
            )
        return result

    def list_files(self, session: ShareSession, dir_id: str, credential: str) -> list[PanFile]:
        files: list[PanFile] = []
        parent = dir_id or "0"
        cursor = "0"
        for page in range(1, 51):
            batch = self._share_list(session.share_id, session.token, parent, "0", page)
            files.extend(batch)
            if not batch:
                break
        return files

    # -- 取链 ---------------------------------------------------------------
    @staticmethod
    def _decode_token(fid_token: str) -> tuple[str, str, str]:
        parts = (fid_token or "").split("|")
        while len(parts) < 3:
            parts.append("")
        return parts[0], parts[1], parts[2]

    def _follow_redirect(self, url: str) -> str:
        current = url
        for _ in range(5):
            nxt = self._probe_redirect(current)
            if not nxt:
                return current
            current = nxt
        return current

    def _probe_redirect(self, url: str) -> str | None:
        try:
            resp = api_request(
                "GET",
                url,
                headers={"Referer": REFERER, "User-Agent": DART_UA},
                stream=True,
                timeout=(15, 30),
            )
        except Exception:  # noqa: BLE001
            return None
        with resp:
            length = resp.headers.get("Content-Length")
            if length is None or not length.isdigit() or int(length) > 8192:
                return None
            body = resp.text or ""
        body = body.lstrip()
        if not body.startswith("{"):
            return None
        try:
            data = json.loads(body)
        except ValueError:
            return None
        return ((data.get("data") or {}).get("redirect_url")) or None

    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        token = self.require_credential(credential)
        s3key, etag, _ = self._decode_token(file.fid_token)
        body = {
            "ShareKey": session.share_id,
            "FileID": int(file.fid or 0),
            "S3KeyFlag": s3key,
            "Size": file.size,
            "Etag": etag,
        }
        self._log(log, "  获取下载直链…")
        payload = self._post_auth(
            f"{DOWNLOAD_BASE}/b/api/share/download/info",
            "/b/api/share/download/info",
            body,
            token,
            platform="android",
            app_version="39",
        )
        self._check(payload, "获取下载链接失败")
        data = payload.get("data") or {}
        raw = data.get("DownloadURL") or ""
        if not raw:
            raise ApiError("未返回下载链接")
        url = self._follow_redirect(decode_download_url(raw) or raw)
        return DownloadLink(url=url, filename=file.name, size=file.size)

    def download_headers(self, credential: str) -> dict[str, str]:
        return {"Referer": REFERER, "User-Agent": WEB_UA}
