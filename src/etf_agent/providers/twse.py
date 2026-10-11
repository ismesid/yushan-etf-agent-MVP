"""TWSE 個股日成交資訊月報 adapter。"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from etf_agent.providers.monthly import HistoryDataError, ParsedMonth, decode_json, month_start, parse_table, validate_ticker


HISTORY_PAGE = "https://www.twse.com.tw/zh/trading/historical/stock-day.html"


def history_url(ticker: str, month: str) -> str:
    validate_ticker(ticker)
    day = month_start(month)
    return "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" + urlencode(
        {"date": day.strftime("%Y%m%d"), "stockNo": ticker, "response": "json"})


def parse_month(body: bytes, *, ticker: str, month: str, fetched_at: datetime, raw_sha256: str) -> ParsedMonth:
    data = decode_json(body)
    if data.get("stat") != "OK":
        raise HistoryDataError(f"TWSE 查詢失敗：{data.get('stat')}")
    if str(data.get("date")) != month_start(month).strftime("%Y%m%d"):
        raise HistoryDataError("TWSE 回傳查詢日期不符")
    title = str(data.get("title", ""))
    if ticker not in title.split():
        raise HistoryDataError("TWSE 回傳股票與請求不一致")
    return parse_table(fields=data.get("fields"), rows=data.get("data"), notes=data.get("notes"),
                       market="TWSE", ticker=ticker, month=month, fetched_at=fetched_at,
                       raw_sha256=raw_sha256, source_key="TWSE_STOCK_DAY")
