"""按官方交易日曆檢查歷史價格視窗；不計因子或產生正式快照。"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from etf_agent.coverage import PRICE_COLUMNS, PriceCoverageError, check_daily_prices
from etf_agent.universe import Universe


REQUIRED_BARS = 21
WINDOW_CSV_COLUMNS = (
    "ticker", "name", "market", "required_bars",
    "valid_price_count", "missing_dates", "invalid_price_dates", "window_complete",
    "calendar_window_shortfall", "status", "calendar_basis", "input_valid",
    "submission_ready",
)


class HistoryWindowError(ValueError):
    """輸入索引或日曆無法辨識，不能建立價格視窗報告。"""


def _date(value: date | str, field: str) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise HistoryWindowError(f"{field} 須為有效 YYYY-MM-DD")


def _calendar_dates(calendar: dict, month: str, as_of: str) -> tuple[dict, dict]:
    if (not isinstance(calendar, dict) or calendar.get("format_version") != "1.0"
            or calendar.get("month") != month or not calendar.get("calendar_version")
            or not isinstance(calendar.get("markets"), dict)
            or not isinstance(calendar.get("sources"), list)):
        raise HistoryWindowError("日曆須為格式 1.0、同月份且包含版本、市場及來源索引")
    expected, markets = {}, {}
    for market in ("TWSE", "TPEX"):
        info = calendar["markets"].get(market)
        if (not isinstance(info, dict) or not isinstance(info.get("trade_dates"), list)
                or type(info.get("schedule_verified")) is not bool
                or type(info.get("actual_sessions_verified")) is not bool):
            raise HistoryWindowError(f"日曆 {market} 日期或確認狀態格式不符")
        days = [_date(value, f"{market}.trade_dates").isoformat() for value in info["trade_dates"]]
        if len(set(days)) != len(days) or any(day[:7] != month for day in days):
            raise HistoryWindowError(f"日曆 {market} 日期重複或跨月份")
        expected[market] = sorted(day for day in days if day <= as_of)[-REQUIRED_BARS:]
        markets[market] = {
            "schedule_verified": info["schedule_verified"],
            "actual_sessions_verified": info["actual_sessions_verified"],
            "calendar_basis": "official_actual_sessions" if info["actual_sessions_verified"] else "official_schedule",
        }
    return expected, markets


def _daily_index(manifest: dict, run_dir: Path, month: str) -> dict[str, Path]:
    if not isinstance(manifest.get("daily_prices"), list):
        raise HistoryWindowError("歷史 manifest 缺少 daily_prices 索引")
    indexed = {}
    for entry in manifest["daily_prices"]:
        if not isinstance(entry, dict):
            raise HistoryWindowError("daily_prices 每筆須為物件")
        day = _date(entry.get("trade_date"), "daily_prices.trade_date").isoformat()
        if day[:7] != month or day in indexed:
            raise HistoryWindowError("每日索引日期跨月份或重複")
        value = entry.get("prices_csv")
        if not isinstance(value, str) or not value.strip():
            raise HistoryWindowError("每日索引 prices_csv 須為相對路徑")
        relative = Path(value)
        path = (run_dir / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(run_dir):
            raise HistoryWindowError("每日價量路徑超出歷史 run 目錄")
        indexed[day] = path
    return indexed


def check_history_windows(
    manifest_path: Path | str, *, as_of: date | str, calendar: dict, universe: Universe,
) -> dict:
    """僅讀取日曆預期且不晚於資料截止日的日表；缺日缺股不補值。

    window_complete 只表示已提供日曆範圍內的 21 筆有效價格齊全；
    input_valid 另反映日表讀取及既有 coverage 的列診斷，不代表正式可交易。
    """
    cutoff = _date(as_of, "as_of").isoformat()
    month = cutoff[:7]
    try:
        path = Path(manifest_path).resolve(strict=True)
        body = path.read_bytes()
        manifest = json.loads(body.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HistoryWindowError(f"歷史 manifest 無法讀取：{exc}") from exc
    if (not isinstance(manifest, dict) or manifest.get("format_version") != "1.0"
            or manifest.get("csv_format_version") != "4.0"
            or manifest.get("requested_month") != month
            or manifest.get("universe_version") != universe.universe_version):
        raise HistoryWindowError("歷史 manifest 格式、CSV 版本、月份或白名單版本不符")
    expected, market_info = _calendar_dates(calendar, month, cutoff)
    indexed = _daily_index(manifest, path.parent, month)
    required_days = sorted(set(expected["TWSE"]) | set(expected["TPEX"]))
    daily_reports, daily_errors, missing_files = [], [], []
    present_by_day, valid_by_day, metadata_by_day = {}, {}, {}
    for day in required_days:
        csv_path = indexed.get(day)
        if csv_path is None or not csv_path.is_file():
            reason = "not_indexed" if csv_path is None else "file_missing"
            missing_files.append({"trade_date": day, "reason": reason,
                                  "prices_csv": None if csv_path is None else str(csv_path)})
            daily_reports.append({"trade_date": day, "status": reason, "errors": []})
            continue
        try:
            report = check_daily_prices(csv_path, trade_date=day, universe=universe)
            present = set(report["present_tickers"])
            price_errors = {issue["ticker"] for issue in report["errors"]
                            if issue.get("field") in (*PRICE_COLUMNS, "price_valid")}
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = {row["ticker"]: row for row in csv.DictReader(handle, strict=True)
                        if row.get("ticker") in present and row.get("trade_date") == day}
            valid = {ticker for ticker, row in rows.items()
                     if row["price_valid"] == "true" and row["close_raw_ktwd_per_lot"] != ""
                     and ticker not in price_errors}
            present_by_day[day], valid_by_day[day], metadata_by_day[day] = present, valid, rows
            daily_reports.append({**report, "status": "checked"})
            daily_errors.extend({"trade_date": day, **issue} for issue in report["errors"])
        except (PriceCoverageError, OSError, UnicodeError, csv.Error) as exc:
            issue = {"trade_date": day, "code": "daily_file_invalid", "message": str(exc)}
            daily_errors.append(issue)
            daily_reports.append({"trade_date": day, "status": "invalid_file",
                                  "input_csv": str(csv_path), "errors": [issue]})
    stocks = []
    for stock in sorted(universe.stocks, key=lambda item: item.ticker):
        days = expected[stock.market]
        shortfall = REQUIRED_BARS - len(days)
        missing = [day for day in days if stock.ticker not in present_by_day.get(day, set())]
        invalid = [day for day in days if stock.ticker in present_by_day.get(day, set())
                   and stock.ticker not in valid_by_day.get(day, set())]
        count = sum(stock.ticker in valid_by_day.get(day, set()) for day in days)
        complete = not shortfall and not missing and not invalid and market_info[stock.market]["schedule_verified"]
        if not market_info[stock.market]["schedule_verified"]:
            status = "calendar_unverified"
        elif shortfall:
            status = "calendar_window_shortfall"
        elif missing:
            status = "missing_prices"
        elif invalid:
            status = "invalid_prices"
        else:
            status = "complete"
        observed = [(day, metadata_by_day.get(day, {}).get(stock.ticker)) for day in days]
        observed = [(day, row) for day, row in observed if row is not None]
        stocks.append({
            "ticker": stock.ticker, "name": stock.name, "market": stock.market,
            "required_bars": REQUIRED_BARS, "expected_dates": days,
            "valid_price_count": count, "missing_dates": missing, "invalid_price_dates": invalid,
            "window_complete": complete, "calendar_window_shortfall": shortfall, "status": status,
            "calendar_basis": market_info[stock.market]["calendar_basis"],
            "source_metadata": {
                "source_keys": sorted({row["source_key"] for _, row in observed}),
                "data_versions": sorted({row["data_version"] for _, row in observed}),
                "fetched_at_values": sorted({row["fetched_at"] for _, row in observed}),
                "known_at_missing_dates": [day for day, row in observed if row["known_at"] == ""],
                "adjustment_unresolved_dates": [day for day, row in observed if row["adjustment_status"] == "unresolved"],
                "tradable_false_dates": [day for day, row in observed if row["tradable"] != "true"],
            },
        })
    complete_count = sum(stock["window_complete"] for stock in stocks)
    limitations = [
        "as_of 是已完成歷史資料的截止日，不是盤前決策日；本批不建立正式 MarketSnapshot",
        "僅按已提供月份的官方日曆檢查，不猜測更早月份交易日或補造缺日／缺價格",
        "有效價格沿用每日 coverage 口徑；窗口齊全與輸入格式通過分開記錄",
        "known_at、公司行動、return_close 與正式可交易狀態未核實；原價不能證明正式因子可用",
        "僅讀日表、不疊加月表；本批未逐份驗 raw hash、歷史股票池、帳戶或正式截止規則",
    ]
    if any(not info["actual_sessions_verified"] for info in market_info.values()):
        limitations.append("日曆依官方開休市排程；實際臨時休市尚未完全核實，calendar_basis=official_schedule")
    return {
        "report_format_version": "1.0", "scope": "historical_price_window_coverage",
        "as_of": cutoff, "requested_month": month, "required_bars": REQUIRED_BARS,
        "input_manifest": str(path), "input_manifest_sha256": hashlib.sha256(body).hexdigest(),
        "universe_version": universe.universe_version, "calendar_version": calendar["calendar_version"],
        "calendar_basis": "official_actual_sessions" if all(info["actual_sessions_verified"] for info in market_info.values()) else "official_schedule",
        "calendar_markets": market_info, "calendar_sources": calendar["sources"],
        "expected_dates_by_market": expected,
        "unread_future_dates": sorted(day for day in indexed if day > cutoff),
        "unused_indexed_dates": sorted(day for day in indexed if day <= cutoff and day not in required_days),
        "missing_day_files": missing_files, "daily_reports": daily_reports, "daily_errors": daily_errors,
        "input_valid": not daily_errors, "stocks": stocks,
        "summary": {"stock_count": len(stocks), "complete_stock_count": complete_count,
                    "incomplete_stock_count": len(stocks) - complete_count,
                    "status_counts": dict(Counter(stock["status"] for stock in stocks))},
        "limitations": limitations, "submission_ready": False,
    }


def write_window_report(report: dict, output_dir: Path | str) -> dict:
    """保存新的 JSON 與逐股閱讀 CSV，不覆寫輸入或舊報告。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / report["as_of"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    stored = {**report, "created_at": now.isoformat(), "run_id": run_id}
    report_json, report_csv = (run_dir / name for name in ("window_report.json", "window_coverage.csv"))
    report_json.write_text(json.dumps(stored, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8", newline="\n")
    with report_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WINDOW_CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for stock in report["stocks"]:
            row = {**stock, "input_valid": report["input_valid"], "submission_ready": False}
            writer.writerow({key: ";".join(value) if isinstance(value, list)
                             else str(value).lower() if isinstance(value, bool) else value
                             for key, value in row.items() if key in WINDOW_CSV_COLUMNS})
    return {"run_dir": str(run_dir), "report_json": str(report_json),
            "report_csv": str(report_csv)}
