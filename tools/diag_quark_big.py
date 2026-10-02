"""从该分享里挑一个中等大小文件，走完整「取链 → 多线程下载 → 校验 → 清理」。"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.config import Config
from yunx.downloader import Download
from yunx.limiter import GlobalRateLimiter
from yunx.models import Platform
from yunx.platforms.quark import QuarkClient
from yunx.util import human_size

LINK = "https://pan.quark.cn/s/35d3c89573ec#/list/share"
MAX_BYTES = 60 * 1024 * 1024


def walk(client, session, cookie, fid, depth=0):
    files = client.list_files(session, fid, cookie)
    for item in files:
        if item.is_dir and depth < 2:
            yield from walk(client, session, cookie, item.fid, depth + 1)
        elif not item.is_dir:
            yield item


def main() -> int:
    cookie = Config().credential(Platform.QUARK)
    client = QuarkClient()
    session = client.open_session(LINK, None, cookie)
    candidates = [f for f in walk(client, session, cookie, "0") if 0 < f.size <= MAX_BYTES]
    if not candidates:
        print("没找到合适大小的文件")
        return 0
    target = max(candidates, key=lambda f: f.size)
    print(f"目标：{target.name}  {human_size(target.size)}")

    link = client.fetch_download(session, target, cookie, log=lambda m: print(m, flush=True))
    link.headers = {**client.download_headers(cookie), **(link.headers or {})}
    with tempfile.TemporaryDirectory() as tmp:
        task = Download("big", link, tmp, threads=16, limiter=GlobalRateLimiter(0))
        started = time.time()
        task.start()
        deadline = time.time() + 600
        while task.state.name in ("RUNNING", "QUEUED") and time.time() < deadline:
            time.sleep(0.5)
        snap = task.snapshot()
        elapsed = time.time() - started
        print(f"状态：{snap.state.name}  {human_size(snap.downloaded)}/{human_size(snap.total)}")
        print(f"用时 {elapsed:.1f}s，平均 {human_size(snap.downloaded / max(elapsed, 0.1))}/s，线程 {snap.workers}")
        if snap.state.name != "COMPLETED":
            print("失败：", snap.message)
            return 1
        size = os.path.getsize(task.target_path)
        print("落盘大小:", size, "期望:", target.size)
        assert size == target.size, "大小不一致"
    if link.cleanup_dir_fid:
        client.cleanup(session, link, cookie)
        print("临时转存已清理")
    print("大文件流程 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
