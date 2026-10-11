"""官方開休市排程的月份日曆；不把排程冒稱實際臨時休市紀錄。"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from etf_agent.providers.http import DownloadError, get_https
from etf_agent.providers.monthly import HistoryDataError, month_start


class CalendarError(ValueError):
    """官方排程無法讀取、年份錯配或快取不完整。"""


def calendar_url(market: str, year: int) -> str:
    if market == "TWSE":
        return f"https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?response=json&date={year}0101"
    if market == "TPEX":
        return f"https://www.tpex.org.tw/www/zh-tw/bulletin/tradingDate?date={year}&response=json"
    raise CalendarError("市場須為 TWSE 或 TPEX")


class _TableRows(HTMLParser):
    """TPEx JSON 內的官方 HTML 表；允許原表個別 td 未閉合。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None

    def finish_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.finish_cell()
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.finish_cell()
        elif tag == "tr":
            self.finish_cell()
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _parse_tpex(payload: dict, year: int) -> list[dict]:
    data = payload.get("data")
    html = data.get("html") if isinstance(data, dict) else None
    if payload.get("stat") != "ok" or not isinstance(html, str):
        raise CalendarError("TPEx 開休市表狀態或 HTML 內容不符")
    table = _TableRows()
    table.feed(html)
    if not table.rows or not re.search(rf"中華民國\s*{year-1911}\s*年", "".join(table.rows[0])):
        raise CalendarError("TPEx 官方開休市表回應年份不符")
    if len(table.rows) < 3 or table.rows[1] != ["紀念節日名稱", "日期", "星期", "說明"]:
        raise CalendarError("TPEx 官方開休市表欄位不符")
    records = {}

    def add_dates(text, name, description, is_open):
        matches = re.findall(r"(\d{1,2})月(\d{1,2})日", text)
        for month, day in matches:
            value = date(year, int(month), int(day)).isoformat()
            record = {"trade_date": value, "name": name, "description": description, "is_open": is_open}
            if value in records and records[value]["is_open"] != is_open:
                raise CalendarError("TPEx 股票開休市日期衝突")
            records[value] = record
        return bool(matches)

    for cells in table.rows[2:]:
        if not cells or "債券" in cells[0]:
            continue  # 各債券系統有不同封關日期，不能混入股票日曆。
        if len(cells) != 4:
            raise CalendarError("TPEx 股票開休市表列格式不符")
        name, dates, _, description = cells
        opened = bool(re.search(r"(?:開始|最後)交易", name))
        if not add_dates(dates, name, description, opened):
            raise CalendarError("TPEx 股票開休市日期無法辨識")
        if opened and "股票" in name and "市場無交易" in description:
            add_dates(description, "股票市場無交易，僅辦理給付結算", description, False)
    if not records:
        raise CalendarError("TPEx 股票開休市表無資料")
    return list(records.values())


def parse_schedule(body: bytes, *, market: str, year: int) -> list[dict]:
    """解析已查證的年度官方表；回應年份須與請求相符。"""
    try:
        payload = json.loads(body.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise CalendarError("官方開休市回應須為物件")
        if market == "TPEX":
            return _parse_tpex(payload, year)
        if market != "TWSE":
            raise CalendarError("市場須為 TWSE 或 TPEX")
        if (not isinstance(payload, dict) or payload.get("stat") != "ok"
                or payload.get("queryYear") != year
                or payload.get("date") != f"{year}0101"
                or payload.get("fields") != ["日期", "名稱", "說明"]
                or not isinstance(payload.get("data"), list) or not payload["data"]):
            raise CalendarError("官方開休市表年份、狀態或欄位不符")
        records = []
        seen = set()
        for cells in payload["data"]:
            if not isinstance(cells, list) or len(cells) != 3 or any(not isinstance(v, str) for v in cells):
                raise CalendarError("官方開休市表列格式不符")
            day = date.fromisoformat(cells[0])
            if day.year != year or day in seen:
                raise CalendarError("官方日期跨年份或重複")
            seen.add(day)
            name = cells[1]
            records.append({"trade_date": day.isoformat(), "name": name, "description": cells[2],
                            "is_open": bool(re.search(r"(?:開始|最後)交易", name))})
        return records
    except CalendarError:
        raise
    except (ValueError, TypeError, UnicodeError) as exc:
        raise CalendarError(f"官方開休市表解析失敗：{exc}") from exc


def build_calendar(month: str, schedules: dict[str, list[dict]], sources: list[dict]) -> dict:
    try:
        first = month_start(month)
    except HistoryDataError as exc:
        raise CalendarError(str(exc)) from exc
    days = [first + timedelta(days=index) for index in range(monthrange(first.year, first.month)[1])]
    markets = {}
    for market in ("TWSE", "TPEX"):
        if market not in schedules or not schedules[market]:
            raise CalendarError(f"缺少 {market} 官方年度開休市表")
        events = {event["trade_date"]: event for event in schedules[market]}
        rows = []
        for day in days:
            event = events.get(day.isoformat())
            opened = event["is_open"] if event is not None else day.weekday() < 5
            rows.append({"trade_date": day.isoformat(), "is_open": opened,
                         "reason": event["name"] if event else "例行交易日" if opened else "週末休市"})
        markets[market] = {"trade_dates": [row["trade_date"] for row in rows if row["is_open"]],
                           "days": rows, "schedule_verified": True, "actual_sessions_verified": False}
    signature = json.dumps({"month": month, "markets": markets,
                            "source_hashes": [source["raw_sha256"] for source in sources]},
                           sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"format_version": "1.0", "scope": "official_monthly_calendar", "month": month,
            "calendar_version": "calendar-v1-" + hashlib.sha256(signature).hexdigest()[:12],
            "calendar_basis": "official_schedule", "markets": markets, "sources": sources,
            "baseline_rule": "weekday sessions except official scheduled closed days; explicit opening events override",
            "limitations": ["依官方年度開休市排程與例行週一至週五交易日建立，非個股停牌表",
                            "未完整核實天然災害等臨時全市場休市公告，actual_sessions_verified=false",
                            "僅提供指定月份，不推定其他月份或歷史公開時間"],
            "submission_ready": False}


def download_calendar(month: str, output_dir: Path | str, *, transport: str = "auto", fetcher=None) -> dict:
    """少量官方 HTTPS 請求，另存原始表、月份 JSON／CSV 及來源資訊。"""
    try:
        first = month_start(month)
    except HistoryDataError as exc:
        raise CalendarError(str(exc)) from exc
    # 先確認兩個來源均已實測，不留下只完成一市場的成功日曆。
    urls = {market: calendar_url(market, first.year) for market in ("TWSE", "TPEX")}
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / month / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=False)
    fetcher = fetcher or get_https
    schedules, sources = {}, []
    for index, (market, url) in enumerate(urls.items(), start=1):
        try:
            response = fetcher(url, transport=transport)
            raw_path = run_dir / "raw" / f"{market}_{first.year}.json"
            raw_path.write_bytes(response.body)
            source = {"source_key": f"CAL{index}", "market": market, "requested_url": url,
                      "effective_url": response.url, "http_status": response.status,
                      "content_type": response.content_type, "fetched_at": response.fetched_at.isoformat(),
                      "transport": response.transport, "raw_path": raw_path.relative_to(run_dir).as_posix(),
                      "raw_sha256": hashlib.sha256(response.body).hexdigest()}
            sources.append(source)
            if (response.status != 200 or "json" not in response.content_type.lower()
                    or urlsplit(response.url).scheme != "https"
                    or urlsplit(response.url).hostname != urlsplit(url).hostname):
                raise CalendarError(f"{market} 官方開休市回應狀態／主機／類型不符")
            schedules[market] = parse_schedule(response.body, market=market, year=first.year)
        except (CalendarError, DownloadError, OSError) as exc:
            (run_dir / "failure.json").write_text(json.dumps({"month": month, "run_id": run_id,
                "success": False, "sources": sources, "error": str(exc)}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            raise CalendarError(f"日曆取得失敗（原始證據保留於 {run_dir}）：{exc}") from exc
    calendar = {**build_calendar(month, schedules, sources), "created_at": now.isoformat(), "run_id": run_id,
                "success": True, "network_requests": len(sources)}
    path = run_dir / "calendar.json"
    path.write_text(json.dumps(calendar, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    with (run_dir / "calendar.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("trade_date", "market", "is_open", "reason", "calendar_basis"), lineterminator="\n")
        writer.writeheader()
        for market, info in calendar["markets"].items():
            writer.writerows({**row, "market": market, "is_open": str(row["is_open"]).lower(),
                              "calendar_basis": calendar["calendar_basis"]} for row in info["days"])
    return {"calendar": calendar, "calendar_path": str(path), "calendar_csv": str(run_dir / "calendar.csv"), "run_dir": str(run_dir)}


def load_calendar(path: Path | str) -> dict:
    """離線使用封存日曆，核對版本格式與其官方原始來源 hash。"""
    try:
        path = Path(path).resolve(strict=True)
        calendar = json.loads(path.read_text(encoding="utf-8-sig"))
        if (not isinstance(calendar, dict) or calendar.get("format_version") != "1.0"
                or calendar.get("scope") != "official_monthly_calendar"
                or not isinstance(calendar.get("sources"), list) or len(calendar["sources"]) != 2):
            raise CalendarError("日曆格式或官方來源不完整")
        schedules = {}
        for source in calendar["sources"]:
            relative = Path(source["raw_path"])
            raw = (path.parent / relative).resolve(strict=True)
            if relative.is_absolute() or not raw.is_relative_to(path.parent):
                raise CalendarError("日曆原始來源路徑超出 run 目錄")
            body = raw.read_bytes()
            if hashlib.sha256(body).hexdigest() != source["raw_sha256"]:
                raise CalendarError("日曆原始來源 hash 不符")
            schedules[source["market"]] = parse_schedule(body, market=source["market"], year=int(calendar["month"][:4]))
        rebuilt = build_calendar(calendar["month"], schedules, calendar["sources"])
        if calendar.get("markets") != rebuilt["markets"] or calendar.get("calendar_version") != rebuilt["calendar_version"]:
            raise CalendarError("日曆內容與官方原始表／版本不一致")
        return calendar
    except CalendarError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CalendarError(f"日曆無法讀取：{exc}") from exc
