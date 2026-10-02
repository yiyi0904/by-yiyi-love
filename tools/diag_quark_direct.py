"""测试夸克能否「不转存」直接取直链，并查看空间占用。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.config import Config
from yunx.models import Platform
from yunx.net import api_request
from yunx.platforms.quark import ORIGIN, REFERER, UA, QuarkClient, _api_url

LINK = "https://pan.quark.cn/s/35d3c89573ec#/list/share"


def raw(method, url, cookie, body=None):
    headers = {"Cookie": cookie, "User-Agent": UA, "Origin": ORIGIN, "Referer": REFERER}
    if body is not None:
        headers["Content-Type"] = "application/json"
    resp = api_request(method, url, headers=headers, json=body)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {"raw": resp.text[:200]}


def main() -> int:
    cookie = Config().credential(Platform.QUARK)
    client = QuarkClient()

    print("== 空间情况 ==")
    status, data = raw(
        "GET",
        "https://drive-pc.quark.cn/1/clouddrive/member?pr=ucpro&fr=pc"
        "&fetch_subscribe=true&_ch=home",
        cookie,
    )
    payload = data.get("data") or {}
    total = payload.get("total_capacity") or 0
    used = payload.get("use_capacity") or 0
    print("  used=%.2fGB total=%.2fGB free=%.2fGB"
          % (used / 1024 ** 3, total / 1024 ** 3, (total - used) / 1024 ** 3))

    session = client.open_session(LINK, None, cookie)
    files = client.list_files(session, "0", cookie)
    sub = client.list_files(session, files[0].fid, cookie)
    target = next(f for f in sub if not f.is_dir)
    print("\n目标文件: %s  %.0f KB" % (target.name, target.size / 1024))
    print("  fid=%s" % target.fid)
    print("  fid_token=%s..." % target.fid_token[:40])
    print("  pdir_fid=%s" % target.parent_fid)

    body = {
        "fids": [target.fid],
        "pwd_id": session.share_id,
        "stoken": session.token,
        "fids_token": [target.fid_token],
    }
    print("\n== A) 直接取链（不转存）==")
    status, data = raw(
        "POST",
        _api_url("/1/clouddrive/file/download?pr=ucpro&fr=pc&sys=win32&ve=3.23.2"),
        cookie,
        body,
    )
    print("  ->", status)
    item = (data.get("data") or [{}])[0]
    for key in sorted(item):
        value = item[key]
        if isinstance(value, str) and len(value) > 90:
            value = value[:90] + "..."
        print("     %-16s = %s" % (key, value))

    url = item.get("download_url") or ""
    if url:
        import tempfile
        import time

        from yunx.downloader import Download
        from yunx.limiter import GlobalRateLimiter

        from yunx.models import DownloadLink

        print("\n== 用下载引擎实下（直链，不转存）==")
        link = DownloadLink(url=url, filename=target.name, size=target.size)
        link.headers = {
            "Cookie": cookie,
            "User-Agent": UA,
            "Referer": REFERER,
        }
        with tempfile.TemporaryDirectory() as tmp:
            task = Download("direct", link, tmp, threads=4, limiter=GlobalRateLimiter(0))
            task.start()
            deadline = time.time() + 120
            while task.state.name in ("RUNNING", "QUEUED") and time.time() < deadline:
                time.sleep(0.2)
            snap = task.snapshot()
            print("  状态:", snap.state.name, snap.downloaded, "/", snap.total)
            if snap.state.name == "COMPLETED":
                print("  文件大小:", os.path.getsize(task.target_path))
            else:
                print("  失败:", snap.message)

    print("\n== B) 加 entry=ft ==")
    body2 = dict(body, entry="ft")
    status, data = raw(
        "POST",
        _api_url("/1/clouddrive/file/download?entry=ft&pr=ucpro&fr=pc"),
        cookie,
        body2,
    )
    print("  ->", status, json.dumps(data, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
