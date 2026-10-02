"""百度网盘（verify → xpan/share 列目录 → 转存 → locatedownload 高速直链）。"""

from __future__ import annotations

import time
import urllib.parse

from ..link_parser import parse_share
from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession
from ..net import api_request, ensure_cookie
from .base import Logger, PanClient

APP_ID = "250528"
UA_WEB = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
UA_NETDISK = "netdisk;12.24.6;piano;android-android;16;JSbridge4.4.0;jointBridge;1.1.0"
TEMP_DIR = "/亦析临时转存"


class BaiduClient(PanClient):
    platform = Platform.BAIDU
    cred_kind = "cookie"
    cred_title = "Cookie"
    cred_help = (
        "推荐：点下方「网页登录」，在弹出的官方页面登录，程序会自动读取并保存凭证。\n\n"
        "手动方式：浏览器登录 https://pan.baidu.com 后按 F12 → Network → 刷新页面，"
        "复制整行 Cookie（必须包含 BDUSS=）。"
    )

    def __init__(self) -> None:
        super().__init__()
        self._bdstoken: str | None = None

    # -- 通用请求 -----------------------------------------------------------
    def _json(self, method: str, url: str, cookie: str, *, headers=None, data=None, params=None) -> dict:
        base_headers = {"Cookie": cookie, "User-Agent": UA_WEB}
        if headers:
            base_headers.update(headers)
        resp = api_request(method, url, headers=base_headers, data=data, params=params)
        try:
            payload = resp.json()
        except ValueError:
            raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")
        return payload

    @staticmethod
    def _check(payload: dict, fallback: str) -> None:
        errno = int(payload.get("errno") or 0)
        if errno != 0:
            msg = (
                payload.get("err_msg")
                or payload.get("show_msg")
                or payload.get("error_msg")
                or fallback
            )
            raise ApiError(f"{msg}（errno={errno}）")

    def _template_variable(self, cookie: str, fields: str):
        payload = self._json(
            "GET",
            "https://pan.baidu.com/api/gettemplatevariable",
            cookie,
            params={
                "clienttype": "0",
                "app_id": APP_ID,
                "web": "1",
                "fields": fields,
            },
        )
        if int(payload.get("errno") or 0) != 0:
            return None
        return payload.get("result") or {}

    def _bdstoken_of(self, cookie: str) -> str:
        if self._bdstoken:
            return self._bdstoken
        result = self._template_variable(cookie, '["bdstoken"]')
        token = (result or {}).get("bdstoken")
        if not token:
            raise ApiError("获取 bdstoken 失败，请检查 Cookie 是否有效")
        self._bdstoken = token
        return token

    # -- 凭证 ---------------------------------------------------------------
    def check_credential(self, credential: str) -> str | None:
        cookie = self.require_credential(credential)
        if "BDUSS=" not in cookie:
            raise ApiError("Cookie 缺少 BDUSS，请重新复制完整 Cookie")
        result = self._template_variable(cookie, '["username","bdstoken"]')
        if not result:
            raise ApiError("Cookie 无效或已过期")
        token = result.get("bdstoken")
        if token:
            self._bdstoken = token
        return result.get("username")

    # -- 分享解析 -----------------------------------------------------------
    def open_session(self, link: str, pwd: str | None, credential: str) -> ShareSession:
        cookie = self.require_credential(credential)
        parsed = parse_share(link)
        if parsed is None:
            raise ApiError("无法识别百度分享链接")
        surl = parsed.share_id
        passcode = (pwd or "").strip() or (parsed.pwd or "")
        sekey = ""
        if passcode:
            payload = self._json(
                "POST",
                f"https://pan.baidu.com/share/verify?surl={urllib.parse.quote(surl)}",
                cookie,
                headers={
                    "Referer": f"https://pan.baidu.com/s/{surl}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"pwd": passcode, "vcode_str": "", "vcode": ""},
            )
            self._check(payload, "验证提取码失败")
            sekey = payload.get("randsk") or ""
            if not sekey:
                raise ApiError("未返回分享密钥")
        return ShareSession(share_id=surl, token=sekey, extra={"passcode": passcode})

    def list_files(self, session: ShareSession, dir_id: str, credential: str) -> list[PanFile]:
        cookie = self.require_credential(credential)
        surl = session.share_id
        directory = "/" if dir_id in ("", "0", None) else dir_id
        is_root = directory in ("", "/")
        sekey = session.token
        auth_cookie = cookie
        if sekey:
            auth_cookie = ensure_cookie(cookie, "BDCLND", sekey)
        files: list[PanFile] = []
        for page in range(1, 101):
            params = {
                "method": "list",
                "shorturl": surl,
                "page": str(page),
                "num": "100",
                "root": "1" if is_root else "0",
                "dir": "/" if is_root else directory,
            }
            if sekey:
                params["sekey"] = sekey
            payload = self._json(
                "GET",
                "https://pan.baidu.com/rest/2.0/xpan/share",
                auth_cookie,
                params=params,
                headers={"Referer": f"https://pan.baidu.com/s/{surl}"},
            )
            errno = int(payload.get("errno") or 0)
            if errno != 0:
                if not sekey:
                    raise ApiError("该分享需要提取码")
                self._check(payload, "获取分享文件列表失败")
            session.extra["share_id"] = payload.get("share_id") or session.extra.get("share_id", "")
            session.extra["uk"] = payload.get("uk") or session.extra.get("uk", "")
            batch = []
            for item in payload.get("list") or []:
                is_dir = str(item.get("isdir")) == "1"
                path = item.get("path") or ""
                batch.append(
                    PanFile(
                        fid=path if is_dir else str(item.get("fs_id") or ""),
                        name=item.get("server_filename") or "",
                        size=int(item.get("size") or 0),
                        is_dir=is_dir,
                        parent_fid=path,
                        modify_time=str(item.get("server_mtime") or ""),
                    )
                )
            files.extend(batch)
            if len(batch) < 100:
                break
        return files

    # -- 个人网盘 -----------------------------------------------------------
    def _list_dir(self, directory: str, cookie: str) -> list[str]:
        try:
            payload = self._json(
                "GET",
                "https://yun.baidu.com/api/list",
                cookie,
                params={
                    "clienttype": "0",
                    "app_id": APP_ID,
                    "web": "1",
                    "order": "time",
                    "desc": "1",
                    "dir": directory,
                    "num": "100",
                    "page": "1",
                },
                headers={"User-Agent": UA_NETDISK},
            )
        except Exception:  # noqa: BLE001
            return []
        if int(payload.get("errno") or 0) != 0:
            return []
        return [item.get("path") for item in payload.get("list") or []]

    def _ensure_temp_dir(self, cookie: str) -> str:
        if TEMP_DIR in self._list_dir("/", cookie):
            return TEMP_DIR
        bdstoken = self._bdstoken_of(cookie)
        payload = self._json(
            "POST",
            "https://pan.baidu.com/api/create",
            cookie,
            params={
                "a": "commit",
                "channel": "chunlei",
                "web": "1",
                "app_id": APP_ID,
                "clienttype": "0",
                "bdstoken": bdstoken,
            },
            headers={
                "User-Agent": UA_NETDISK,
                "Referer": "https://yun.baidu.com/disk/main",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            data={"path": TEMP_DIR, "isdir": "1", "size": "", "block_list": "[]",
                  "method": "post", "dataType": "json"},
        )
        if int(payload.get("errno") or 0) == 0:
            return TEMP_DIR
        return "/"

    def _transfer(self, session: ShareSession, file: PanFile, to_dir: str, cookie: str) -> tuple[str, str]:
        bdstoken = self._bdstoken_of(cookie)
        share_id = session.extra.get("share_id") or ""
        uk = session.extra.get("uk") or ""
        if not share_id or not uk:
            raise ApiError("分享信息不完整，请重新解析")
        auth_cookie = ensure_cookie(cookie, "BDCLND", session.token)
        payload = self._json(
            "POST",
            "https://pan.baidu.com/share/transfer",
            auth_cookie,
            params={
                "shareid": share_id,
                "from": uk,
                "channel": "chunlei",
                "sekey": session.token,
                "ondup": "newcopy",
                "web": "1",
                "app_id": APP_ID,
                "bdstoken": bdstoken,
                "clienttype": "0",
            },
            headers={
                "Origin": "https://pan.baidu.com",
                "Referer": "https://pan.baidu.com/s/",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            data={"fsidlist": f'["{file.fid}"]', "path": to_dir},
        )
        self._check(payload, "转存失败")
        extra = payload.get("extra") or {}
        items = extra.get("list") or []
        if not items:
            raise ApiError("转存失败：未返回新文件")
        new_id = str(items[0].get("to_fs_id") or "")
        new_path = items[0].get("to") or f"{to_dir}/"
        if not new_id:
            raise ApiError("转存失败：未返回新文件标识")
        return new_id, new_path

    def _locate_download(self, path: str, cookie: str) -> str:
        ts = int(time.time())
        params = {
            "method": "locatedownload",
            "app_id": APP_ID,
            "clienttype": "17",
            "ver": "4.0",
            "ant": "1",
            "check_blue": "1",
            "es": "1",
            "esl": "1",
            "apn_id": "1_-1",
            "freeisp": "0",
            "queryfree": "0",
            "use": "1",
            "dtype": "1",
            "eck": "1",
            "ehps": "1",
            "err_ver": "1.0",
            "network_type": "WIFI",
            "channel": "0",
            "path": path,
            "time": str(ts),
            "rand": "5ed606e9da222cde0474cdf70eda884b",
            "devuid": "0F1E9FC2E084472DA5A61C4CF4C759AF",
            "cuid": "0F1E9FC2E084472DA5A61C4CF4C759AF",
            "deviceid": "348642637967375013",
            "psign": "860a071f77c860e8cea06e4e54c518f3",
            "version": "2.2.111.34",
            "version_app": "12.24.6",
            "vip": "0",
        }
        payload = self._json(
            "POST",
            "https://d.pcs.baidu.com/rest/2.0/pcs/file",
            cookie,
            params=params,
            headers={
                "User-Agent": UA_NETDISK,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="0",
        )
        self._check(payload, "获取高速下载链接失败")
        candidates = [
            item for item in (payload.get("urls") or []) if item.get("url")
        ]
        if not candidates:
            raise ApiError("未返回下载链接")
        plain = [c for c in candidates if int(c.get("encrypt", 1)) == 0]
        plain.sort(key=lambda c: not str(c.get("url", "")).startswith("https"))
        if plain:
            return plain[0]["url"]
        https = [c for c in candidates if str(c.get("url", "")).startswith("https")]
        return (https or candidates)[0]["url"]

    def _delete_path(self, path: str, cookie: str) -> bool:
        try:
            bdstoken = self._bdstoken_of(cookie)
        except ApiError:
            return False
        try:
            payload = self._json(
                "POST",
                "https://pan.baidu.com/api/filemanager",
                cookie,
                params={
                    "async": "2",
                    "onnest": "fail",
                    "opera": "delete",
                    "bdstoken": bdstoken,
                    "newVerify": "1",
                    "clienttype": "0",
                    "app_id": APP_ID,
                    "web": "1",
                },
                headers={
                    "User-Agent": UA_NETDISK,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                data={"filelist": f'["{path}"]'},
            )
        except Exception:  # noqa: BLE001
            return False
        return int(payload.get("errno") or 0) == 0

    # -- 取链 ---------------------------------------------------------------
    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        cookie = self.require_credential(credential)
        self._log(log, "  转存到临时目录…")
        temp_dir = self._ensure_temp_dir(cookie)
        _, new_path = self._transfer(session, file, temp_dir, cookie)
        self._log(log, "  获取高速下载直链…")
        url = self._locate_download(new_path, cookie)
        # appall 直链自带签名，取链后即可删除转存残留
        self._delete_path(new_path, cookie)
        if new_path.startswith(TEMP_DIR + "/"):
            self._delete_path(TEMP_DIR, cookie)
        return DownloadLink(url=url, filename=file.name, size=file.size)

    def download_headers(self, credential: str) -> dict[str, str]:
        return {
            "Cookie": (credential or "").strip(),
            "User-Agent": UA_NETDISK,
        }
