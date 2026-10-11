"""小量 HTTPS 下載；Windows 可用既有 curl，保持憑證驗證。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class DownloadError(ValueError):
    pass


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    url: str
    status: int
    content_type: str
    fetched_at: datetime
    transport: str


def get_https(url: str, *, transport: str = "auto", timeout: int = 10) -> HttpResponse:
    """每次至多一個請求；無背景重試，不繞過 HTTP 拒絕或 TLS 驗證。"""
    if urlsplit(url).scheme != "https":
        raise DownloadError("資料來源必須使用 HTTPS")
    if transport not in {"auto", "urllib", "curl"}:
        raise DownloadError("transport 必須為 auto／urllib／curl")
    curl = shutil.which("curl.exe") or shutil.which("curl")
    chosen = "curl" if transport == "curl" or (transport == "auto" and curl) else "urllib"
    try:
        if chosen == "curl":
            if not curl:
                raise DownloadError("找不到系統 curl；可明確選擇 --transport urllib")
            marker = b"\nETF_HTTP_META:"
            result = subprocess.run(
                [curl, "--disable", "--silent", "--show-error", "--location",
                 "--max-redirs", "3", "--proto", "=https", "--proto-redir", "=https",
                 "--connect-timeout", str(timeout), "--max-time", str(timeout),
                 "--write-out", marker.decode() + "%{http_code}\t%{content_type}\t%{url_effective}", url],
                capture_output=True, timeout=timeout + 5,
            )
            if result.returncode:
                raise DownloadError(f"curl 失敗 ({result.returncode}): {result.stderr.decode('utf-8', errors='replace').strip()}")
            body, separator, metadata = result.stdout.rpartition(marker)
            if not separator:
                raise DownloadError("curl 沒有回傳 HTTP 狀態")
            status_text, content_type, effective_url = metadata.decode("utf-8").strip().split("\t", 2)
            status = int(status_text)
        else:
            request = Request(url, headers={"Accept": "application/json"})
            try:
                response = urlopen(request, timeout=timeout)
            except HTTPError as exc:
                # HTTP 拒絕也保存原文；由上層判定失敗，不丟失錯誤頁證據。
                response = exc
            with response:
                effective_url = response.url
                status = response.code
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
        if urlsplit(effective_url).scheme != "https":
            raise DownloadError("資料來源重新導向至非 HTTPS")
        fetched_at = datetime.now(timezone(timedelta(hours=8)))
        return HttpResponse(body, effective_url, status, content_type, fetched_at, chosen)
    except (HTTPError, URLError, OSError, subprocess.TimeoutExpired, UnicodeError, ValueError) as exc:
        if isinstance(exc, DownloadError):
            raise
        raise DownloadError(f"HTTPS 下載失敗：{exc}") from exc
