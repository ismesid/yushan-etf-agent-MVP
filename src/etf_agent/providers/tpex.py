"""TPEx 個股月報：張／仟元僅作報表換算，不能假裝精確量值。"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from etf_agent.providers.monthly import HistoryDataError, ParsedMonth, decode_json, month_start, parse_table, validate_ticker


HISTORY_PAGE = "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/stock-pricing.html"


def history_url(ticker: str, month: str) -> str:
    validate_ticker(ticker)
    day = month_start(month)
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?" + urlencode(
        {"code": ticker, "date": day.strftime("%Y/%m/%d"), "response": "json"})


def parse_month(body: bytes, *, ticker: str, month: str, fetched_at: datetime, raw_sha256: str) -> ParsedMonth:
    data = decode_json(body)
    if str(data.get("stat", "")).lower() != "ok":
        raise HistoryDataError(f"TPEx 查詢失敗：{data.get('stat')}")
    requested = month_start(month).strftime("%Y%m%d")
    if data.get("date") != requested or str(data.get("code")) != ticker:
        raise HistoryDataError("TPEx 回傳查詢日期／股票不符")
    tables = data.get("tables")
    if not isinstance(tables, list) or len(tables) != 1 or not isinstance(tables[0], dict):
        raise HistoryDataError("TPEx 月報表格結構改變，需重新核對")
    table = tables[0]
    if table.get("date") != requested:
        raise HistoryDataError("TPEx 表格查詢日期不符")
    return parse_table(fields=table.get("fields"), rows=table.get("data"), notes=table.get("notes"),
                       market="TPEX", ticker=ticker, month=month, fetched_at=fetched_at,
                       raw_sha256=raw_sha256, source_key="TPEX_TRADING_STOCK_MONTH")
