"""官方歷史月報共同解析；保留報表精度與未知的當時可知時間。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from etf_agent.contracts import ContractError, PriceBar


class HistoryDataError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedMonth:
    bars: tuple[PriceBar, ...]
    fields: tuple[str, ...]
    source_rows: tuple[tuple[str, ...], ...]
    notes: tuple[str, ...]
    volume_unit: str
    amount_unit: str
    exact_volume_amount: bool
    reported_quantities: tuple[tuple[Decimal | None, Decimal | None], ...]


def month_start(month: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month):
        raise HistoryDataError("月份須為 YYYY-MM")
    try:
        return date.fromisoformat(month + "-01")
    except ValueError as exc:
        raise HistoryDataError("月份不存在") from exc


def validate_ticker(ticker: str):
    if not re.fullmatch(r"[0-9]{4}", ticker):
        raise HistoryDataError("股票代碼須為四位字串")


def decode_json(body: bytes) -> dict:
    try:
        value = json.loads(body.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HistoryDataError("官方回應不是 UTF-8 JSON，可能是 HTML 錯誤頁") from exc
    if not isinstance(value, dict):
        raise HistoryDataError("官方回應須為 JSON 物件")
    return value


def _number(value: str) -> Decimal | None:
    cleaned = value.replace(",", "").strip()
    if cleaned in {"", "--", "---", "----"}:
        return None
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise HistoryDataError(f"無法解析數字：{value!r}") from exc
    if not number.is_finite():
        raise HistoryDataError("數值不可為 NaN／Infinity")
    return number


def parse_table(*, fields, rows, notes, market: str, ticker: str, month: str,
                fetched_at: datetime, raw_sha256: str, source_key: str) -> ParsedMonth:
    validate_ticker(ticker)
    requested = month_start(month)
    if not isinstance(fields, list) or not all(isinstance(item, str) for item in fields):
        raise HistoryDataError("官方報表缺少欄位名稱")
    if not isinstance(rows, list) or not rows:
        raise HistoryDataError("查詢月份沒有行情")
    if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
        raise HistoryDataError("官方報表註記格式不符")
    names = [re.sub(r"\s+", "", name) for name in fields]
    if len(set(names)) != len(names):
        raise HistoryDataError("官方欄位名稱重複")
    column = {name: i for i, name in enumerate(names)}
    if market == "TWSE":
        required = ("日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價")
        volume_unit, amount_unit, factor, exact = "股", "元", Decimal(1), True
    elif market == "TPEX":
        required = ("日期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤")
        volume_unit, amount_unit, factor, exact = "張", "仟元", Decimal(1000), False
    else:
        raise HistoryDataError("不支援的市場")
    if not set(required) <= column.keys():
        raise HistoryDataError(f"{market} 月報欄位／單位不符：{fields}")
    bars, originals, quantities, seen = [], [], [], {}
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields) or not all(isinstance(item, str) for item in row):
            raise HistoryDataError("行情列長度／型別不符")
        try:
            year, mm, dd = map(int, row[column[required[0]]].strip().split("/"))
            day = date(year + 1911, mm, dd)
        except (ValueError, IndexError) as exc:
            raise HistoryDataError("無效民國交易日期") from exc
        if (day.year, day.month) != (requested.year, requested.month):
            raise HistoryDataError("回傳行情年月與請求不一致；禁止把最新行情當成歷史")
        original = tuple(row)
        if day in seen:
            if seen[day] == original:
                continue
            raise HistoryDataError("同股同日行情衝突；不得任選一列")
        seen[day] = original
        volume = _number(row[column[required[1]]])
        amount = _number(row[column[required[2]]])
        if any(value is not None and value < 0 for value in (volume, amount)):
            raise HistoryDataError("成交量值不可為負")
        if volume is not None and volume != volume.to_integral_value():
            raise HistoryDataError("月報股數／張數須為整數")
        if (volume is None) != (amount is None) or (volume == 0 and amount not in (0, None)):
            raise HistoryDataError("成交量值缺失或零成交不一致")
        converted_volume = None if volume is None else volume * factor
        converted_amount = None if amount is None else amount * factor
        prices = [_number(row[column[name]]) for name in required[3:]]
        try:
            bar = PriceBar(
                trade_date=day, ticker=ticker, market=market,
                open=prices[0], high=prices[1], low=prices[2], close_raw=prices[3],
                return_close=None,
                volume_shares=int(converted_volume) if exact and converted_volume is not None else None,
                amount_twd=converted_amount if exact else None,
                source_key=source_key, known_at=None, fetched_at=fetched_at,
                raw_sha256=raw_sha256, data_version="history-sample-v1-" + raw_sha256[:12],
                adjustment_status="unresolved", price_valid=prices[3] is not None, tradable=False,
            )
        except ContractError as exc:
            raise HistoryDataError(f"行情不合理：{exc}") from exc
        bars.append(bar)
        originals.append(original)
        quantities.append((converted_volume, converted_amount))
    order = sorted(range(len(bars)), key=lambda i: bars[i].trade_date)
    return ParsedMonth(tuple(bars[i] for i in order), tuple(fields),
                       tuple(originals[i] for i in order), tuple(notes), volume_unit,
                       amount_unit, exact, tuple(quantities[i] for i in order))
