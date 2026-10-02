"""用本机已保存的凭证复现夸克取链失败，并打印服务端原始响应。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.config import Config
from yunx.models import Platform
from yunx.platforms.quark import QuarkClient

LINK = sys.argv[1] if len(sys.argv) > 1 else "https://pan.quark.cn/s/35d3c89573ec#/list/share"


def main() -> int:
    config = Config()
    for platform in Platform:
        value = config.credential(platform)
        if value:
            print(
                f"{platform.value}: len={len(value)} sha1={hashlib.sha1(value.encode()).hexdigest()[:10]}",
                flush=True,
            )
    cookie = config.credential(Platform.QUARK)
    if not cookie:
        print("没有夸克凭证")
        return 1

    client = QuarkClient()
    print("\n== 1) 校验凭证 ==", flush=True)
    try:
        print("nickname:", client.check_credential(cookie), flush=True)
    except Exception as exc:  # noqa: BLE001
        print("校验失败:", type(exc).__name__, exc, flush=True)

    print("\n== 2) 打开分享 ==", flush=True)
    session = None
    try:
        session = client.open_session(LINK, None, cookie)
        print("session:", session.share_id, "title:", session.title, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("解析失败:", type(exc).__name__, exc, flush=True)
        return 1

    print("\n== 3) 列文件 ==", flush=True)
    try:
        files = client.list_files(session, "0", cookie)
        for item in files[:10]:
            kind = "DIR " if item.is_dir else "FILE"
            print(f"  {kind} {item.name}  size={item.size} fid={item.fid[:12]}…", flush=True)
        print(f"  共 {len(files)} 项", flush=True)
    except Exception as exc:  # noqa: BLE001
        print("列目录失败:", type(exc).__name__, exc, flush=True)
        traceback.print_exc()
        return 1

    target = next((f for f in files if not f.is_dir), None)
    parent = "0"
    if target is None:
        folder = next((f for f in files if f.is_dir), None)
        if folder is None:
            print("空分享，跳过取链", flush=True)
            return 0
        print(f"\n== 3b) 进入子目录：{folder.name} ==", flush=True)
        print(f"  folder.fid={folder.fid}", flush=True)
        sub = client.list_files(session, folder.fid, cookie)
        for item in sub[:10]:
            kind = "DIR " if item.is_dir else "FILE"
            print(
                f"  {kind} {item.name} size={item.size} fid={item.fid} "
                f"pdir_fid={item.parent_fid}",
                flush=True,
            )
        print(f"  共 {len(sub)} 项", flush=True)
        target = next((f for f in sub if not f.is_dir), None)
        if target is None:
            print("子目录里没有文件，跳过取链", flush=True)
            return 0

    print(f"\n== 4) 取链：{target.name} ==", flush=True)
    print(f"  fid={target.fid} pdir_fid={target.parent_fid}", flush=True)
    try:
        link = client.fetch_download(session, target, cookie, log=lambda m: print(m, flush=True))
        print("OK url:", link.url[:120], flush=True)
        print("   size:", link.size, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("取链失败:", type(exc).__name__, exc, flush=True)
        traceback.print_exc()
        return 1

    print("\n== 5) 用多线程引擎实下 ==", flush=True)
    import tempfile
    import time

    from yunx.downloader import Download
    from yunx.limiter import GlobalRateLimiter

    link.headers = {**client.download_headers(cookie), **(link.headers or {})}
    with tempfile.TemporaryDirectory() as tmp:
        task = Download(
            "diag",
            link,
            tmp,
            threads=4,
            limiter=GlobalRateLimiter(0),
        )
        task.start()
        deadline = time.time() + 120
        while task.state.name in ("RUNNING", "QUEUED") and time.time() < deadline:
            time.sleep(0.2)
        snap = task.snapshot()
        print("下载状态:", snap.state.name, "已下载:", snap.downloaded, "/", snap.total, flush=True)
        if snap.state.name != "COMPLETED":
            print("错误:", snap.message, flush=True)
            return 1
        print("文件:", os.path.getsize(task.target_path), "字节", flush=True)

    print("\n== 6) 清理临时转存 ==", flush=True)
    if link.cleanup_dir_fid:
        client.cleanup(session, link, cookie)
        print("已清理:", link.cleanup_dir_fid, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
