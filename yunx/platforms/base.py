"""平台客户端基类。"""

from __future__ import annotations

from typing import Callable

from ..models import ApiError, DownloadLink, PanFile, Platform, ShareSession

Logger = Callable[[str], None]


class PanClient:
    """所有网盘客户端的统一接口。"""

    platform: Platform
    #: 凭证类型：cookie / token
    cred_kind: str = "cookie"
    #: 界面里显示的凭证名称
    cred_title: str = "Cookie"
    #: 获取凭证的说明
    cred_help: str = ""
    #: 构造直链下载请求时要带的请求头说明（在 download_headers 中实现）

    def __init__(self) -> None:
        #: 会话期间被服务端刷新过的凭证（如有，由界面回写配置）
        self.refreshed_credential: str | None = None

    # -- 凭证 ---------------------------------------------------------------
    def check_credential(self, credential: str) -> str | None:
        """校验凭证，成功时返回昵称（可为 None）。"""
        return None

    def require_credential(self, credential: str) -> str:
        if not credential or not credential.strip():
            raise ApiError(
                f"请先到右上角「账号与凭证」填写 {self.platform.label} 的 {self.cred_title}"
            )
        return credential.strip()

    # -- 解析 ---------------------------------------------------------------
    def open_session(self, link: str, pwd: str | None, credential: str) -> ShareSession:
        raise NotImplementedError

    def list_files(self, session: ShareSession, dir_id: str, credential: str) -> list[PanFile]:
        raise NotImplementedError

    def fetch_download(
        self,
        session: ShareSession,
        file: PanFile,
        credential: str,
        log: Logger | None = None,
    ) -> DownloadLink:
        raise NotImplementedError

    # -- 下载 ---------------------------------------------------------------
    def download_headers(self, credential: str) -> dict[str, str]:
        return {}

    def cleanup(self, session: ShareSession | None, link: DownloadLink, credential: str) -> None:
        """下载完成后清理临时转存（默认无操作）。"""
        return None

    # -- 工具 ---------------------------------------------------------------
    def _log(self, log: Logger | None, message: str) -> None:
        if log is not None:
            try:
                log(message)
            except Exception:
                pass
