"""UC 网盘（分享直链无需转存；OSS 直链必须带 Referer 才满速）。"""

from __future__ import annotations

import urllib.parse

from ..link_parser import parse_share
from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession
from ..net import api_request, drop_puus, merge_set_cookies, set_cookies
from .base import Logger, PanClient

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
API_BASE = "https://pc-api.uc.cn"
WEB_ORIGIN = "https://drive.uc.cn"
DOWNLOAD_REFERER = WEB_ORIGIN + "/"

VIDEO_EXTS = {"mp4", "mkv", "mov", "avi", "webm", "flv", "ts", "m3u8", "wmv", "rmvb"}


class UCClient(PanClient):
    platform = Platform.UC
    cred_kind = "cookie"
    cred_title = "Cookie"
    cred_help = (
        "推荐：点下方「网页登录」，在弹出的官方页面登录，程序会自动读取并保存凭证。\n\n"
        "手动方式：浏览器登录 https://drive.uc.cn 后按 F12 → Network → 刷新页面，"
        "复制 Request Headers 里整行 Cookie 值（需含 __pus、__puus）。"
    )

    def check_credential(self, credential: str) -> str | None:
        cookie = self.require_credential(credential)
        resp = api_request(
            "GET",
            "https://drive.uc.cn/account/info",
            headers={"Cookie": cookie, "User-Agent": UA},
        )
        try:
            data = resp.json()
        except ValueError:
            raise ApiError("账号校验失败：返回内容异常")
        merged = merge_set_cookies(cookie, set_cookies(resp))
        if merged != cookie:
            self.refreshed_credential = merged
        payload = data.get("data")
        # 未登录时 UC 同样返回 success:true + 空 data，必须要求 data 非空
        if data.get("success") and isinstance(payload, dict) and payload:
            return payload.get("nickname") or payload.get("user_name") or "已登录"
        raise ApiError("Cookie 无效或已过期，请重新获取")

    # -- 内部请求 -----------------------------------------------------------
    def _headers(self, cookie: str, json_body: bool = False) -> dict[str, str]:
        headers = {
            "Cookie": cookie,
            "User-Agent": UA,
            "Origin": WEB_ORIGIN,
            "Referer": DOWNLOAD_REFERER,
        }
        if json_body:
            headers["Content-Type"] = "application/json;charset=UTF-8"
        return headers

    def _request(
        self, method: str, url: str, cookie: str, body: dict | None = None, headers: dict | None = None
    ) -> dict:
        resp = api_request(
            method,
            url,
            headers=headers or self._headers(cookie, json_body=body is not None),
            json=body,
        )
        merged = merge_set_cookies(cookie, set_cookies(resp))
        if merged != cookie:
            self.refreshed_credential = merged
        try:
            data = resp.json()
        except ValueError:
            raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")
        status = int(data.get("status", 0))
        code = data.get("code")
        ok = status == 200 or code == 0
        if not ok:
            raise ApiError(data.get("message") or "请求失败")
        return data

    def refresh_session(self, cookie: str) -> str:
        try:
            resp = api_request(
                "GET",
                f"{API_BASE}/1/clouddrive/config?pr=UCBrowser&fr=pc",
                headers={"Cookie": drop_puus(cookie), "User-Agent": UA, "Referer": DOWNLOAD_REFERER},
            )
        except Exception:  # noqa: BLE001
            return cookie
        merged = merge_set_cookies(cookie, set_cookies(resp))
        if merged != cookie:
            self.refreshed_credential = merged
        return merged

    # -- 分享解析 -----------------------------------------------------------
    def open_session(self, link: str, pwd: str | None, credential: str) -> ShareSession:
        cookie = self.require_credential(credential)
        parsed = parse_share(link)
        if parsed is None:
            raise ApiError("无法识别 UC 分享链接")
        passcode = (pwd or "").strip() or (parsed.pwd or "")
        data = self._request(
            "POST",
            f"{API_BASE}/1/clouddrive/share/sharepage/token?pr=UCBrowser&fr=pc",
            cookie,
            {"pwd_id": parsed.share_id, "passcode": passcode, "share_for_transfer": True},
        )
        payload = data.get("data") or {}
        stoken = payload.get("stoken")
        if not stoken:
            raise ApiError("未获取到分享凭证")
        return ShareSession(
            share_id=parsed.share_id,
            token=stoken,
            title=payload.get("title") or "",
            extra={"passcode": passcode},
        )

    def list_files(self, session: ShareSession, dir_id: str, credential: str) -> list[PanFile]:
        cookie = self.require_credential(credential)
        pdir = dir_id or "0"
        files: list[PanFile] = []
        for page in range(1, 101):
            query = urllib.parse.urlencode(
                {
                    "entry": "ft",
                    "fr": "pc",
                    "pr": "UCBrowser",
                    "pwd_id": session.share_id,
                    "pdir_fid": pdir,
                    "fetch_file_list": "1",
                    "passcode": "",
                    "_page": str(page),
                    "_size": "50",
                    "_fetch_total": "1",
                    "_fetch_task": "1",
                    "_fetch_share": "1",
                    "_sort": "",
                    "stoken": session.token,
                }
            )
            data = self._request(
                "GET",
                f"{API_BASE}/1/clouddrive/transfer_share/detail?{query}",
                cookie,
                headers={
                    "Cookie": cookie,
                    "User-Agent": UA,
                    "Origin": "https://fast.uc.cn",
                    "Referer": "https://fast.uc.cn/",
                },
            )
            payload = data.get("data") or {}
            raw = payload.get("list") or (payload.get("detail_info") or {}).get("list") or []
            batch = [
                PanFile(
                    fid=item.get("fid", ""),
                    name=item.get("file_name", ""),
                    size=int(item.get("size") or 0),
                    is_dir=bool(item.get("dir")),
                    parent_fid=item.get("pdir_fid", ""),
                    fid_token=item.get("share_fid_token", ""),
                    modify_time=str(item.get("updated_at") or ""),
                )
                for item in raw
            ]
            files.extend(batch)
            if len(batch) < 50:
                break
        return files

    # -- 取链 ---------------------------------------------------------------
    def _video_preview(self, session: ShareSession, item: PanFile, cookie: str) -> DownloadLink | None:
        query = urllib.parse.urlencode(
            {
                "pr": "UCBrowser",
                "fr": "h5",
                "pwd_id": session.share_id,
                "stoken": session.token,
                "fid": item.fid,
                "fid_token": item.fid_token,
            }
        )
        try:
            data = self._request(
                "GET",
                f"{API_BASE}/1/clouddrive/share/sharepage/video_preview?{query}",
                cookie,
                headers={
                    "Cookie": cookie,
                    "User-Agent": UA,
                    "Origin": WEB_ORIGIN,
                    "Referer": DOWNLOAD_REFERER,
                    "Content-Type": "application/json",
                },
            )
        except Exception:  # noqa: BLE001
            return None
        play = ((data.get("data") or {}).get("play_info")) or {}
        url = play.get("url")
        if not url:
            return None
        return DownloadLink(
            url=url,
            filename=item.name,
            size=int(play.get("size") or item.size),
        )

    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        cookie = self.refreshed_credential or self.require_credential(credential)
        ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
        if ext in VIDEO_EXTS:
            self._log(log, "  尝试获取原画直链…")
            preview = self._video_preview(session, file, cookie)
            if preview is not None:
                return preview
        self._log(log, "  获取下载直链…")
        data = self._request(
            "POST",
            f"{API_BASE}/1/clouddrive/file/download?entry=ft&fr=pc&pr=UCBrowser",
            cookie,
            {
                "fids": [file.fid],
                "pwd_id": session.share_id,
                "stoken": session.token,
                "fids_token": [file.fid_token],
            },
        )
        items = data.get("data") or []
        if not items:
            raise ApiError("未返回下载直链")
        return DownloadLink(
            url=items[0].get("download_url", ""),
            filename=items[0].get("file_name") or file.name,
            size=int(items[0].get("size") or file.size),
        )

    def download_headers(self, credential: str) -> dict[str, str]:
        return {
            "Cookie": (self.refreshed_credential or credential or "").strip(),
            "User-Agent": UA,
            "Referer": DOWNLOAD_REFERER,
            "Origin": WEB_ORIGIN,
        }

