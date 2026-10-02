"""配置持久化（账号凭证、下载参数、界面偏好）。"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from .models import Platform
from .util import app_data_dir, default_download_dir

CONFIG_PATH = os.path.join(app_data_dir(), "config.json")

DEFAULT_THREADS = {
    Platform.QUARK.value: 16,
    Platform.UC.value: 16,
    Platform.XUNLEI.value: 8,
    Platform.BAIDU.value: 16,
    Platform.C139.value: 16,
    Platform.PAN123.value: 16,
}


def _defaults() -> dict[str, Any]:
    return {
        "credentials": {p.value: "" for p in Platform},
        "xunlei_refresh_token": "",
        "proxy": "",
        "theme": "dark",
        "repo_url": "https://github.com/yiyi0904/by-yiyi-love",
        "download_dir": default_download_dir(),
        "threads": dict(DEFAULT_THREADS),
        "max_concurrent_tasks": 3,
        "speed_limit_kb": 0,
        "window": {"width": 1180, "height": 760, "x": None, "y": None},
    }


class Config:
    """线程安全的简单配置存储。"""

    def __init__(self, path: str = CONFIG_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data = _defaults()
        self.load()

    # -- 读写 ---------------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            if not os.path.isfile(self.path):
                return
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
            except (OSError, ValueError):
                return
            base = _defaults()
            for key, value in loaded.items():
                if isinstance(value, dict) and isinstance(base.get(key), dict):
                    base[key].update(value)
                else:
                    base[key] = value
            self.data = base

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except OSError:
                pass

    # -- 便捷访问 -----------------------------------------------------------
    def get(self, key: str, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self.data[key] = value

    def credential(self, platform: Platform | str) -> str:
        key = platform.value if isinstance(platform, Platform) else str(platform)
        with self._lock:
            return self.data.get("credentials", {}).get(key, "") or ""

    def set_credential(self, platform: Platform | str, value: str) -> None:
        key = platform.value if isinstance(platform, Platform) else str(platform)
        with self._lock:
            self.data.setdefault("credentials", {})[key] = value

    def threads(self, platform: Platform | str) -> int:
        key = platform.value if isinstance(platform, Platform) else str(platform)
        try:
            value = int(self.data.get("threads", {}).get(key, DEFAULT_THREADS.get(key, 16)))
        except (TypeError, ValueError):
            value = 16
        return max(1, min(value, 128))

    def download_dir(self) -> str:
        with self._lock:
            path = self.data.get("download_dir") or default_download_dir()
        os.makedirs(path, exist_ok=True)
        return path

    def max_tasks(self) -> int:
        try:
            return max(1, min(int(self.data.get("max_concurrent_tasks", 3)), 10))
        except (TypeError, ValueError):
            return 3

    def speed_limit(self) -> int:
        """全局限速，字节/秒；0 表示不限速。"""
        try:
            kb = int(self.data.get("speed_limit_kb", 0))
        except (TypeError, ValueError):
            kb = 0
        return max(0, kb) * 1024
