"""公共数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Platform(str, Enum):
    """支持的网盘平台。"""

    QUARK = "quark"
    UC = "uc"
    XUNLEI = "xunlei"
    BAIDU = "baidu"
    C139 = "c139"
    PAN123 = "pan123"

    @property
    def label(self) -> str:
        return PLATFORM_LABELS[self]


PLATFORM_LABELS = {
    Platform.QUARK: "夸克网盘",
    Platform.UC: "UC 网盘",
    Platform.XUNLEI: "迅雷网盘",
    Platform.BAIDU: "百度网盘",
    Platform.C139: "移动云盘(139)",
    Platform.PAN123: "123 云盘",
}


@dataclass
class ParsedShare:
    """从分享链接/文案中提取出的解析结果。"""

    share_id: str
    pwd: str | None
    platform: Platform


@dataclass
class PanFile:
    """网盘中的文件或目录。"""

    fid: str
    name: str
    size: int = 0
    is_dir: bool = False
    parent_fid: str = ""
    fid_token: str = ""
    modify_time: str = ""

    @property
    def kind_text(self) -> str:
        return "文件夹" if self.is_dir else "文件"


@dataclass
class ShareSession:
    """一次分享解析会话（平台各自解释 token 的含义）。"""

    share_id: str
    token: str = ""
    title: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class DownloadLink:
    """最终可直接下载的直链及其清理信息。"""

    url: str
    filename: str = ""
    size: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    #: 取链过程中在用户网盘里产生的临时目录（下载完成后清理）
    cleanup_dir_fid: str | None = None
    #: 临时目录清理需要带的凭证
    cleanup_credential: str = ""
    #: 临时转存出来的文件 id（部分平台需要单独删除）
    cleanup_file_ids: list[str] = field(default_factory=list)
    #: 是否 HLS（m3u8）流，需要分片下载
    is_hls: bool = False


class ApiError(Exception):
    """平台接口返回的业务错误（消息面向用户）。"""


class NeedCredentialError(ApiError):
    """缺少/失效的登录凭证。"""
