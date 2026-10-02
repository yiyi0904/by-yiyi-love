"""多线程分片下载引擎。

移植自安卓版 ChunkDownloader / DownloadManager 的核心策略：
- Range 分片 + 多线程并行 + 断点续传（.part 文件 + 元数据）；
- 服务器忽略 Range（返回 200）时回退单流整文件，绝不为单个分片下载整文件；
- 写入后校验字节数，避免空洞文件；
- 支持暂停 / 继续 / 取消 / 删除。
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import requests

from .limiter import GlobalRateLimiter
from .models import DownloadLink
from .net import make_session, proxies
from .util import RateMeter, human_size, sanitize_filename, unique_path

BUFFER_SIZE = 256 * 1024
CHUNK_RETRIES = 4
MIN_CHUNK = 1 * 1024 * 1024
PROGRESS_INTERVAL = 0.25


class DlState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def label(self) -> str:
        return {
            DlState.QUEUED: "排队中",
            DlState.RUNNING: "下载中",
            DlState.PAUSED: "已暂停",
            DlState.COMPLETED: "已完成",
            DlState.FAILED: "失败",
            DlState.CANCELED: "已取消",
        }[self]


class RangeIgnored(Exception):
    """服务器忽略了 Range 请求（返回 200 整文件）。"""


class DownloadCanceled(Exception):
    pass


@dataclass
class Snapshot:
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    state: DlState = DlState.QUEUED
    message: str = ""
    workers: int = 1


def probe_size(url: str, headers: dict[str, str], session: requests.Session) -> tuple[int, bool]:
    """探测文件大小与是否支持 Range。返回 (size, range_supported)。"""
    try:
        resp = session.get(
            url,
            headers={**headers, "Range": "bytes=0-0"},
            stream=True,
            timeout=(15, 30),
            proxies=proxies(),
        )
    except requests.RequestException:
        return 0, False
    with resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" in ctype:
            raise RuntimeError("下载地址返回了网页（链接可能已失效或需要 Referer）")
        if resp.status_code == 206:
            cr = resp.headers.get("Content-Range", "")
            total = 0
            if "/" in cr:
                tail = cr.rsplit("/", 1)[1].strip()
                if tail.isdigit():
                    total = int(tail)
            return total, True
        if resp.status_code == 200:
            length = resp.headers.get("Content-Length")
            return (int(length) if length and length.isdigit() else 0), False
        if resp.status_code in (403, 401):
            raise RuntimeError(f"下载地址拒绝访问（HTTP {resp.status_code}），请检查账号或直链是否过期")
        return 0, False


class Download:
    """单个文件的下载任务。"""

    def __init__(
        self,
        task_id: str,
        link: DownloadLink,
        save_dir: str,
        threads: int = 16,
        limiter: GlobalRateLimiter | None = None,
        on_event: Callable[["Download"], None] | None = None,
    ) -> None:
        self.id = task_id
        self.link = link
        self.save_dir = save_dir
        self.threads = max(1, min(int(threads), 128))
        self.limiter = limiter or GlobalRateLimiter(0)
        self.on_event = on_event

        self.filename = sanitize_filename(link.filename or self._name_from_url() or "download.bin")
        self.target_path = os.path.join(save_dir, self.filename)
        self.part_path = self.target_path + ".yixipart"
        self.meta_path = self.target_path + ".yiximeta"

        self.state = DlState.QUEUED
        self.downloaded = 0
        self.total = int(link.size or 0)
        self.message = ""
        self.workers = 1
        self.created_at = time.time()
        self.finished_at = 0.0
        self.session = make_session(max(self.threads + 4, 16))

        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._meter = RateMeter(2.0)
        self._lock = threading.Lock()
        self._last_notify = 0.0
        self._completed_ranges: set[int] = set()

    # -- 元信息 -------------------------------------------------------------
    def _name_from_url(self) -> str:
        try:
            path = urllib.parse.urlparse(self.link.url).path
            return urllib.parse.unquote(os.path.basename(path))
        except Exception:
            return ""

    @property
    def progress(self) -> float:
        if self.total > 0:
            return min(1.0, self.downloaded / self.total)
        return 0.0

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                downloaded=self.downloaded,
                total=self.total,
                speed=self._meter.speed() if self.state == DlState.RUNNING else 0.0,
                state=self.state,
                message=self.message,
                workers=self.workers,
            )

    def _notify(self, force: bool = False) -> None:
        if self.on_event is None:
            return
        now = time.monotonic()
        if not force and now - self._last_notify < PROGRESS_INTERVAL:
            return
        self._last_notify = now
        try:
            self.on_event(self)
        except Exception:
            pass

    def _add_bytes(self, n: int) -> None:
        with self._lock:
            self.downloaded += n
        self._meter.add(n)
        self.limiter.consume(n)
        self._notify()

    # -- 控制 ---------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._cancel.clear()
        self.state = DlState.RUNNING
        self.message = ""
        self._notify(force=True)
        self._thread = threading.Thread(target=self._run, name=f"yunx-dl-{self.id}", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self.state == DlState.RUNNING:
            self._stop.set()
            self.state = DlState.PAUSED
            self._notify(force=True)

    def cancel(self) -> None:
        self._cancel.set()
        self._stop.set()
        if self.state not in (DlState.COMPLETED, DlState.CANCELED):
            self.state = DlState.CANCELED
            self._notify(force=True)

    def remove_files(self) -> None:
        for path in (self.part_path, self.meta_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def is_active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- 主流程 -------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._prepare_resume()
            total, range_ok = probe_size(self.link.url, self.link.headers, self.session)
            if total > 0:
                with self._lock:
                    self.total = total
            if not range_ok or self.total <= 0 or self.total < 2 * MIN_CHUNK:
                self._single_stream()
            else:
                self._chunked(range_ok=True)
            self._finalize()
        except DownloadCanceled:
            self._settle_after_stop()
        except RangeIgnored:
            # 服务器忽略 Range：整体回退单流
            try:
                self._single_stream()
                self._finalize()
            except DownloadCanceled:
                self._settle_after_stop()
            except Exception as exc:  # noqa: BLE001
                self._fail(exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)

    def _settle_after_stop(self) -> None:
        """区分「暂停」与「取消」。"""
        if self._cancel.is_set():
            self.state = DlState.CANCELED
        else:
            self.state = DlState.PAUSED
        self._notify(force=True)

    def _fail(self, exc: Exception) -> None:
        if self._cancel.is_set():
            self.state = DlState.CANCELED
        elif self._stop.is_set():
            self.state = DlState.PAUSED
        else:
            self.state = DlState.FAILED
            self.message = str(exc) or exc.__class__.__name__
        self._notify(force=True)

    def _finalize(self) -> None:
        if self.total > 0:
            try:
                real = os.path.getsize(self.part_path)
            except OSError:
                real = 0
            if real < self.total:
                raise RuntimeError(f"文件不完整：已写入 {human_size(real)} / 需要 {human_size(self.total)}")

        final = unique_path(self.target_path)
        try:
            if os.path.exists(final):
                os.remove(final)
            os.replace(self.part_path, final)
        except OSError as exc:
            raise RuntimeError(f"保存文件失败：{exc}") from exc
        try:
            if os.path.exists(self.meta_path):
                os.remove(self.meta_path)
        except OSError:
            pass
        self.target_path = final
        with self._lock:
            if self.total > 0:
                self.downloaded = self.total
        self.state = DlState.COMPLETED
        self.finished_at = time.time()
        self.message = ""
        self._notify(force=True)

    # -- 断点续传 -----------------------------------------------------------
    def _prepare_resume(self) -> None:
        """读取元数据恢复断点信息。

        part 文件是预分配的（长度等于文件总大小），所以不能用文件长度当进度，
        必须以「已完成的分片区间」为准。
        """
        self._completed_ranges.clear()
        self._resume_ranges: list[tuple[int, int]] | None = None
        with self._lock:
            self.downloaded = 0
        if not (os.path.exists(self.part_path) and os.path.exists(self.meta_path)):
            return
        try:
            with open(self.meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            return
        if meta.get("url") != self.link.url:
            return
        raw_ranges = meta.get("ranges") or []
        ranges: list[tuple[int, int]] = []
        for item in raw_ranges:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                ranges.append((int(item[0]), int(item[1])))
        if not ranges:
            return
        done = {int(i) for i in meta.get("done", []) if isinstance(i, int) or str(i).isdigit()}
        done = {i for i in done if 0 <= i < len(ranges)}
        with self._lock:
            self.total = int(meta.get("total") or self.total or 0)
            self.downloaded = sum(ranges[i][1] - ranges[i][0] + 1 for i in done)
        self._completed_ranges = done
        self._resume_ranges = ranges

    def _write_meta(self, ranges: list[tuple[int, int]]) -> None:
        try:
            with open(self.meta_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "url": self.link.url,
                        "total": self.total,
                        "ranges": ranges,
                        "done": sorted(self._completed_ranges),
                    },
                    fh,
                )
        except OSError:
            pass

    # -- 分片下载 -----------------------------------------------------------
    def _chunked(self, range_ok: bool = True) -> None:
        total = self.total
        resume_ranges = getattr(self, "_resume_ranges", None)
        if resume_ranges:
            # 断点续传：沿用上次的分片边界，避免区间错位
            ranges = list(resume_ranges)
            total = max(total, ranges[-1][1] + 1)
            self.total = total
        else:
            count = max(1, min(self.threads, max(1, math.ceil(total / MIN_CHUNK))))
            chunk_size = math.ceil(total / count)
            ranges = [
                (i * chunk_size, min((i + 1) * chunk_size - 1, total - 1))
                for i in range(count)
            ]
        count = min(self.threads, len(ranges))
        self.workers = count
        self._resume_ranges = None
        self._write_meta(ranges)

        # 确保 part 文件长度正确（预分配，便于各分片定位写入）
        with open(self.part_path, "r+b" if os.path.exists(self.part_path) else "w+b") as fh:
            fh.truncate(total)

        pending = [i for i in range(len(ranges)) if i not in self._completed_ranges]
        queue_lock = threading.Lock()
        errors: list[Exception] = []
        range_ignored = threading.Event()

        def worker() -> None:
            while True:
                if self._cancel.is_set() or self._stop.is_set() or range_ignored.is_set():
                    return
                with queue_lock:
                    if not pending:
                        return
                    idx = pending.pop(0)
                try:
                    self._download_range(idx, ranges[idx])
                except RangeIgnored:
                    range_ignored.set()
                    return
                except DownloadCanceled:
                    return
                except Exception as exc:  # noqa: BLE001
                    with queue_lock:
                        errors.append(exc)
                    return

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(count)]
        for t in threads:
            t.start()
            time.sleep(0.02)  # 错峰建连
        for t in threads:
            t.join()

        if self._cancel.is_set():
            raise DownloadCanceled()
        if self._stop.is_set():
            raise DownloadCanceled()
        if range_ignored.is_set():
            raise RangeIgnored()
        if errors:
            raise errors[0]

    def _download_range(self, idx: int, span: tuple[int, int]) -> None:
        start, end = span
        last_error: Exception | None = None
        for attempt in range(CHUNK_RETRIES):
            if self._cancel.is_set() or self._stop.is_set():
                raise DownloadCanceled()
            try:
                self._range_attempt(start, end)
            except RangeIgnored:
                raise
            except DownloadCanceled:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(0.6 * (attempt + 1), 3.0))
                continue
            else:
                with self._lock:
                    self._completed_ranges.add(idx)
                return
        raise RuntimeError(f"分片 {idx} 下载失败：{last_error}")

    def _range_attempt(self, start: int, end: int) -> None:
        headers = {**self.link.headers, "Range": f"bytes={start}-{end}"}
        try:
            resp = self.session.get(
                self.link.url, headers=headers, stream=True, timeout=(15, 60), proxies=proxies()
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"网络错误：{exc}") from exc
        with resp:
            if resp.status_code == 200:
                raise RangeIgnored()
            if resp.status_code != 206:
                raise RuntimeError(f"分片请求返回 HTTP {resp.status_code}")
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise RuntimeError("分片返回网页内容（链接可能失效）")
            expected = end - start + 1
            written = 0
            with open(self.part_path, "r+b") as fh:
                fh.seek(start)
                for chunk in resp.iter_content(BUFFER_SIZE):
                    if not chunk:
                        continue
                    if self._cancel.is_set() or self._stop.is_set():
                        raise DownloadCanceled()
                    allow = min(len(chunk), expected - written)
                    if allow <= 0:
                        break
                    fh.write(chunk[:allow])
                    written += allow
                    self._add_bytes(allow)
                    if written >= expected:
                        break
            if written < expected:
                raise RuntimeError(f"分片数据不足（{written}/{expected}）")

    # -- 单流下载 -----------------------------------------------------------
    def _single_stream(self) -> None:
        self.workers = 1
        if os.path.exists(self.part_path):
            try:
                os.remove(self.part_path)
            except OSError:
                pass
        if os.path.exists(self.meta_path):
            try:
                os.remove(self.meta_path)
            except OSError:
                pass
        with self._lock:
            self.downloaded = 0

        try:
            resp = self.session.get(
                self.link.url, headers=self.link.headers, stream=True, timeout=(15, 60), proxies=proxies()
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"网络错误：{exc}") from exc

        with resp:
            if resp.status_code >= 400:
                raise RuntimeError(f"下载失败 HTTP {resp.status_code}")
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise RuntimeError("下载地址返回网页内容（链接可能已失效或需要 Referer）")
            total = self.total
            if total <= 0:
                length = resp.headers.get("Content-Length")
                if length and length.isdigit():
                    total = int(length)
            if total > 0 and self.total <= 0:
                with self._lock:
                    self.total = total
            written = 0
            with open(self.part_path, "wb") as fh:
                for chunk in resp.iter_content(BUFFER_SIZE):
                    if not chunk:
                        continue
                    if self._cancel.is_set() or self._stop.is_set():
                        raise DownloadCanceled()
                    fh.write(chunk)
                    written += len(chunk)
                    self._add_bytes(len(chunk))
                    if total > 0 and written >= total:
                        break
            if total > 0 and written < total:
                raise RuntimeError(f"下载中断：{human_size(written)} / {human_size(total)}")


class DownloadQueue:
    """带并发上限的任务队列。"""

    def __init__(self, max_concurrent: int = 3, limiter: GlobalRateLimiter | None = None) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.limiter = limiter or GlobalRateLimiter(0)
        self._tasks: list[Download] = []
        self._lock = threading.RLock()
        self._scheduler: threading.Thread | None = None
        self._wake = threading.Event()
        self._running = True

    def start(self) -> None:
        if self._scheduler and self._scheduler.is_alive():
            return
        self._running = True
        self._scheduler = threading.Thread(target=self._loop, name="yunx-scheduler", daemon=True)
        self._scheduler.start()

    def stop(self) -> None:
        self._running = False
        self._wake.set()

    def add(self, task: Download) -> None:
        with self._lock:
            self._tasks.append(task)
        self._wake.set()

    def set_max_concurrent(self, value: int) -> None:
        self.max_concurrent = max(1, min(int(value), 16))
        self._wake.set()

    def _loop(self) -> None:
        while self._running:
            try:
                active = sum(1 for t in self._tasks if t.state == DlState.RUNNING and t.is_active())
                if active < self.max_concurrent:
                    queued = next(
                        (t for t in self._tasks if t.state == DlState.QUEUED and not t.is_active()),
                        None,
                    )
                    if queued is not None:
                        queued.start()
                        continue
                self._wake.wait(timeout=0.4)
                self._wake.clear()
            except Exception:  # pragma: no cover
                time.sleep(0.5)
