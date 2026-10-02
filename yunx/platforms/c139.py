"""中国移动云盘 / 139 和彩云（分享接口 AES-CBC 加密 + mcloud-sign 签名）。"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import random
import re
import urllib.parse
from datetime import datetime

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..link_parser import parse_share
from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession
from ..net import api_request
from .base import Logger, PanClient

SHARE_BASE = "https://share-kd-njs.yun.139.com"
SHARE_LIST_URL = f"{SHARE_BASE}/yun-share/richlifeApp/devapp/IOutLink/getOutLinkInfoV6"
SHARE_LINK_URL = f"{SHARE_BASE}/yun-share/richlifeApp/devapp/IOutLink/dlFromOutLinkV3"
SHARE_GENERAL_URL = f"{SHARE_BASE}/yun-share/richlifeApp/devapp/IOutLink/getOutLinkGeneral"
CLOUD_BASE = "https://personal-kd-njs.yun.139.com"
FILE_LIST_URL = f"{CLOUD_BASE}/hcy/file/list"

YUN_CHANNEL_SOURCE = "10000034"
MCLOUD_VERSION = "7.17.9"
MCLOUD_CLIENT = "10701"
MCLOUD_CHANNEL = "1000101"
X_DEVICEINFO = "||9|7.17.9|chrome|116.0.0.0|2cdaf7ada9e353c70eba99092e177991||windows 10||zh-CN|||"
X_CLIENT_INFO = (
    "||9|7.17.9|chrome|116.0.0.0|2cdaf7ada9e353c70eba99092e177991||windows 10||zh-CN|||dW5kZWZpbmVk||"
)

AES_KEY = b"PVGDwmcvfs1uV3d1"

SHARE_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Mobile Safari/537.36"
)
PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

SHARE_X_DEVICEINFO = "||3|12.27.0|||||chrome 150.0.0.0|360X444|zh-cn|||"
SHARE_X_HUAWEI_CHANNELSRC = "10245500"
SHARE_X_MM_SOURCE = "0002"

_POOL = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


# --------------------------------------------------------------------------
# 加解密 / 签名
# --------------------------------------------------------------------------
def _pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    pad = block - (len(data) % block)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 16 and data[-pad:] == bytes([pad]) * pad:
        return data[:-pad]
    return data


def encrypt_body(plaintext: str) -> str:
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ct = encryptor.update(_pkcs7_pad(plaintext.encode("utf-8"))) + encryptor.finalize()
    return base64.b64encode(iv + ct).decode("ascii")


def decrypt_body(b64: str) -> str:
    raw = base64.b64decode(b64)
    iv, ct = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(AES_KEY), modes.CBC(iv))
    decryptor = cipher.decryptor()
    data = _pkcs7_unpad(decryptor.update(ct) + decryptor.finalize())
    if len(data) > 2 and data[0] == 0x1F and data[1] == 0x8B:
        data = gzip.decompress(data)
    return data.decode("utf-8", "ignore")


def _encode_uri_component(text: str) -> str:
    return (
        urllib.parse.quote(text, safe="")
        .replace("%21", "!")
        .replace("%27", "'")
        .replace("%28", "(")
        .replace("%29", ")")
        .replace("%2A", "*")
    )


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sign_header(body_json: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rand = "".join(random.choice(_POOL) for _ in range(16))
    encoded = _encode_uri_component(body_json)
    sorted_chars = "".join(sorted(encoded))
    b64 = base64.b64encode(sorted_chars.encode("utf-8")).decode("ascii")
    sign = _md5(_md5(b64) + _md5(f"{ts}:{rand}")).upper()
    return f"{ts},{rand},{sign}"


# --------------------------------------------------------------------------
# Cookie 解析
# --------------------------------------------------------------------------
def _cookie_items(cookie: str) -> dict[str, str]:
    items: dict[str, str] = {}
    for part in (cookie or "").split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            items[key.strip()] = value.strip()
    return items


def extract_authorization(cookie: str) -> str | None:
    value = _cookie_items(cookie).get("authorization")
    return value or None


def extract_account_full(cookie: str) -> str | None:
    items = _cookie_items(cookie)
    encrypted = items.get("ORCHES-I-ACCOUNT-ENCRYPT")
    if encrypted:
        try:
            decoded = base64.b64decode(encrypted).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            decoded = ""
        if decoded:
            return decoded
    auth = extract_authorization(cookie)
    if auth:
        try:
            raw = auth.removeprefix("Basic").strip()
            decoded = base64.b64decode(raw).decode("utf-8", "ignore")
            parts = decoded.split(":")
            if len(parts) > 1 and parts[1]:
                return parts[1]
        except Exception:  # noqa: BLE001
            pass
    return items.get("Login_UserNumber") or None


class C139Client(PanClient):
    platform = Platform.C139
    cred_kind = "cookie"
    cred_title = "Cookie"
    cred_help = (
        "推荐：点下方「网页登录」，在弹出的官方页面用移动手机号登录，程序会自动读取并保存凭证。\n\n"
        "手动方式：浏览器登录 https://yun.139.com 后按 F12 → Network → 刷新，"
        "复制整行 Cookie（建议包含 authorization 与 Login_UserNumber）。"
    )

    # -- 凭证 ---------------------------------------------------------------
    def check_credential(self, credential: str) -> str | None:
        cookie = self.require_credential(credential)
        account = extract_account_full(cookie)
        if not account:
            raise ApiError("Cookie 里没有账号信息，请确认已登录 yun.139.com 后复制完整 Cookie")
        authorization = extract_authorization(cookie)
        if authorization:
            if not self._verify_cloud(cookie, authorization):
                raise ApiError("Cookie 已失效，请重新登录 yun.139.com 后复制完整 Cookie")
        else:
            items = _cookie_items(cookie)
            if not (items.get("Os_SSo_Sid") and items.get("RMKEY")):
                raise ApiError(
                    "Cookie 缺少 authorization（或 Os_SSo_Sid + RMKEY），请重新复制完整 Cookie"
                )
        return account

    def _verify_cloud(self, cookie: str, authorization: str) -> bool:
        """调用个人云盘列表接口验证登录态。"""
        body = json.dumps(
            {
                "pageInfo": {"pageSize": 1, "pageCursor": None},
                "orderBy": "updated_at",
                "orderDirection": "DESC",
                "parentFileId": "root",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        headers = {
            "Authorization": authorization,
            "mcloud-sign": sign_header(body),
            "x-yun-channel-source": YUN_CHANNEL_SOURCE,
            "x-yun-app-channel": YUN_CHANNEL_SOURCE,
            "x-huawei-channelSrc": YUN_CHANNEL_SOURCE,
            "mcloud-version": MCLOUD_VERSION,
            "mcloud-client": MCLOUD_CLIENT,
            "mcloud-channel": MCLOUD_CHANNEL,
            "mcloud-route": "001",
            "x-yun-module-type": "100",
            "x-yun-api-version": "v1",
            "x-yun-svc-type": "1",
            "x-SvcType": "1",
            "caller": "web",
            "x-inner-ntwk": "2",
            "CMS-DEVICE": "default",
            "x-m4c-src": "10002",
            "x-m4c-caller": "PC",
            "X-Deviceinfo": X_DEVICEINFO,
            "x-yun-client-info": X_CLIENT_INFO,
            "INNER-HCY-ROUTER-HTTPS": "1",
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": PC_UA,
            "Origin": "https://yun.139.com",
            "Referer": "https://yun.139.com/",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie,
        }
        try:
            resp = api_request("POST", FILE_LIST_URL, headers=headers, data=body)
            payload = resp.json()
        except Exception:  # noqa: BLE001
            return False
        code = str(payload.get("code") or "")
        return bool(payload.get("success")) and code in ("0", "0000")

    # -- 底层请求 -----------------------------------------------------------
    def _share_post(self, url: str, plain_body: str, authorization: str | None = None) -> dict:
        headers = {
            "hcy-cool-flag": "1",
            "x-deviceinfo": SHARE_X_DEVICEINFO,
            "x-huawei-channelsrc": SHARE_X_HUAWEI_CHANNELSRC,
            "x-mm-source": SHARE_X_MM_SOURCE,
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": SHARE_MOBILE_UA,
            "Origin": "https://yun.139.com",
            "Referer": "https://yun.139.com/",
            "Accept": "application/json, text/plain, */*",
        }
        if authorization:
            headers["Authorization"] = authorization
            headers["mcloud-sign"] = sign_header(plain_body)
        resp = api_request("POST", url, headers=headers, data=encrypt_body(plain_body))
        text = resp.text or ""
        try:
            return json.loads(decrypt_body(text))
        except Exception:  # noqa: BLE001
            try:
                return json.loads(text)
            except ValueError:
                raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")

    @staticmethod
    def _check(payload: dict, fallback: str) -> None:
        code = payload.get("resultCode")
        if code not in (None, "", "0"):
            raise ApiError(payload.get("desc") or f"{fallback}（{code}）")
        if payload.get("success") is False:
            raise ApiError(payload.get("desc") or fallback)

    # -- 分享解析 -----------------------------------------------------------
    def _general(self, link_id: str) -> dict:
        body = json.dumps(
            {"getOutLinkGeneralReq": {"linkID": link_id, "isPasswd": 1, "account": ""}},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        payload = self._share_post(SHARE_GENERAL_URL, body)
        try:
            self._check(payload, "获取分享信息失败")
        except ApiError:
            return {}
        items = (
            ((payload.get("data") or {}).get("getOutLinkGeneralResp") or {}).get("outLinkGeneral")
            or []
        )
        return items[0] if items else {}

    def open_session(self, link: str, pwd: str | None, credential: str) -> ShareSession:
        cookie = self.require_credential(credential)
        if not extract_account_full(cookie):
            raise ApiError("登录态缺少账号信息，请重新复制 Cookie")
        parsed = parse_share(link)
        if parsed is None:
            raise ApiError("无法识别 139 分享链接")
        info = self._general(parsed.share_id)
        passwd = (pwd or "").strip() or (parsed.pwd or "") or (info.get("passwd") or "")
        title = info.get("lkName") or parsed.share_id
        return ShareSession(share_id=parsed.share_id, token=passwd, title=title)

    def list_files(self, session: ShareSession, dir_id: str, credential: str) -> list[PanFile]:
        pca_id = "root" if dir_id in ("", "0", None) else dir_id
        files: list[PanFile] = []
        for begin in range(1, 20000, 200):
            body = json.dumps(
                {
                    "getOutLinkInfoReq": {
                        "account": "",
                        "linkID": session.share_id,
                        "passwd": session.token,
                        "caSrt": 1,
                        "coSrt": 1,
                        "srtDr": 0,
                        "bNum": begin,
                        "pCaID": pca_id,
                        "eNum": begin + 199,
                    }
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
            payload = self._share_post(SHARE_LIST_URL, body)
            self._check(payload, "获取文件列表失败")
            data = payload.get("data") or {}
            batch: list[PanFile] = []
            for item in data.get("caLst") or []:
                batch.append(
                    PanFile(
                        fid=item.get("caID") or "",
                        name=item.get("caName") or "",
                        size=0,
                        is_dir=True,
                        parent_fid=pca_id,
                        modify_time=str(item.get("udTime") or item.get("ctTime") or ""),
                    )
                )
            for item in data.get("coLst") or []:
                is_dir = bool(item.get("isdir")) or int(item.get("coType") or 1) == 2
                batch.append(
                    PanFile(
                        fid=item.get("coID") or "",
                        name=item.get("coName") or "",
                        size=int(item.get("coSize") or 0),
                        is_dir=is_dir,
                        parent_fid=pca_id,
                        modify_time=str(item.get("udTime") or item.get("ctTime") or ""),
                    )
                )
            files.extend(batch)
            if len(batch) < 200:
                break
        return files

    # -- 取链 ---------------------------------------------------------------
    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        cookie = self.require_credential(credential)
        account = extract_account_full(cookie)
        if not account:
            raise ApiError("登录态缺少账号信息，请重新复制 Cookie")
        authorization = extract_authorization(cookie)
        body = json.dumps(
            {
                "dlFromOutLinkReqV3": {
                    "account": account,
                    "linkID": session.share_id,
                    "coIDLst": {"item": [file.fid]},
                    "commonAccountInfo": {"account": account, "accountType": 1},
                }
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        self._log(log, "  获取下载直链…")
        payload = self._share_post(SHARE_LINK_URL, body, authorization)
        self._check(payload, "获取下载链接失败")
        data = payload.get("data") or {}
        url = data.get("redrUrl") or ""
        if not url:
            raise ApiError("未返回下载链接")
        return DownloadLink(
            url=url,
            filename=file.name,
            size=int(data.get("coSize") or data.get("size") or file.size),
        )

    def download_headers(self, credential: str) -> dict[str, str]:
        return {"User-Agent": PC_UA}
