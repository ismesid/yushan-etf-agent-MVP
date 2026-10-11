"""TWSE／TPEx 指定單日全市場行情；不呼叫網路、不查月報。

成交金額與成交股數保留精確原量值。均價由元／股重算，使用50位
Decimal精度，不把網站顯示的四捨五入均價或揭示買賣量當作成交資料。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlencode


class DailyQuotesError(ValueError):
    """指定單日回應的日期、單位、結構或數值無法核對。"""


_NUMBER = re.compile(r"\+?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?")
_MISSING = {"", "-", "--", "---", "----", "N/A", "NA", "NULL", "不適用"}
_SOURCES = {"TWSE": "TWSE_MI_INDEX_DAY", "TPEX": "TPEX_DAILY_QUOTES"}


def _request(market: str, trade_date: str) -> tuple[str, date]:
    if not isinstance(market, str) or market.upper() not in _SOURCES:
        raise DailyQuotesError("market 必須是 TWSE 或 TPEX")
    if not isinstance(trade_date, str):
        raise DailyQuotesError("trade_date 必須是 YYYY-MM-DD")
    try:
        requested = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise DailyQuotesError("trade_date 必須是有效 YYYY-MM-DD") from exc
    if requested.isoformat() != trade_date:
        raise DailyQuotesError("trade_date 必須是 YYYY-MM-DD")
    return market.upper(), requested


def daily_url(market: str, trade_date: str) -> str:
    """明確指定一天，不省略日期，也不使用個股月報入口。"""
    market, requested = _request(market, trade_date)
    if market == "TWSE":
        return "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?" + urlencode(
            {"date": requested.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"})
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?" + urlencode(
        {"date": requested.strftime("%Y/%m/%d"), "response": "json"})


def _nonnegative_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise DailyQuotesError(f"{field} 數值型別不符")
    text = str(value).strip()
    if text.upper() in _MISSING:
        return None
    if not _NUMBER.fullmatch(text):
        raise DailyQuotesError(f"{field} 不是可核對的非負十進位數")
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise DailyQuotesError(f"{field} 數值無效") from exc
    if not number.is_finite() or number < 0:
        raise DailyQuotesError(f"{field} 數值無效")
    return number


def _positive_decimal(value: object, field: str) -> Decimal | None:
    number = _nonnegative_decimal(value, field)
    return number if number is not None and number > 0 else None


def _invalid_constant(value: str):
    raise DailyQuotesError(f"JSON 包含非有限數值 {value}")


def _table_date(value: object) -> date:
    """官方表格日期只接受YYYYMMDD或已核對的民國YYY/MM/DD。"""
    if not isinstance(value, str):
        raise DailyQuotesError("股票行情表格日期格式不符")
    if re.fullmatch(r"\d{8}", value):
        parts = (int(value[:4]), int(value[4:6]), int(value[6:8]))
    elif re.fullmatch(r"\d{3}/\d{2}/\d{2}", value):
        year, month, day = map(int, value.split("/"))
        parts = (year + 1911, month, day)
    else:
        raise DailyQuotesError("股票行情表格日期格式不符")
    try:
        return date(*parts)
    except ValueError as exc:
        raise DailyQuotesError("股票行情表格日期無效") from exc


def parse_daily(body: bytes | str, market: str, trade_date: str) -> dict[str, dict]:
    """回傳以ticker索引的行情；未知量值為None，缺成交不補零或沿用。

    僅接受回應date與請求日完全相同。所有股票行情表均檢查，重碼直接
    拒絕，不依表格索引猜欄位，也不接受仟元／仟股等近似量值。
    """
    market, requested = _request(market, trade_date)
    if not isinstance(body, (bytes, str)):
        raise DailyQuotesError("行情body必須為原始bytes或JSON文字")
    raw = body if isinstance(body, bytes) else body.encode("utf-8")
    try:
        payload = json.loads(raw.decode("utf-8-sig"), parse_float=Decimal,
                             parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyQuotesError("官方單日回應不是有效UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise DailyQuotesError("官方單日回應必須為JSON物件")
    if str(payload.get("stat", "")).lower() != "ok":
        raise DailyQuotesError("官方單日行情查詢未成功")
    expected_date = requested.strftime("%Y%m%d")
    if payload.get("date") != expected_date:
        raise DailyQuotesError("官方單日回傳日期與請求不符")
    params = payload.get("params")
    if params is not None and (not isinstance(params, dict) or params.get("date") != expected_date):
        raise DailyQuotesError("官方單日查詢參數日期不符")
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise DailyQuotesError("官方單日tables結構改變")
    code_field, name_field, close_field, amount_field = (
        ("證券代號", "證券名稱", "收盤價", "成交金額") if market == "TWSE"
        else ("代號", "名稱", "收盤", "成交金額(元)"))
    required = {code_field, name_field, close_field, "成交股數", amount_field}
    source_url = daily_url(market, trade_date)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    quotes: dict[str, dict] = {}
    matched = 0
    for table in tables:
        if not isinstance(table, dict):
            raise DailyQuotesError("官方單日table必須為物件")
        fields = table.get("fields")
        if not isinstance(fields, list) or code_field not in fields:
            continue
        matched += 1
        if any(not isinstance(field, str) for field in fields) or len(set(fields)) != len(fields):
            raise DailyQuotesError("股票行情欄位型別或重複欄位不符")
        if not required.issubset(fields):
            raise DailyQuotesError("股票行情缺必要欄位或成交量／金額單位改變")
        if market == "TWSE" and table.get("hints") != "單位：元、股":
            raise DailyQuotesError("TWSE 股票行情須明確標示單位：元、股")
        rows = table.get("data")
        if not isinstance(rows, list):
            raise DailyQuotesError("股票行情data結構改變")
        returned_date = table.get("date")
        if returned_date is None and not rows:
            continue
        if returned_date is not None and _table_date(returned_date) != requested:
            raise DailyQuotesError("股票行情表格日期不符")
        title_date = re.search(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日", str(table.get("title", "")))
        if title_date:
            year, month, day = map(int, title_date.groups())
            if (year + 1911, month, day) != (requested.year, requested.month, requested.day):
                raise DailyQuotesError("股票行情表格標題日期不符")
        # TPEx日期來自table.date；TWSE實際回應則由含日期的title核對。
        if returned_date is None and (market == "TPEX" or title_date is None):
            raise DailyQuotesError("有資料的股票行情表格缺少日期證據")
        indexes = {field: fields.index(field) for field in required}
        for row in rows:
            if not isinstance(row, list) or len(row) != len(fields):
                raise DailyQuotesError("股票行情列寬與fields不符")
            ticker = row[indexes[code_field]]
            if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z0-9]+", ticker.strip()):
                raise DailyQuotesError("股票代號格式不符")
            ticker = ticker.strip()
            if ticker in quotes:
                raise DailyQuotesError(f"單日行情重複股票代號：{ticker}")
            close = _positive_decimal(row[indexes[close_field]], f"{ticker} close")
            reported_amount = _nonnegative_decimal(row[indexes[amount_field]], f"{ticker} amount_twd")
            reported_volume = _nonnegative_decimal(row[indexes["成交股數"]], f"{ticker} volume_shares")
            if reported_volume is not None and reported_volume != reported_volume.to_integral_value():
                raise DailyQuotesError(f"{ticker} 成交股數必須是整數股")
            if ((reported_volume == 0 and reported_amount is not None and reported_amount > 0)
                    or (reported_amount == 0 and reported_volume is not None and reported_volume > 0)):
                raise DailyQuotesError(f"{ticker} 零成交股數與成交金額不一致")
            if reported_volume == 0 and reported_amount == 0:
                trading_status = "no_trade"
            elif (reported_volume is not None and reported_volume > 0
                  and reported_amount is not None and reported_amount > 0):
                trading_status = "traded"
            else:
                trading_status = "unknown"
            amount = reported_amount if reported_amount is not None and reported_amount > 0 else None
            volume = reported_volume if reported_volume is not None and reported_volume > 0 else None
            with localcontext() as context:
                context.prec = 50
                vwap = amount / volume if amount is not None and volume is not None else None
            quotes[ticker] = {
                "ticker": ticker, "name": row[indexes[name_field]], "market": market,
                "trade_date": trade_date,
                "close_twd_per_share": format(close, "f") if close is not None else None,
                "volume_shares": int(volume) if volume is not None else None,
                "amount_twd": format(amount, "f") if amount is not None else None,
                "vwap_twd_per_share": format(vwap, "f") if vwap is not None else None,
                "trading_status": trading_status,
                "source_key": _SOURCES[market], "source_url": source_url, "raw_sha256": raw_sha256,
            }
    if not matched or not quotes:
        raise DailyQuotesError("單日回應沒有可核對的股票行情")
    return quotes
