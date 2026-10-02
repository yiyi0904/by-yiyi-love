"""夸克网盘（含 Web 端 Cookie 认证、分享解析、转存取链）。"""

from __future__ import annotations

import time
import urllib.parse

from ..link_parser import parse_share
from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession
from ..net import api_request, drop_puus, merge_set_cookies, set_cookies
from .base import Logger, PanClient

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.12-a038f7b798 "
    "Safari/537.36 Channel/pckk_other_ch"
)
WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 QuarkPC/6.0.8.649"
)
BASE = "https://drive-pc.quark.cn"
REFERER = "https://pan.quark.cn/"
ORIGIN = "https://pan.quark.cn"
TEMP_DIR_NAME = "亦析临时转存"


def _api_url(path: str) -> str:
    return f"{BASE}{path}"


class QuarkClient(PanClient):
    platform = Platform.QUARK
    cred_kind = "cookie"
    cred_title = "Cookie"
    cred_help = (
        "推荐：点下方「网页登录」，在弹出的官方页面登录，程序会自动读取并保存凭证。\n\n"
        "手动方式：浏览器登录 https://pan.quark.cn 后按 F12 → Network → 刷新页面 → "
        "点任意请求，复制 Request Headers 里整行 Cookie 值粘贴到这里。"
    )

    # -- 凭证 ---------------------------------------------------------------
    def check_credential(self, credential: str) -> str | None:
        cookie = self.require_credential(credential)
        resp = api_request(
            "GET",
            "https://pan.quark.cn/account/info",
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
        # 注意：未登录时该接口同样返回 success:true，但 data 是空对象，
        # 必须要求 data 非空，否则会把匿名会话误判成登录成功。
        if data.get("success") and isinstance(payload, dict) and payload:
            return payload.get("nickname") or payload.get("user_name") or "已登录"
        raise ApiError("Cookie 无效或已过期，请重新获取")

    # -- 内部请求 -----------------------------------------------------------
    def _post_json(self, url: str, cookie: str, body: dict, timeout=(15, 60)) -> dict:
        resp = api_request(
            "POST",
            url,
            headers={
                "Cookie": cookie,
                "User-Agent": UA,
                "Content-Type": "application/json",
                "Origin": ORIGIN,
                "Referer": REFERER,
            },
            json=body,
            timeout=timeout,
        )
        merged = merge_set_cookies(cookie, set_cookies(resp))
        if merged != cookie:
            self.refreshed_credential = merged
        try:
            data = resp.json()
        except ValueError:
            raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")
        if int(data.get("status", 0)) != 200:
            raise ApiError(data.get("message") or "请求失败")
        return data

    def _get_json(self, url: str, cookie: str, timeout=(15, 60)) -> dict:
        resp = api_request(
            "GET",
            url,
            headers={
                "Cookie": cookie,
                "User-Agent": UA,
                "Origin": ORIGIN,
                "Referer": REFERER,
            },
            timeout=timeout,
        )
        merged = merge_set_cookies(cookie, set_cookies(resp))
        if merged != cookie:
            self.refreshed_credential = merged
        try:
            data = resp.json()
        except ValueError:
            raise ApiError(f"接口返回异常（HTTP {resp.status_code}）")
        if int(data.get("status", 0)) != 200:
            raise ApiError(data.get("message") or "请求失败")
        return data

    def refresh_session(self, cookie: str) -> str:
        """剥离 __puus 后请求 /config，让服务端重新下发（对齐 AList refreshPuus）。"""
        try:
            resp = api_request(
                "GET",
                _api_url("/1/clouddrive/config?pr=ucpro&fr=pc"),
                headers={
                    "Cookie": drop_puus(cookie),
                    "User-Agent": UA,
                    "Referer": REFERER,
                },
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
            raise ApiError("无法识别夸克分享链接")
        passcode = (pwd or "").strip() or (parsed.pwd or "")
        data = self._post_json(
            _api_url("/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"),
            cookie,
            {
                "pwd_id": parsed.share_id,
                "passcode": passcode,
                "support_visit_limit_private_share": True,
            },
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
                    "pr": "ucpro",
                    "fr": "pc",
                    "pwd_id": session.share_id,
                    "stoken": session.token,
                    "pdir_fid": pdir,
                    "ver": "2",
                    "force": "0",
                    "_page": str(page),
                    "_size": "100",
                    "_fetch_banner": "0",
                    "_fetch_share": "0",
                    "fetch_relate_conversation": "0",
                    "_fetch_total": "1",
                    "_sort": "file_type:asc,file_name:asc",
                }
            )
            data = self._get_json(
                _api_url("/1/clouddrive/share/sharepage/detail?") + query, cookie
            )
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
                for item in (data.get("data") or {}).get("list") or []
            ]
            files.extend(batch)
            if len(batch) < 100:
                break
        return files

    # -- 个人网盘 / 转存 -----------------------------------------------------
    def _list_cloud(self, pdir_fid: str, cookie: str) -> list[PanFile]:
        query = urllib.parse.urlencode(
            {
                "pr": "ucpro",
                "fr": "pc",
                "pdir_fid": pdir_fid,
                "page": "1",
                "size": "100",
            }
        )
        data = self._get_json(_api_url("/1/clouddrive/file?") + query, cookie)
        return [
            PanFile(
                fid=item.get("fid", ""),
                name=item.get("file_name") or item.get("fname", ""),
                size=int(item.get("size") or 0),
                is_dir=bool(item.get("dir")),
            )
            for item in (data.get("data") or {}).get("list") or []
        ]

    def _create_folder(self, name: str, parent_fid: str, cookie: str) -> str:
        data = self._post_json(
            _api_url("/1/clouddrive/file?pr=ucpro&fr=pc"),
            cookie,
            {
                "pdir_fid": parent_fid,
                "file_name": name,
                "dir_path": "",
                "dir_init_lock": False,
            },
        )
        fid = (data.get("data") or {}).get("fid")
        if not fid:
            raise ApiError("创建临时目录失败")
        return fid

    def _ensure_temp_dir(self, cookie: str) -> str:
        for item in self._list_cloud("0", cookie):
            if item.is_dir and item.name == TEMP_DIR_NAME:
                return item.fid
        return self._create_folder(TEMP_DIR_NAME, "0", cookie)

    def _save_share(
        self, session: ShareSession, item: PanFile, to_pdir: str, cookie: str
    ) -> str:
        data = self._post_json(
            _api_url("/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"),
            cookie,
            {
                "pwd_id": session.share_id,
                "stoken": session.token,
                "pdir_fid": item.parent_fid or "0",
                "to_pdir_fid": to_pdir,
                "fid_list": [item.fid],
                "fid_token_list": [item.fid_token],
                "scene": "link",
            },
        )
        task_id = (data.get("data") or {}).get("task_id")
        if not task_id:
            raise ApiError("转存失败：未返回任务号")
        return task_id

    def _poll_task(self, task_id: str, cookie: str) -> str:
        # 注意：pr/fr 不能省，否则服务端按未登录访客处理（401 require login [guest]）
        query = urllib.parse.urlencode(
            {"pr": "ucpro", "fr": "pc", "task_id": task_id, "retry_index": 0}
        )
        for _ in range(15):
            data = self._get_json(_api_url("/1/clouddrive/task?") + query, cookie)
            payload = data.get("data") or {}
            finished = (
                int(payload.get("finished_at") or 0) > 0
                or int(payload.get("status") or 0) == 2
                or int(payload.get("task_status") or 0) == 2
            )
            if finished:
                fids = ((payload.get("save_as") or {}).get("save_as_top_fids")) or []
                if fids:
                    return fids[0]
                raise ApiError("转存完成但未返回文件标识")
            time.sleep(1)
        raise ApiError("转存超时，请稍后重试")

    def _download_url(self, fid: str, cookie: str) -> tuple[str, int]:
        data = self._post_json(
            _api_url("/1/clouddrive/file/download?pr=ucpro&fr=pc&sys=win32&ve=3.23.2"),
            cookie,
            {"fids": [fid]},
        )
        items = data.get("data") or []
        if not items:
            raise ApiError("未返回下载直链")
        return items[0].get("download_url", ""), int(items[0].get("size") or 0)

    def _delete(self, fid: str, cookie: str) -> None:
        try:
            self._post_json(
                _api_url("/1/clouddrive/file/delete?pr=ucpro&fr=pc&uc_param_str="),
                cookie,
                {"action_type": 2, "filelist": [fid], "exclude_fids": []},
            )
        except Exception:  # noqa: BLE001
            pass

    # -- 取链 ---------------------------------------------------------------
    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        cookie = self.require_credential(credential)
        if self.refreshed_credential:
            cookie = self.refreshed_credential
        # 优先「直接取链」：不用转存，因此不占网盘空间、也更快。
        try:
            link = self._direct_download(session, file, cookie)
            self._log(log, "  获取下载直链（直连）…")
            return link
        except Exception as exc:  # noqa: BLE001
            self._log(log, f"  直连取链失败（{exc}），改用转存方式…")
        return self._transfer_download(session, file, cookie, log)

    def _direct_download(
        self, session: ShareSession, file: PanFile, cookie: str
    ) -> DownloadLink:
        """用分享 fid + stoken + fid_token 直接取直链（夸克支持，无需转存）。"""
        data = self._post_json(
            _api_url("/1/clouddrive/file/download?pr=ucpro&fr=pc&sys=win32&ve=3.23.2"),
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
        item = items[0]
        url = item.get("download_url") or ""
        if not url:
            raise ApiError("未返回下载直链")
        return DownloadLink(
            url=url,
            filename=item.get("file_name") or file.name,
            size=int(item.get("size") or file.size or 0),
        )

    def _transfer_download(
        self,
        session: ShareSession,
        file: PanFile,
        cookie: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        """回退方案：转存到临时目录再取链（会占用网盘空间）。"""
        self._log(log, "  创建/复用临时转存目录…")
        base_dir = self._ensure_temp_dir(cookie)
        sub_name = f"tr_{int(time.time() * 1000)}_{int(time.time() * 997) % 1000000}"
        sub_dir = self._create_folder(sub_name, base_dir, cookie)
        self._log(log, "  转存分享文件…")
        task_id = self._save_share(session, file, sub_dir, cookie)
        saved_fid = self._poll_task(task_id, cookie)
        self._log(log, "  获取下载直链…")
        url, size = self._download_url(saved_fid, cookie)
        if not url:
            raise ApiError("未返回下载直链")
        return DownloadLink(
            url=url,
            filename=file.name,
            size=size or file.size,
            cleanup_dir_fid=sub_dir,
            cleanup_credential=cookie,
        )

    def download_headers(self, credential: str) -> dict[str, str]:
        return {
            "Cookie": (self.refreshed_credential or credential or "").strip(),
            "User-Agent": UA,
            "Referer": REFERER,
        }

    def cleanup(self, session: ShareSession | None, link: DownloadLink, credential: str) -> None:
        if not link.cleanup_dir_fid:
            return
        cookie = link.cleanup_credential or self.refreshed_credential or credential
        self._delete(link.cleanup_dir_fid, cookie)

