"""兩檔官方歷史樣本：下載、保存原始證據及可閱讀 CSV，不做投資決策。"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from etf_agent.contracts import PriceBar
from etf_agent.providers import tpex, twse
from etf_agent.providers.http import DownloadError, HttpResponse, get_https
from etf_agent.providers.monthly import HistoryDataError, month_start


SAMPLE_SYMBOLS = (("TWSE", "2330", twse), ("TPEX", "5274", tpex))
CSV_FORMAT_VERSION = "4.0"
PRICE_COLUMNS = {name: name + "_ktwd_per_lot" for name in ("open", "high", "low", "close_raw", "return_close")}
CSV_COLUMN_NAMES = {**PRICE_COLUMNS, "volume_shares": "volume_lots", "amount_twd": "amount_ktwd"}
EXTRA_COLUMNS = ("reported_volume_lots", "reported_amount_ktwd", "reported_avg_price_ktwd_per_lot",
                 "exact_volume_amount")


def _thousands(value) -> str | None:
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 50
        return str(Decimal(value) / Decimal(1000))


def _average_price_ktwd_per_lot(amount_twd, volume_shares) -> str | None:
    """千元／張與元／股數值相同；8位小數僅供閱讀，正式計算須重讀原始量值。"""
    if amount_twd is None or volume_shares is None or Decimal(volume_shares) <= 0:
        return None
    with localcontext() as context:
        context.prec = 50
        average = Decimal(amount_twd) / Decimal(volume_shares)
        return format(average.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP), "f")


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_prices(path: Path, rows: list[dict]):
    # BOM 讓 Windows Excel 可辨識 UTF-8；未知數值用空欄，並在 manifest 解釋。
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        columns = []
        for field in fields(PriceBar):
            if field.name == "raw_sha256":
                continue
            columns.append(CSV_COLUMN_NAMES.get(field.name, field.name))
            if field.name == "amount_twd":
                columns.append("avg_price_ktwd_per_lot")
        writer = csv.DictWriter(handle, fieldnames=columns + list(EXTRA_COLUMNS))
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["avg_price_ktwd_per_lot"] = _average_price_ktwd_per_lot(csv_row["amount_twd"], csv_row["volume_shares"])
            csv_row["reported_avg_price_ktwd_per_lot"] = _average_price_ktwd_per_lot(csv_row["reported_amount_twd"], csv_row["reported_volume_shares"])
            for original, renamed in PRICE_COLUMNS.items():
                # 元／股 × 1000股／張 ÷ 1000元／千元，數值相同，欄名明示單位。
                csv_row[renamed] = csv_row.pop(original)
            csv_row["volume_lots"] = _thousands(csv_row.pop("volume_shares"))
            csv_row["amount_ktwd"] = _thousands(csv_row.pop("amount_twd"))
            csv_row["reported_volume_lots"] = _thousands(csv_row.pop("reported_volume_shares"))
            csv_row["reported_amount_ktwd"] = _thousands(csv_row.pop("reported_amount_twd"))
            csv_row.pop("source_url", None)
            csv_row.pop("raw_sha256", None)
            csv_row.pop("source_volume_unit", None)
            csv_row.pop("source_amount_unit", None)
            writer.writerow({key: str(value).lower() if isinstance(value, bool) else value
                             for key, value in csv_row.items()})


def _write_daily_prices(run_dir: Path, month: str, rows: list[dict]) -> list[dict]:
    """把同一清洗結果依資料日分組，不補未回傳日期或缺少的股票。"""
    by_date, seen = {}, set()
    for row in rows:
        key = (row["trade_date"], row["ticker"])
        if key in seen:
            raise HistoryDataError("同股同日資料重複，停止建立每日價量表")
        seen.add(key)
        by_date.setdefault(row["trade_date"], []).append(row)
    daily_dir = run_dir / "daily" / month
    daily_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for day in sorted(by_date):
        day_rows = sorted(by_date[day], key=lambda row: (row["ticker"], row["market"]))
        path = daily_dir / (day + "_prices.csv")
        _write_prices(path, day_rows)
        entries.append({"trade_date": day, "prices_csv": path.relative_to(run_dir).as_posix(),
                        "row_count": len(day_rows)})
    return entries


def download_history_sample(month: str, output: Path, *, transport: str = "auto", fetcher=None) -> dict:
    return _export_sample(month, output, transport=transport, fetcher=fetcher or get_https)


def _export_sample(month: str, output: Path, *, transport: str, fetcher, reexport_of: dict | None = None) -> dict:
    requested = month_start(month)
    now = datetime.now(timezone(timedelta(hours=8)))
    if requested >= now.date().replace(day=1):
        raise HistoryDataError("樣本只接受已完成月份，不以當月或未來資料冒充完整月報")
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = output / month / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "raw").mkdir()
    (run_dir / "source_csv").mkdir()
    monthly_dir = run_dir / "monthly" / month
    monthly_dir.mkdir(parents=True)
    entries, all_rows = [], []
    for market, ticker, adapter in SAMPLE_SYMBOLS:
        filename = f"{market}_{ticker}_{month}"
        url = adapter.history_url(ticker, month)
        entry = {"market": market, "ticker": ticker, "requested_month": month,
                 "requested_url": url, "history_page": adapter.HISTORY_PAGE, "status": "failed"}
        time_field = "reexported_at" if reexport_of else "requested_at"
        entry[time_field] = datetime.now(timezone(timedelta(hours=8))).isoformat()
        try:
            response = fetcher(url, transport=transport, timeout=10)
            digest = hashlib.sha256(response.body).hexdigest()
            raw_path = run_dir / "raw" / (filename + ".json")
            raw_path.write_bytes(response.body)
            entry.update({"effective_url": response.url, "http_status": response.status,
                          "content_type": response.content_type, "fetched_at": response.fetched_at.isoformat(),
                          "transport": response.transport, "raw_sha256": digest,
                          "raw_path": raw_path.relative_to(run_dir).as_posix()})
            if response.status != 200:
                raise HistoryDataError(f"HTTP {response.status}；原始回應已保存，不轉為行情")
            if urlsplit(response.url).hostname != urlsplit(url).hostname:
                raise HistoryDataError("官方端點導向其他主機，需重新核對來源")
            if "json" not in response.content_type.lower():
                raise HistoryDataError("HTTP 回應未宣告 JSON；拒絕 HTML／其他內容")
            parsed = adapter.parse_month(response.body, ticker=ticker, month=month,
                                         fetched_at=response.fetched_at, raw_sha256=digest)
            rows = []
            for bar, (volume, amount) in zip(parsed.bars, parsed.reported_quantities, strict=True):
                row = bar.to_dict()
                row.update({"reported_volume_shares": None if volume is None else str(volume),
                            "reported_amount_twd": None if amount is None else str(amount),
                            "source_volume_unit": parsed.volume_unit, "source_amount_unit": parsed.amount_unit,
                            "exact_volume_amount": parsed.exact_volume_amount})
                rows.append(row)
            monthly_csv = monthly_dir / (filename + ".csv")
            _write_prices(monthly_csv, rows)
            source_csv = run_dir / "source_csv" / month / (filename + "_source.csv")
            source_csv.parent.mkdir(parents=True, exist_ok=True)
            with source_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(parsed.fields)
                writer.writerows(parsed.source_rows)
            entry.update({"status": "success", "row_count": len(rows),
                          "first_trade_date": parsed.bars[0].trade_date.isoformat(),
                          "last_trade_date": parsed.bars[-1].trade_date.isoformat(),
                          "fields": list(parsed.fields), "notes": list(parsed.notes),
                          "data_version": parsed.bars[0].data_version,
                          "units": {"source_volume": parsed.volume_unit, "source_amount": parsed.amount_unit,
                                    "prices": "TWD", "reported_conversion": "乘1000" if not parsed.exact_volume_amount else "原始股／元"},
                          "exact_volume_amount": parsed.exact_volume_amount,
                          "prices_csv": monthly_csv.relative_to(run_dir).as_posix(),
                          "source_csv": source_csv.relative_to(run_dir).as_posix()})
            all_rows.extend(rows)
        except (DownloadError, HistoryDataError, OSError) as exc:
            entry["error"] = str(exc)
        entries.append(entry)
    daily_prices = _write_daily_prices(run_dir, month, all_rows)
    success = all(entry["status"] == "success" for entry in entries)
    quality = {
        "scope": "two_symbol_historical_download_sample", "success": success,
        "rows": len(all_rows), "requested_month": month, "synthetic_data": False,
        "daily_file_count": len(daily_prices),
        "monthly_file_count": sum(entry["status"] == "success" for entry in entries),
        "checks": {"response_month_and_ticker_verified": success, "OHLC_basic_checked": success,
                   "calendar_completeness_verified": False, "corporate_actions_verified": False,
                   "historical_known_at_verified": False, "all_150_symbols_covered": False},
        "limitations": ["只有2330與5274的一個月報，不是完整白名單或回測資料集",
                        "TPEx月報以整數張／仟元揭示且不含鉅額；reported欄位僅換算，精確量值留空",
                        "均價以量值比計算；TPEx只列報表估算均價，精確均價留空",
                        "均價固定8位小數僅供閱讀；兩市場成交統計口徑不同，不能用此CSV作正式結算",
                        "今天補抓的月報無法證明歷史發布時間與修正版；known_at留空",
                        "未核實交易日曆與公司行動；return_close留空、tradable=false"],
        "submission_ready": False,
    }
    _write_json(run_dir / "data_quality.json", quality)
    manifest = {"format_version": "1.0", "csv_format_version": CSV_FORMAT_VERSION,
                "csv_units": {"volume_lots": "張（1000股）", "reported_volume_lots": "張（報表換算）",
                              "prices": "新臺幣千元／張（1張=1000股）",
                              "amount_ktwd": "新臺幣千元", "reported_amount_ktwd": "新臺幣千元（報表換算）",
                              "avg_price_ktwd_per_lot": "新臺幣千元／張（精確量值比，閱讀顯示8位小數）",
                              "reported_avg_price_ktwd_per_lot": "新臺幣千元／張（報表量值比，縮位來源為估算）"},
                "csv_average_rounding": {"decimal_places": 8, "mode": "ROUND_HALF_UP", "purpose": "readable_display_only"},
                "run_id": run_id, "requested_month": month,
                "created_at": now.isoformat(), "success": success,
                "data_origin": "official_historical_download",
                "purpose": "offline_cached_export" if reexport_of else "download_and_read_sample",
                "network_requests": 0 if reexport_of else len(entries),
                "csv_encoding": "UTF-8 with BOM", "csv_null": "empty field", "submission_ready": False,
                "source_count": len(entries), "sources": entries, "daily_prices": daily_prices,
                "price_views": {"preferred_input": "daily", "monthly_use": "inspection",
                                "same_cleaned_input": True, "combine_views": False},
                "quality_report": "data_quality.json"}
    if reexport_of:
        manifest["reexport_of"] = reexport_of
    _write_json(run_dir / "manifest.json", manifest)
    return {"success": success, "run_dir": str(run_dir.resolve()),
            "daily_dir": str((run_dir / "daily" / month).resolve()),
            "monthly_dir": str(monthly_dir.resolve()),
            "daily_prices": [{**entry, "prices_csv": str((run_dir / entry["prices_csv"]).resolve())}
                             for entry in daily_prices],
            "manifest": str((run_dir / "manifest.json").resolve()), "row_count": len(all_rows), "sources": entries}


def export_history_sample(manifest: Path, output: Path) -> dict:
    """僅從已保存的官方 JSON 匯出；驗證 hash，不重新連網或修改舊證據。"""
    try:
        manifest_path = manifest.resolve(strict=True)
        manifest_body = manifest_path.read_bytes()
        original = json.loads(manifest_body.decode("utf-8-sig"))
        if not isinstance(original, dict) or original.get("format_version") != "1.0" or original.get("success") is not True:
            raise HistoryDataError("離線重輸出須使用格式1.0且完整成功的來源 manifest")
        month = original["requested_month"]
        month_start(month)
        sources = original["sources"]
        if not isinstance(sources, list) or len(sources) != len(SAMPLE_SYMBOLS):
            raise HistoryDataError("來源 manifest 須完整包含兩檔樣本")
        expected = {(market, ticker): adapter for market, ticker, adapter in SAMPLE_SYMBOLS}
        cached, seen = {}, set()
        for source in sources:
            key = (source["market"], source["ticker"])
            if key not in expected or key in seen or source["status"] != "success":
                raise HistoryDataError("來源股票／市場／狀態不符或重複")
            seen.add(key)
            if source["requested_month"] != month or source["http_status"] != 200:
                raise HistoryDataError("來源月份或原 HTTP 狀態不符")
            raw_relative = Path(source["raw_path"])
            raw_path = (manifest_path.parent / raw_relative).resolve(strict=True)
            if raw_relative.is_absolute() or not raw_path.is_relative_to(manifest_path.parent):
                raise HistoryDataError("原始資料路徑超出來源目錄")
            body = raw_path.read_bytes()
            digest = hashlib.sha256(body).hexdigest()
            if digest != source["raw_sha256"]:
                raise HistoryDataError("原始資料 SHA-256 不符，停止離線匯出")
            fetched_at = datetime.fromisoformat(source["fetched_at"])
            adapter = expected[key]
            requested_url = adapter.history_url(key[1], month)
            if source["requested_url"] != requested_url:
                raise HistoryDataError("來源請求網址與月份／股票不一致")
            # 先解析全部來源再建目錄；錯格式不會產生部分成功的 CSV。
            adapter.parse_month(body, ticker=key[1], month=month, fetched_at=fetched_at, raw_sha256=digest)
            response = HttpResponse(body, source["effective_url"], source["http_status"],
                                    source["content_type"], fetched_at, "cached_replay")
            if (urlsplit(response.url).scheme != "https"
                    or urlsplit(response.url).hostname != urlsplit(requested_url).hostname
                    or "json" not in response.content_type.lower()):
                raise HistoryDataError("來源網址／內容類型不符")
            cached[requested_url] = response
        replay = {"manifest_path": str(manifest_path),
                  "manifest_sha256": hashlib.sha256(manifest_body).hexdigest(), "run_id": original["run_id"]}
    except HistoryDataError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HistoryDataError(f"來源 manifest／原始資料無效：{exc}") from exc

    def read_cached(url, **kwargs):
        return cached[url]

    return _export_sample(month, output, transport="cached_replay", fetcher=read_cached, reexport_of=replay)
