"""CSV 4.0 每日價量的白名單覆蓋與基本格式核對；不產生正式快照。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from uuid import uuid4

from etf_agent.universe import Universe


PRICE_CSV_COLUMNS = (
    "trade_date", "ticker", "market", "open_ktwd_per_lot", "high_ktwd_per_lot",
    "low_ktwd_per_lot", "close_raw_ktwd_per_lot", "return_close_ktwd_per_lot",
    "volume_lots", "amount_ktwd", "avg_price_ktwd_per_lot", "source_key",
    "known_at", "fetched_at", "data_version", "adjustment_status", "price_valid",
    "tradable", "reported_volume_lots", "reported_amount_ktwd",
    "reported_avg_price_ktwd_per_lot", "exact_volume_amount",
)
PRICE_COLUMNS = PRICE_CSV_COLUMNS[3:8]
NUMERIC_COLUMNS = (*PRICE_COLUMNS, "volume_lots", "amount_ktwd", "avg_price_ktwd_per_lot",
                   "reported_volume_lots", "reported_amount_ktwd", "reported_avg_price_ktwd_per_lot")


class PriceCoverageError(ValueError):
    """無法讀取指定日期或 CSV 格式，不能建立有效的覆蓋報告。"""


def _trade_date(value: date | str) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise PriceCoverageError("資料日期須為有效 YYYY-MM-DD")


def _check_values(row: dict, line: int) -> tuple[bool, dict, list[dict]]:
    errors: list[dict] = []

    def error(code: str, message: str, field: str):
        errors.append({"row": line, "ticker": row["ticker"], "code": code,
                       "message": message, "field": field})

    numbers: dict[str, Decimal | None] = {}
    for field in NUMERIC_COLUMNS:
        value = row[field]
        numbers[field] = None
        if value == "":
            continue
        try:
            number = Decimal(value)
            if not number.is_finite():
                raise InvalidOperation
            is_price = field in PRICE_COLUMNS or "avg_price" in field
            if number < 0 or (is_price and number == 0):
                raise InvalidOperation
            numbers[field] = number
        except InvalidOperation:
            error("numeric_value", f"{field} 須為有限數值；價格大於零、量值非負，未知留空", field)

    flags = {}
    for field in ("price_valid", "tradable", "exact_volume_amount"):
        flags[field] = row[field] == "true"
        if row[field] not in ("true", "false"):
            error("boolean_value", f"{field} 須為 true 或 false", field)
    for field in ("source_key", "data_version"):
        if not row[field].strip():
            error("missing_metadata", f"{field} 不可空白", field)
    if row["adjustment_status"] not in ("raw", "adjusted", "unresolved"):
        error("adjustment_status", "adjustment_status 須為 raw、adjusted 或 unresolved", "adjustment_status")
    for field in ("known_at", "fetched_at"):
        value = row[field]
        if value == "" and field == "known_at":
            continue
        try:
            if not re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T", value):
                raise ValueError
            timestamp = datetime.fromisoformat(value)
            if timestamp.utcoffset() != timedelta(hours=8):
                raise ValueError
        except ValueError:
            error("timestamp", f"{field} 須為有效含 +08:00 時區的 ISO 時間", field)

    close = numbers["close_raw_ktwd_per_lot"]
    high, low = numbers["high_ktwd_per_lot"], numbers["low_ktwd_per_lot"]
    if flags["price_valid"] and close is None:
        error("price_flag", "price_valid=true 須有有效原始收盤價", "price_valid")
    if high is not None and low is not None:
        if high < low or any(value is not None and not low <= value <= high
                             for value in (numbers["open_ktwd_per_lot"], close)):
            error("ohlc", "最高價不得低於最低價，開盤／收盤須在高低價之間", "close_raw_ktwd_per_lot")
    if flags["tradable"] and (not flags["price_valid"] or close is None):
        error("tradable_flag", "tradable=true 須有有效價格", "tradable")
    for prefix in ("", "reported_"):
        volume, amount = numbers[prefix + "volume_lots"], numbers[prefix + "amount_ktwd"]
        if (volume is None) != (amount is None):
            error("volume_amount_pair", "成交量／金額須同時提供或同時留空", prefix + "amount_ktwd")
        if volume == 0 and amount is not None and amount > 0:
            error("zero_volume", "零成交量不可有正成交金額", prefix + "amount_ktwd")

    price_errors = any(issue["field"] in (*PRICE_COLUMNS, "price_valid") for issue in errors)
    valid_price = flags["price_valid"] and close is not None and not price_errors
    return valid_price, flags, errors


def check_daily_prices(
    csv_path: Path | str, *, trade_date: date | str, universe: Universe,
) -> dict:
    """同日、白名單內、正市場且唯一的列算已取得，另統計有效價格。

    缺值保持缺值。重複列全部排除，不自行取一筆。列錯誤保留在報告；
    缺檔、無法辨識的標頭或 CSV 語法則拋 PriceCoverageError。
    """
    expected_date = _trade_date(trade_date).isoformat()
    csv_path = Path(csv_path).resolve()
    try:
        content = csv_path.read_bytes()
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        if next(reader, None) != list(PRICE_CSV_COLUMNS):
            raise PriceCoverageError("日表須使用 CSV 4.0 的 22 欄標頭；請傳入整理後每日檔")
        rows = [(reader.line_num, cells) for cells in reader if cells]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PriceCoverageError(f"每日 CSV 讀取失敗：{exc}") from exc

    stocks = {stock.ticker: stock for stock in universe.stocks}
    errors: list[dict] = []
    candidates: dict[str, tuple[dict, bool, dict]] = {}
    seen = Counter()
    unexpected: set[str] = set()

    def error(line: int, ticker: str, code: str, message: str):
        errors.append({"row": line, "ticker": ticker, "code": code, "message": message})

    for line, cells in rows:
        if len(cells) > 1 and cells[0] == expected_date:
            seen[cells[1]] += 1
            if seen[cells[1]] > 1:
                error(line, cells[1], "duplicate", "同日同股票有重複列，整組排除")
        if len(cells) != len(PRICE_CSV_COLUMNS):
            error(line, cells[1] if len(cells) > 1 else "", "column_count", "此列欄位數須為 22")
            continue
        row = dict(zip(PRICE_CSV_COLUMNS, cells))
        ticker = row["ticker"]
        if row["trade_date"] != expected_date:
            error(line, ticker, "trade_date", f"資料日期須為 {expected_date}，收到 {row['trade_date']}")
            continue
        stock = stocks.get(ticker)
        if stock is None:
            unexpected.add(ticker)
            error(line, ticker, "outside_universe", "代號格式錯誤或不在 F05 白名單")
            continue
        if row["market"] != stock.market:
            error(line, ticker, "market", f"F05 市場為 {stock.market}，收到 {row['market']}")
            continue
        valid_price, flags, row_errors = _check_values(row, line)
        errors.extend(row_errors)
        candidates[ticker] = (row, valid_price, flags)

    duplicates = {ticker for ticker, count in seen.items() if count > 1}
    present = set(candidates) - duplicates
    valid_prices = {ticker for ticker in present if candidates[ticker][1]}
    missing = set(stocks) - present
    warning_specs = (
        ("known_at_missing", "公開可知時間未核實", lambda row, flags: not row["known_at"]),
        ("adjustment_unresolved", "公司行動／報酬計算用價格尚未核實", lambda row, flags: row["adjustment_status"] == "unresolved"),
        ("not_tradable", "原列 tradable=false；未判定正式可交易", lambda row, flags: not flags["tradable"]),
        ("reported_precision", "來源量值精度未核實，reported 值維持報表精度", lambda row, flags: not flags["exact_volume_amount"]),
        ("close_missing", "原始收盤價留空，尚無有效收盤", lambda row, flags: not row["close_raw_ktwd_per_lot"]),
    )
    warnings = []
    for code, message, condition in warning_specs:
        tickers = sorted(ticker for ticker in present if condition(candidates[ticker][0], candidates[ticker][2]))
        if tickers:
            warnings.append({"code": code, "message": message, "tickers": tickers})
    with localcontext() as context:
        context.prec = 50
        percent = (Decimal(len(present)) * 100 / len(stocks)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    by_market = {}
    for market in ("TWSE", "TPEX"):
        expected = {ticker for ticker, stock in stocks.items() if stock.market == market}
        by_market[market] = {"expected_count": len(expected), "present_count": len(expected & present),
                             "valid_price_count": len(expected & valid_prices), "missing_count": len(expected & missing)}
    return {
        "report_format_version": "1.0", "scope": "daily_price_coverage", "csv_format_version": "4.0",
        "trade_date": expected_date, "input_csv": str(csv_path),
        "input_csv_sha256": hashlib.sha256(content).hexdigest(),
        "universe_version": universe.universe_version, "universe_csv_sha256": universe.csv_sha256,
        "universe_source_sha256": universe.source_sha256,
        "row_count": len(rows), "expected_count": len(stocks), "present_count": len(present),
        "valid_price_count": len(valid_prices),
        "tradable_flag_count": sum(candidates[ticker][2]["tradable"] for ticker in present),
        "missing_count": len(missing), "coverage_percent": str(percent),
        "present_tickers": sorted(present), "missing_tickers": sorted(missing),
        "missing_stocks": [{"ticker": ticker, "name": stocks[ticker].name, "market": stocks[ticker].market}
                           for ticker in sorted(missing)],
        "duplicate_tickers": sorted(duplicates), "unexpected_tickers": sorted(unexpected),
        "by_market": by_market, "input_valid": not errors,
        "coverage_complete": not missing and not errors, "errors": errors, "warnings": warnings,
        "submission_ready": False,
        "checks_not_performed": ["行情原始來源hash", "交易日曆與盤前截止", "公司行動", "21日因子視窗",
                                 "歷史時點股票池", "帳戶及正式交易驗證"],
    }


def write_coverage_report(report: dict, output_dir: Path | str) -> dict:
    """保存一次新的報告版本，不覆寫輸入 CSV 或既有報告。"""
    created_at = datetime.now(timezone(timedelta(hours=8)))
    run_id = created_at.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / report["trade_date"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    stored = {**report, "created_at": created_at.isoformat(), "run_id": run_id}
    report_json, missing_csv = (run_dir / name for name in ("coverage.json", "missing_stocks.csv"))
    report_json.write_text(json.dumps(stored, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    with missing_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("ticker", "name", "market"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["missing_stocks"])
    return {"run_dir": str(run_dir), "report_json": str(report_json), "missing_csv": str(missing_csv)}
