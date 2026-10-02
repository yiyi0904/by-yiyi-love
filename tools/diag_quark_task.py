"""细查夸克转存任务轮询为什么返回 require login [guest]。"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunx.config import Config
from yunx.models import Platform
from yunx.net import api_request
from yunx.platforms.quark import ORIGIN, REFERER, UA, QuarkClient, _api_url

LINK = "https://pan.quark.cn/s/35d3c89573ec#/list/share"


def raw(url: str, cookie: str, method: str = "GET", body: dict | None = None):
    headers = {
        "Cookie": cookie,
        "User-Agent": UA,
        "Origin": ORIGIN,
        "Referer": REFERER,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    resp = api_request(method, url, headers=headers, json=body)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text[:300]


def main() -> int:
    config = Config()
    original = config.credential(Platform.QUARK)
    client = QuarkClient()
    session = client.open_session(LINK, None, original)
    files = client.list_files(session, "0", original)
    folder = files[0]
    sub = client.list_files(session, folder.fid, original)
    target = next(f for f in sub if not f.is_dir)
    print("目标文件:", target.name, flush=True)

    cookie = original
    base = client._ensure_temp_dir(cookie)  # noqa: SLF001
    print("临时目录:", base, "refreshed?", client.refreshed_credential is not None, flush=True)
    if client.refreshed_credential:
        cookie = client.refreshed_credential
        client.refreshed_credential = None

    sub_name = f"diag_{int(__import__('time').time() * 1000)}"
    sub_dir = client._create_folder(sub_name, base, cookie)  # noqa: SLF001
    if client.refreshed_credential:
        cookie = client.refreshed_credential
        client.refreshed_credential = None
    print("临时子目录:", sub_dir, flush=True)

    task_id = client._save_share(session, target, sub_dir, cookie)  # noqa: SLF001
    print("task_id:", task_id, flush=True)
    if client.refreshed_credential:
        print("!! 会话 Cookie 在转存后被刷新", flush=True)

    q = urllib.parse.urlencode({"task_id": task_id, "retry_index": 0})
    variants = {
        "原cookie": original,
        "刷新后cookie": cookie,
    }
    for label, ck in variants.items():
        if ck is None:
            continue
        status, payload = raw(_api_url("/1/clouddrive/task?") + q, ck)
        print(f"\n[{label}] HTTP {status}", flush=True)
        print(json.dumps(payload, ensure_ascii=False)[:600], flush=True)

    # 不用 retry_index 再试一次
    q2 = urllib.parse.urlencode({"task_id": task_id})
    status, payload = raw(_api_url("/1/clouddrive/task?") + q2, cookie)
    print(f"\n[无 retry_index] HTTP {status}", flush=True)
    print(json.dumps(payload, ensure_ascii=False)[:600], flush=True)

    # 对照：同一 cookie 调 member 接口
    status, payload = raw("https://drive-pc.quark.cn/1/clouddrive/member?pr=ucpro&fr=pc&fetch_subscribe=true&_ch=home", cookie)
    print(f"\n[member 对照] HTTP {status}", flush=True)
    print(json.dumps(payload, ensure_ascii=False)[:300], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
