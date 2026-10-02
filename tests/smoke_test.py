"""非 GUI 冒烟测试：签名、编解码、下载引擎分片逻辑。"""

from __future__ import annotations

import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yunx.platforms.c139 import decrypt_body, encrypt_body, sign_header
from yunx.platforms.pan123 import decode_download_url, make_sign
from yunx.platforms.xunlei import build_captcha_sign, jwt_claims
from yunx.util import human_size, sanitize_filename, unique_path


def test_pan123_sign() -> None:
    key, value = make_sign("/b/api/share/download/info", ts=1700000000)
    assert 1 <= len(key) <= 8 and all(c in "0123456789abcdef" for c in key), key
    assert value.startswith("1700000000-"), value
    print("pan123 sign ok:", key, value)


def test_pan123_decode() -> None:
    raw = base64.urlsafe_b64encode(b"https://cdn.example.com/a.bin").decode()
    assert decode_download_url(f"https://x/download-v2?params={raw}") == "https://cdn.example.com/a.bin"
    plain = base64.b64encode(b"https://cdn.example.com/b.bin").decode()
    assert decode_download_url(plain) == "https://cdn.example.com/b.bin"
    assert decode_download_url("https://cdn.example.com/c.bin") is None
    print("pan123 decode ok")


def test_c139_crypto() -> None:
    payload = '{"getOutLinkInfoReq":{"linkID":"abc"}}'
    assert decrypt_body(encrypt_body(payload)) == payload
    header = sign_header(payload)
    assert len(header.split(",")) == 3
    print("c139 crypto ok:", header[:32], "...")


def test_xunlei_sign() -> None:
    sign = build_captcha_sign("a" * 32, "1700000000000")
    assert sign.startswith("1.") and len(sign) == 34, sign
    assert jwt_claims("x.y.z") == {}
    print("xunlei captcha sign ok:", sign[:12], "...")


def test_util() -> None:
    assert human_size(1536) == "1.50 KB"
    assert sanitize_filename("a/b:c?.mp4") == "a_b_c_.mp4"
    assert sanitize_filename("CON") == "_CON"
    print("util ok")


def test_chunked_download_local() -> None:
    """起一个本地 HTTP 服务，验证分片下载 + 断点续传 + 落盘内容正确。"""
    import hashlib
    import http.server
    import socketserver
    import threading
    import time
    import urllib.parse

    from yunx.downloader import Download
    from yunx.models import DownloadLink

    data = bytes((i * 7 + 13) % 256 for i in range(1024 * 1024 * 3 + 12345))
    etag = hashlib.md5(data).hexdigest()
    hits = {"count": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # noqa: D102
            pass

        def do_GET(self):  # noqa: N802
            hits["count"] += 1
            rng = self.headers.get("Range")
            if rng:
                start_s, _, end_s = rng.replace("bytes=", "").partition("-")
                start = int(start_s)
                end = int(end_s) if end_s else len(data) - 1
                end = min(end, len(data) - 1)
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory() as tmp:
        link = DownloadLink(
            url=f"http://127.0.0.1:{port}/file.bin",
            filename="payload.bin",
            size=len(data),
        )
        task = Download("test1", link, tmp, threads=8)
        task.start()
        deadline = time.time() + 60
        while task.state.name in ("RUNNING", "QUEUED") and time.time() < deadline:
            time.sleep(0.1)
        snap = task.snapshot()
        assert snap.state.name == "COMPLETED", (snap.state, snap.message)
        with open(task.target_path, "rb") as fh:
            saved = fh.read()
        assert hashlib.md5(saved).hexdigest() == etag, "内容不一致"
        print(f"chunked download ok: {len(saved)} bytes, {hits['count']} range requests")

        # 忽略 Range 的服务器 → 应回退单流
        class PlainHandler(Handler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        plain = socketserver.ThreadingTCPServer(("127.0.0.1", 0), PlainHandler)
        plain.daemon_threads = True
        plain_port = plain.server_address[1]
        threading.Thread(target=plain.serve_forever, daemon=True).start()
        link2 = DownloadLink(
            url=f"http://127.0.0.1:{plain_port}/file.bin",
            filename="payload2.bin",
            size=len(data),
        )
        task2 = Download("test2", link2, tmp, threads=8)
        task2.start()
        deadline = time.time() + 60
        while task2.state.name in ("RUNNING", "QUEUED") and time.time() < deadline:
            time.sleep(0.1)
        assert task2.state.name == "COMPLETED", task2.snapshot()
        with open(task2.target_path, "rb") as fh:
            saved2 = fh.read()
        assert hashlib.md5(saved2).hexdigest() == etag
        print("single-stream fallback ok")

        # 暂停 / 继续（断点续传）
        slow_data = bytes((i * 31 + 7) % 256 for i in range(12 * 1024 * 1024))

        class SlowHandler(Handler):
            def do_GET(self):  # noqa: N802
                rng = self.headers.get("Range")
                if rng:
                    start_s, _, end_s = rng.replace("bytes=", "").partition("-")
                    start = int(start_s)
                    end = min(int(end_s) if end_s else len(slow_data) - 1, len(slow_data) - 1)
                    chunk = slow_data[start : end + 1]
                    self.send_response(206)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(slow_data)}")
                    self.send_header("Content-Length", str(len(chunk)))
                    self.end_headers()
                    step = 64 * 1024
                    for i in range(0, len(chunk), step):
                        self.wfile.write(chunk[i : i + step])
                        self.wfile.flush()
                        time.sleep(0.02)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(slow_data)))
                    self.end_headers()
                    self.wfile.write(slow_data)

        slow = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SlowHandler)
        slow.daemon_threads = True
        slow_port = slow.server_address[1]
        threading.Thread(target=slow.serve_forever, daemon=True).start()
        link3 = DownloadLink(
            url=f"http://127.0.0.1:{slow_port}/slow.bin",
            filename="payload3.bin",
            size=len(slow_data),
        )
        task3 = Download("test3", link3, tmp, threads=4)
        task3.start()
        time.sleep(0.35)
        task3.pause()
        time.sleep(0.5)
        snap_pause = task3.snapshot()
        assert snap_pause.state.name == "PAUSED", snap_pause
        assert 0 < snap_pause.downloaded < len(slow_data), snap_pause
        print(f"pause ok: {snap_pause.downloaded}/{len(slow_data)}")
        task3.start()
        deadline = time.time() + 120
        while task3.state.name in ("RUNNING", "QUEUED") and time.time() < deadline:
            time.sleep(0.1)
        assert task3.state.name == "COMPLETED", task3.snapshot()
        with open(task3.target_path, "rb") as fh:
            saved3 = fh.read()
        assert hashlib.md5(saved3).hexdigest() == hashlib.md5(slow_data).hexdigest(), "续传后内容不一致"
        print("resume ok:", len(saved3), "bytes")
        slow.shutdown()

    server.shutdown()


if __name__ == "__main__":
    test_pan123_sign()
    test_pan123_decode()
    test_c139_crypto()
    test_xunlei_sign()
    test_util()
    test_chunked_download_local()
    print("ALL SMOKE TESTS PASSED")
