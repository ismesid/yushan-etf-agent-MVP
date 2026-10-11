"""以已驗收的歷史原價視窗計算分析因子，不建立正式交易快照。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from pathlib import Path
from statistics import median
from uuid import uuid4


DECIMAL_PRECISION = 34
FEATURE_CSV_COLUMNS = ("ticker", "name", "market", "mom20_pct", "trend20_pct", "vol20_annual_pct")
FORMULAS = {
    "mom20": "P[20] / P[0] - 1",
    "trend20": "P[20] / mean(P[1:21]) - 1",
    "vol20": "sample_stdev(P[i] / P[i-1] - 1, i=1..20, ddof=1) * sqrt(252)",
}


class FeatureAnalysisError(ValueError):
    """歷史視窗或沿用的行情與驗收證據不符，無法進行本批分析。"""


def calculate_price_features(prices) -> dict[str, Decimal]:
    """恰以 21 筆依交易日排序的正原價計算三因子；回傳比例小數。"""
    try:
        values = list(prices)
    except TypeError as exc:
        raise FeatureAnalysisError("prices 必須包含 21 筆原價") from exc
    if len(values) != 21:
        raise FeatureAnalysisError("三因子需要恰好 21 筆原價")
    converted = []
    for value in values:
        if type(value) not in (Decimal, str, int):
            raise FeatureAnalysisError("原價必須使用 Decimal、十進位字串或整數")
        try:
            price = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise FeatureAnalysisError("原價無法轉成 Decimal") from exc
        if not price.is_finite() or price <= 0:
            raise FeatureAnalysisError("原價必須是有限正數")
        converted.append(price)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        returns = [converted[i] / converted[i - 1] - 1 for i in range(1, 21)]
        average_return = sum(returns, Decimal(0)) / 20
        variance = sum(((value - average_return) ** 2 for value in returns), Decimal(0)) / 19
        return {
            "mom20": converted[-1] / converted[0] - 1,
            "trend20": converted[-1] / (sum(converted[1:], Decimal(0)) / 20) - 1,
            "vol20": variance.sqrt() * Decimal(252).sqrt(),
        }


def _read_json(path: Path) -> tuple[dict, bytes]:
    try:
        body = path.read_bytes()
        result = json.loads(body.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FeatureAnalysisError(f"無法讀取 {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise FeatureAnalysisError(f"{path} 必須包含 JSON 物件")
    return result, body


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _date(value, field: str) -> str:
    try:
        result = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise FeatureAnalysisError(f"{field} 必須是 YYYY-MM-DD") from exc
    if result.isoformat() != value:
        raise FeatureAnalysisError(f"{field} 必須是 YYYY-MM-DD")
    return value


def _required_dates(report: dict) -> dict[str, list[str]]:
    result = {}
    expected = report.get("expected_dates_by_market")
    if not isinstance(expected, dict):
        raise FeatureAnalysisError("視窗報告缺少共同日期")
    for market in ("TWSE", "TPEX"):
        days = expected.get(market)
        if not isinstance(days, list) or len(days) != 21:
            raise FeatureAnalysisError(f"{market} 視窗需要 21 個共同日期")
        days = [_date(day, "expected_dates_by_market") for day in days]
        if sorted(set(days)) != days or any(day > report["as_of"] for day in days):
            raise FeatureAnalysisError("共同日期必須依序、不重複且不得超過截止日")
        result[market] = days
    return result


def analyze_history_features(window_report_path: Path | str) -> dict:
    """只讀已完整的視窗及相關日表，核對先前保存的輸入 hash 後計算。"""
    report_path = Path(window_report_path).resolve()
    window, window_body = _read_json(report_path)
    if (window.get("report_format_version") != "1.0"
            or window.get("scope") != "historical_price_window_coverage"
            or window.get("input_valid") is not True
            or window.get("submission_ready") is not False
            or window.get("required_bars") != 21):
        raise FeatureAnalysisError("需使用格式 1.0、價格驗收有效的 21 筆歷史視窗報告")
    cutoff = _date(window.get("as_of"), "as_of")
    expected = _required_dates(window)
    stocks = window.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        raise FeatureAnalysisError("視窗報告缺少逐股結果")
    tickers = [stock.get("ticker") for stock in stocks if isinstance(stock, dict)]
    if (len(tickers) != len(stocks) or any(not isinstance(ticker, str) for ticker in tickers)
            or len(set(tickers)) != len(tickers)):
        raise FeatureAnalysisError("視窗報告股票欄位錯誤或有重複")
    selected = [stock for stock in stocks if stock.get("window_complete") is True]
    excluded = [stock for stock in stocks if stock.get("window_complete") is not True]
    for stock in selected:
        if stock.get("market") not in expected or stock.get("valid_price_count") != 21:
            raise FeatureAnalysisError("完整視窗的市場或價格筆數不符")
    manifest_value = window.get("input_manifest")
    if not isinstance(manifest_value, str):
        raise FeatureAnalysisError("視窗報告缺少 input_manifest 路徑")
    manifest_path = Path(manifest_value)
    if not manifest_path.is_absolute():
        manifest_path = report_path.parent / manifest_path
    manifest_path = manifest_path.resolve()
    manifest, manifest_body = _read_json(manifest_path)
    if _sha256(manifest_body) != window.get("input_manifest_sha256"):
        raise FeatureAnalysisError("行情 manifest hash 與視窗驗收不一致")
    if (manifest.get("format_version") != "1.0" or manifest.get("csv_format_version") != "4.0"
            or manifest.get("requested_month") != cutoff[:7]
            or manifest.get("universe_version") != window.get("universe_version")):
        raise FeatureAnalysisError("行情 manifest 版本、月份或股票清單不符")
    run_dir = manifest_path.parent
    required_days = sorted({day for stock in selected for day in expected[stock["market"]]})
    daily_entries = manifest.get("daily_prices")
    daily_reports = window.get("daily_reports")
    if not isinstance(daily_entries, list) or not isinstance(daily_reports, list):
        raise FeatureAnalysisError("行情或視窗報告缺少日表索引")
    indexed = {day: [entry for entry in daily_entries if isinstance(entry, dict)
                     and entry.get("trade_date") == day] for day in required_days}
    validated = {day: [entry for entry in daily_reports if isinstance(entry, dict)
                       and entry.get("trade_date") == day] for day in required_days}
    rows_by_day, daily_inputs = {}, []
    selected_by_market = {market: {stock["ticker"] for stock in selected if stock["market"] == market}
                          for market in expected}
    for day in required_days:
        if len(indexed[day]) != 1 or len(validated[day]) != 1:
            raise FeatureAnalysisError(f"{day} 缺少唯一日表或驗收記錄")
        entry, checked = indexed[day][0], validated[day][0]
        relative_value = entry.get("prices_csv")
        if not isinstance(relative_value, str) or not relative_value.strip():
            raise FeatureAnalysisError(f"{day} 缺少日表路徑")
        relative = Path(relative_value)
        csv_path = (run_dir / relative).resolve()
        if relative.is_absolute() or not csv_path.is_relative_to(run_dir):
            raise FeatureAnalysisError(f"{day} 日表路徑超出行情 run")
        if checked.get("status") != "checked" or Path(checked.get("input_csv", "")).resolve() != csv_path:
            raise FeatureAnalysisError(f"{day} 日表與既有驗收路徑不符")
        try:
            body = csv_path.read_bytes()
        except OSError as exc:
            raise FeatureAnalysisError(f"無法讀取 {day} 日表: {exc}") from exc
        digest = _sha256(body)
        if digest != checked.get("input_csv_sha256"):
            raise FeatureAnalysisError(f"{day} 日表 hash 與視窗驗收不一致")
        required_tickers = set().union(*(selected_by_market[market] for market in expected
                                        if day in expected[market]))
        observed = {}
        try:
            reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")), strict=True)
            for row in reader:
                ticker = row.get("ticker")
                if ticker not in required_tickers:
                    continue
                market = row.get("market")
                if (ticker in observed or row.get("trade_date") != day
                        or ticker not in selected_by_market.get(market, set())
                        or row.get("price_valid") != "true"):
                    raise FeatureAnalysisError(f"{day} {ticker} 完整視窗價格欄位不符")
                observed[ticker] = row
        except (UnicodeError, csv.Error) as exc:
            raise FeatureAnalysisError(f"{day} 日表無法解析: {exc}") from exc
        if set(observed) != required_tickers:
            raise FeatureAnalysisError(f"{day} 已完整股票在日表中缺少價格")
        rows_by_day[day] = observed
        daily_inputs.append({"trade_date": day, "path": str(csv_path), "sha256": digest})
    rows = []
    for stock in sorted(selected, key=lambda item: item["ticker"]):
        days = expected[stock["market"]]
        inputs = [rows_by_day[day][stock["ticker"]] for day in days]
        values = calculate_price_features([row.get("close_raw_ktwd_per_lot") for row in inputs])
        source_metadata = {
            "source_keys": sorted({row.get("source_key", "") for row in inputs}),
            "data_versions": sorted({row.get("data_version", "") for row in inputs}),
            "fetched_at_values": sorted({row.get("fetched_at", "") for row in inputs}),
            "known_at_missing_dates": [day for day, row in zip(days, inputs) if not row.get("known_at")],
            "adjustment_unresolved_dates": [day for day, row in zip(days, inputs)
                                            if row.get("adjustment_status") == "unresolved"],
            "tradable_false_dates": [day for day, row in zip(days, inputs) if row.get("tradable") != "true"],
        }
        rows.append({"ticker": stock["ticker"], "name": stock.get("name", ""), "market": stock["market"],
                     "price_count": 21, "return_count": 20,
                     "values": {key: str(value) for key, value in values.items()},
                     "source_metadata": source_metadata})
    excluded_rows = [{key: stock.get(key) for key in
                      ("ticker", "name", "market", "status", "valid_price_count", "missing_dates",
                       "invalid_price_dates", "calendar_window_shortfall", "source_metadata")}
                     for stock in excluded]
    identity = {"definition_version": "price-features-v1", "formulas": FORMULAS,
                "decimal_precision": DECIMAL_PRECISION, "rounding": "ROUND_HALF_EVEN",
                "input_window_report_sha256": _sha256(window_body),
                "input_manifest_sha256": _sha256(manifest_body), "as_of": cutoff,
                "daily_inputs": [{"trade_date": item["trade_date"], "sha256": item["sha256"]}
                                 for item in daily_inputs], "tickers": [row["ticker"] for row in rows]}
    version_hash = _sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {
        "analysis_format_version": "1.0", "scope": "historical_raw_price_feature_analysis", "as_of": cutoff,
        "feature_version": "price-features-v1-" + version_hash[:12],
        "input_window_report": {"path": str(report_path), "sha256": _sha256(window_body)},
        "input_manifest": {"path": str(manifest_path), "sha256": _sha256(manifest_body)},
        "universe_version": window.get("universe_version"), "calendar_version": window.get("calendar_version"),
        "calendar_basis": window.get("calendar_basis"), "calendar_markets": window.get("calendar_markets"),
        "expected_dates_by_market": expected, "daily_inputs": daily_inputs,
        "formulas": FORMULAS.copy(), "annualization_trading_days": 252,
        "decimal_precision": DECIMAL_PRECISION, "calculation_rounding": "ROUND_HALF_EVEN",
        "units": {"input_price": "千元新臺幣／張（1 張 = 1000 股），同比例等同元／股",
                  "internal_features": "ratio，字串保存 Decimal；0.1 代表 10%",
                  "csv_features": "percent；10.000000 代表 10%"},
        "csv_display": {"decimal_places": 6, "rounding": "ROUND_HALF_UP"},
        "price_basis": "unadjusted_raw_close", "rows": rows, "excluded_stocks": excluded_rows,
        "summary": {"stock_count": len(stocks), "analyzed_stock_count": len(rows),
                    "excluded_stock_count": len(excluded_rows)},
        "limitations": [
            "使用未調整原價作歷史分析；除權息等公司行動可能影響動能、均線及波動。",
            "只沿用既有完整價格視窗，未補值或重新調查排除股票的缺失原因。",
            "as_of 是歷史資料截止日，未建立可在當時取得的正式 MarketSnapshot 或 FeatureTable。",
            "日曆仍沿用既有核實範圍；歷史公開時間、公司行動及正式可交易資格尚未核實。",
            "本表尚未套用排名、權重、選股、配置或模型決策。",
        ], "submission_ready": False,
    }


def _percent(value: str | Decimal) -> str:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return format((Decimal(value) * 100).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")


def _render_feature_analysis(report: dict) -> str:
    """將已計算的分析轉成含選用理由與數值解讀的閱讀摘要。"""
    summary = report["summary"]
    lines = [f"# {report['as_of']} 三因子原價分析", "",
             f"分析 {summary['analyzed_stock_count']}／{summary['stock_count']} 檔；"
             f"沿用既有不足視窗並排除 {summary['excluded_stock_count']} 檔，沒有補值。", "",
             f"特徵版本：`{report['feature_version']}`；日曆依據：`{report['calendar_basis']}`。", "",
             "數值以百分數呈現；例如 10 表示 10%。每檔 21 筆收盤原價提供 20 個相鄰日報酬。", "",
             "## 為什麼先使用這三個指標", "",
             "這組指標沿用專案的價格動能與風險控制草案。現有收盤資料就能計算，公式簡單、來源可追溯，"
             "適合先建立可檢查的 MVP 分析流程。20 個交易日大約對應一個月，讓三項數值採用相同的近期觀察範圍。", "",
             "動能看整段首尾漲跌；均線偏離補充期末價格相對近期平均的位置；波動衡量期間每日漲跌的起伏。"
             "動能與均線偏離有相關性，這三項主要涵蓋趨勢與波動兩種面向。基本面、法人籌碼與新聞資料仍待後續加入。", "",
             "這是 MVP 的初始分析選擇，尚未經回測選出最佳指標或期間；20 日及年化常數 252 都是設計約定。", "",
             "## 各指標代表什麼", "",
             "| 指標 | 如何讀數值 | 分析時要留意 |",
             "|---|---|---|",
             "| 20 日動能 | 10% 表示這段期間原價上漲 10%；負值表示下跌。 | 可比較近期表現強弱；高動能也可能出現回撤。 |",
             "| 均線偏離 | 3% 表示最後收盤高於最近 20 筆平均 3%；負值表示低於平均。 | 可觀察期末趨勢位置；過大偏離也可能表示短期漲幅集中。 |",
             "| 年化波動 | 將這 20 個日報酬的離散程度換算到年尺度；數值較高表示近期起伏較大。 | 可作價格風險的比較尺度；不能直接推得未來報酬或虧損機率，低波動仍可能虧損。 |", "",
             "## 計算方式", "",
             "- 20 日動能：最後收盤／最早收盤 − 1，觀察整段期間漲跌。",
             "- 均線偏離：最後收盤／最後 20 筆平均 − 1，觀察相對近期平均的位置。",
             "- 年化波動：20 個日報酬的樣本標準差（分母 19）× √252，觀察價格起伏。", "",
             "## 後續如何運用", "",
             "1. 先在同一截止日比較各股的原始因子值，轉成相對排名。",
             "2. 依設計草案討論動能／均線偏離正向、低波動反向的分數，再決定綜合權重與候選清單。",
             "3. 將因子與來源證據交給模型，結合市場背景及既有持股提出選股理由；配置程式再處理權重、風控、股數與現金。", "",
             "目前已完成原價因子數值分析；上述排名、綜合權重及投資模型流程仍待後續批次討論與實作。", "",
             "## 分布", "", "| 因子 | 最小值（%） | 中位數（%） | 最大值（%） |",
             "|---|---:|---:|---:|"]
    labels = {"mom20": "20 日動能", "trend20": "均線偏離", "vol20": "年化波動"}
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for key, label in labels.items():
            values = [Decimal(row["values"][key]) for row in report["rows"]]
            if values:
                lines.append(f"| {label} | {_percent(min(values))} | {_percent(median(values))} | {_percent(max(values))} |")
    lines.extend(["", "## 股票閱讀範例", "", "依股票代號列前五檔，便於對照 CSV。", "",
                  "| 股票 | 市場 | 動能（%） | 均線偏離（%） | 年化波動（%） |",
                  "|---|---|---:|---:|---:|"])
    for row in report["rows"][:5]:
        lines.append(f"| {row['ticker']} {row['name']} | {row['market']} | "
                     f"{_percent(row['values']['mom20'])} | {_percent(row['values']['trend20'])} | "
                     f"{_percent(row['values']['vol20'])} |")
    lines.extend(["", "完整分析見 [CSV](features.csv)；共同日期、公式、內部小數及來源見 [metadata](metadata.json)。", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(["", "`submission_ready=false`。", ""])
    return "\n".join(lines)


def write_feature_analysis(report: dict, output_dir: Path | str) -> dict:
    """以獨立執行版本保存六欄分析 CSV、計算來源 metadata 及可讀摘要。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / report["as_of"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    features_csv, metadata_json, analysis_md = (run_dir / name for name in
                                               ("features.csv", "metadata.json", "analysis.md"))
    with features_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({"ticker": row["ticker"], "name": row["name"], "market": row["market"],
                             "mom20_pct": _percent(row["values"]["mom20"]),
                             "trend20_pct": _percent(row["values"]["trend20"]),
                             "vol20_annual_pct": _percent(row["values"]["vol20"])})
    analysis_md.write_text(_render_feature_analysis(report), encoding="utf-8", newline="\n")
    stored = {**report, "created_at": now.isoformat(), "run_id": run_id,
              "artifacts": {"features_csv": features_csv.name, "analysis_md": analysis_md.name}}
    metadata_json.write_text(json.dumps(stored, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")
    return {"run_dir": str(run_dir), "features_csv": str(features_csv),
            "metadata_json": str(metadata_json), "analysis_md": str(analysis_md)}
