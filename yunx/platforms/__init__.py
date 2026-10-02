"""各网盘平台的解析与取链实现。"""

from __future__ import annotations

from ..models import Platform
from .base import PanClient
from .baidu import BaiduClient
from .c139 import C139Client
from .pan123 import Pan123Client
from .quark import QuarkClient
from .uc import UCClient
from .xunlei import XunleiClient

_CLIENTS: dict[Platform, PanClient] = {
    Platform.QUARK: QuarkClient(),
    Platform.UC: UCClient(),
    Platform.BAIDU: BaiduClient(),
    Platform.PAN123: Pan123Client(),
    Platform.C139: C139Client(),
    Platform.XUNLEI: XunleiClient(),
}


def get_client(platform: Platform) -> PanClient:
    return _CLIENTS[platform]


def all_clients() -> dict[Platform, PanClient]:
    return dict(_CLIENTS)


__all__ = ["PanClient", "get_client", "all_clients"]
