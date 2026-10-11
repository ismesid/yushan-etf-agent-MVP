"""Read one validated historical market date for every agent; never fetch or value accounts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from etf_agent.coverage import PRICE_COLUMNS, PriceCoverageError, check_daily_prices
from etf_agent.universe import Universe


class PriceContextError(ValueError):
    """The requested date, provenance or saved price contents cannot be verified."""


def _date(value: date | str) -> str:
    if type(value) is date:
        return value.isoformat()
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise PriceContextError("估值日期須為有效 YYYY-MM-DD") from exc
    return value


def _read_json(path: Path) -> tuple[dict, bytes]:
    try:
        body = path.read_bytes()
        value = json.loads(body.decode("utf-8-sig"))
        if type(value) is not dict:
            raise PriceContextError(f"{path.name} 須為 JSON object")
        return value, body
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PriceContextError(f"JSON 讀取失敗：{path}: {exc}") from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _reference(base: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PriceContextError(f"缺少 {label} 路徑")
    return (base / value).resolve()


def _verify_hash(body: bytes, expected: object, label: str):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PriceContextError(f"{label} SHA-256 格式錯誤")
    if _sha256(body) != expected:
        raise PriceContextError(f"{label} hash 與既有歷史驗收不一致")


def load_history_closes(
    ranking_metadata_path: Path | str, *, as_of: date | str, universe: Universe,
) -> dict:
    """核對既有排名來源，只讀明確指定的唯一日表；不讀較晚日期或 raw。"""
    cutoff = _date(as_of)
    metadata_path = Path(ranking_metadata_path).resolve()
    metadata, metadata_body = _read_json(metadata_path)
    if (metadata.get("analysis_format_version") != "1.0"
            or metadata.get("scope") != "historical_raw_price_factor_ranking"
            or metadata.get("submission_ready") is not False):
        raise PriceContextError("只接受 1.0 歷史排名 metadata，不能當作正式行情快照")
    # 在解析 manifest／任何行情路徑前確認日期，避免讀入決策日或未來行情。
    if metadata.get("as_of") != cutoff:
        raise PriceContextError(f"排名資料截止日須為 {cutoff}，收到 {metadata.get('as_of')}")
    if metadata.get("universe_version") != universe.universe_version:
        raise PriceContextError("排名與 F05 白名單版本不一致")
    reference = metadata.get("input_manifest")
    if not isinstance(reference, dict):
        raise PriceContextError("排名缺少行情 manifest 引用")
    manifest_path = _reference(metadata_path.parent, reference.get("path"), "input_manifest")
    manifest, manifest_body = _read_json(manifest_path)
    _verify_hash(manifest_body, reference.get("sha256"), "行情 manifest")
    if (manifest.get("format_version") != "1.0" or manifest.get("csv_format_version") != "4.0"
            or manifest.get("requested_month") != cutoff[:7]
            or manifest.get("universe_version") != universe.universe_version):
        raise PriceContextError("行情 manifest 版本、月份或白名單不一致")
    indexed, validated = manifest.get("daily_prices"), metadata.get("daily_inputs")
    if not isinstance(indexed, list) or not isinstance(validated, list):
        raise PriceContextError("缺少日表索引或既有驗收 hash")
    entries = [item for item in indexed if isinstance(item, dict) and item.get("trade_date") == cutoff]
    checked = [item for item in validated if isinstance(item, dict) and item.get("trade_date") == cutoff]
    if len(entries) != 1 or len(checked) != 1:
        raise PriceContextError(f"{cutoff} 須有唯一日表及驗收紀錄")
    relative = entries[0].get("prices_csv")
    csv_path = _reference(manifest_path.parent, relative, "daily_prices.prices_csv")
    if Path(relative).is_absolute() or not csv_path.is_relative_to(manifest_path.parent):
        raise PriceContextError("日表路徑超出行情 run")
    if _reference(metadata_path.parent, checked[0].get("path"), "daily_inputs.path") != csv_path:
        raise PriceContextError("日表索引與排名驗收路徑不一致")
    try:
        body = csv_path.read_bytes()
    except OSError as exc:
        raise PriceContextError(f"日表讀取失敗：{exc}") from exc
    _verify_hash(body, checked[0].get("sha256"), "估值日表")
    try:
        coverage = check_daily_prices(csv_path, trade_date=cutoff, universe=universe)
        if coverage["input_csv_sha256"] != _sha256(body):
            raise PriceContextError("日表在讀取期間已變更")
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig")), strict=True))
    except (PriceCoverageError, UnicodeError, csv.Error) as exc:
        raise PriceContextError(f"歷史日表錯誤：{exc}") from exc
    if entries[0].get("row_count") != len(rows):
        raise PriceContextError("日表列數與 manifest 索引不一致")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise PriceContextError("manifest 缺少來源清單")
    source_index = {}
    for source in sources:
        if isinstance(source, dict) and source.get("status") == "success":
            key = source.get("source_key")
            if not isinstance(key, str) or not key or key in source_index:
                raise PriceContextError("manifest 成功來源 ID 缺失或重複")
            source_index[key] = source
    valid = set(coverage["present_tickers"])
    invalid_prices = {item["ticker"] for item in coverage["errors"]
                      if item.get("field") in (*PRICE_COLUMNS, "price_valid")}
    quotes = {}
    for row in rows:
        ticker = row.get("ticker")
        if row.get("trade_date") != cutoff or ticker not in valid:
            continue
        source = source_index.get(row["source_key"])
        if source is None or any(source.get(key) != row[key]
                                 for key in ("ticker", "market", "data_version", "fetched_at")):
            raise PriceContextError(f"{ticker} 的來源身分、版本或取得時間與 manifest 不一致")
        raw_hash = source.get("raw_sha256")
        if not isinstance(raw_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
            raise PriceContextError(f"{ticker} 的原始來源 hash 缺失")
        price_valid = (ticker not in invalid_prices
                       and row["price_valid"] == "true" and bool(row["close_raw_ktwd_per_lot"]))
        quotes[ticker] = {
            "trade_date": cutoff, "market": row["market"], "price_valid": price_valid,
            # 千元／張 × 1000 元／千元 ÷ 1000 股／張，數字恰與元／股相同。
            "close_twd_per_share": Decimal(row["close_raw_ktwd_per_lot"]) if price_valid else None,
            "source_key": row["source_key"], "data_version": row["data_version"],
            "known_at": row["known_at"] or None, "fetched_at": row["fetched_at"],
            "adjustment_status": row["adjustment_status"], "tradable": row["tradable"] == "true",
            "raw_sha256": raw_hash, "requested_url": source.get("requested_url"),
        }
    return {
        "as_of": cutoff, "stocks": {stock.ticker: {"name": stock.name, "market": stock.market}
                                     for stock in universe.stocks}, "quotes": quotes,
        "universe_version": universe.universe_version,
        "issues": [{"code": item["code"], "severity": "BLOCK", "ticker": item.get("ticker"),
                    "message": item["message"]} for item in coverage["errors"]],
        "inputs": {"ranking_metadata": {"path": str(metadata_path), "sha256": _sha256(metadata_body)},
                   "history_manifest": {"path": str(manifest_path), "sha256": _sha256(manifest_body)},
                   "daily_prices": {"path": str(csv_path), "sha256": _sha256(body), "trade_date": cutoff},
                   "universe_csv_sha256": universe.csv_sha256,
                   "universe_source_sha256": universe.source_sha256},
    }
