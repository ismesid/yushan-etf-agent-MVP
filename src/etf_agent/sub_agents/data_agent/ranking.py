"""離線歷史因子排名；分析分數不代表正式交易資格或配置權重。"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from fractions import Fraction
from pathlib import Path
from uuid import uuid4


DECIMAL_PRECISION = 34
FACTORS = ("mom20", "trend20", "lowvol20")
SOURCE_FACTORS = {"mom20": "mom20", "trend20": "trend20", "lowvol20": "vol20"}
RANKING_CSV_COLUMNS = (
    "rank", "ticker", "name", "market", "mom20_pct", "trend20_pct", "vol20_annual_pct",
    "rank_mom20_pct", "rank_trend20_pct", "rank_lowvol20_pct",
    "contribution_mom20_pct", "contribution_trend20_pct", "contribution_lowvol20_pct",
    "score_pct", "analysis_included", "formal_eligible",
)


class RankingError(ValueError):
    """不完整或不一致的因子與設定必須停止排名。"""


def _decimal(value, field: str) -> Decimal:
    if type(value) not in (Decimal, str, int):
        raise RankingError(f"{field} 必須是十進位文字、Decimal 或整數")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise RankingError(f"{field} 無法轉為 Decimal") from exc
    if not result.is_finite():
        raise RankingError(f"{field} 必須是有限數值")
    return result


def _weights(values: dict) -> dict[str, Decimal]:
    if not isinstance(values, dict) or set(values) != set(FACTORS):
        raise RankingError("權重必須完整包含 mom20、trend20、lowvol20")
    result = {factor: _decimal(values[factor], f"weights.{factor}") for factor in FACTORS}
    if any(value < 0 or value > 1 for value in result.values()):
        raise RankingError("各因子權重必須介於 0 與 1")
    # Validate the sum exactly, including configuration digits beyond calculation precision.
    with localcontext() as context:
        context.prec = max(DECIMAL_PRECISION, max(-value.as_tuple().exponent for value in result.values()) + 3)
        if sum(result.values(), Decimal(0)) != 1:
            raise RankingError("三個權重總和必須精確等於 1；不自動重新配重")
    return result


def _profile(profile: dict) -> dict:
    if profile.get("format_version") != "1.0" or profile.get("factor_profile") != "price_only_v1":
        raise RankingError("本批只支援 1.0／price_only_v1 排名設定")
    enabled = profile.get("enabled_factors")
    if not isinstance(enabled, list) or len(enabled) != 3 or any(factor not in FACTORS for factor in enabled):
        raise RankingError("本批必須啟用 mom20、trend20、lowvol20 三個因子")
    if len(set(enabled)) != 3:
        raise RankingError("啟用因子不能重複")
    weights = _weights(profile.get("weights"))
    return {"format_version": "1.0", "factor_profile": "price_only_v1",
            "enabled_factors": list(enabled), "weights": {factor: str(weights[factor]) for factor in FACTORS}}


def _read_json(path: Path, *, decimal_numbers: bool = False) -> tuple[dict, bytes]:
    try:
        body = path.read_bytes()
        options = {"parse_float": Decimal} if decimal_numbers else {}
        result = json.loads(body.decode("utf-8-sig"), **options)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RankingError(f"無法讀取 {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise RankingError(f"{path} 必須是 JSON 物件")
    return result, body


def load_ranking_profile(path: Path | str = "config/ranking.json") -> dict:
    """讀取整批共用的三因子設定；權重轉成精確十進位文字。"""
    profile, _ = _read_json(Path(path).resolve(), decimal_numbers=True)
    return _profile(profile)


def _percentile_ranks(values: list[Decimal]) -> list[Fraction]:
    if len(values) == 1 or len(set(values)) == 1:
        return [Fraction(1, 2)] * len(values)
    indexed = sorted(range(len(values)), key=lambda index: values[index])
    result = [Fraction(0)] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[indexed[end]] == values[indexed[start]]:
            end += 1
        # Positions start..end-1 have average one-based rank (start + end + 1) / 2.
        average_rank = Fraction(start + end + 1, 2)
        percentile = (average_rank - 1) / (len(values) - 1)
        for index in indexed[start:end]:
            result[index] = percentile
        start = end
    return result


def calculate_factor_rankings(rows, weights: dict) -> list[dict]:
    """純排名函式；回傳 Decimal 分數，按精確總分再按 ticker 排序。"""
    configured = _weights(weights)
    if not isinstance(rows, (list, tuple)) or not rows:
        raise RankingError("排名母體至少需要一檔股票")
    tickers, converted = set(), []
    for row in rows:
        if not isinstance(row, dict):
            raise RankingError("每筆因子必須是物件")
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip() or ticker in tickers:
            raise RankingError("股票代號不能空白或重複")
        tickers.add(ticker)
        values = row.get("values")
        if not isinstance(values, dict) or any(factor not in values for factor in SOURCE_FACTORS.values()):
            raise RankingError(f"{ticker} 缺少三個完整因子值；不逐股重新配重")
        numbers = {factor: _decimal(values[factor], f"{ticker}.{factor}") for factor in SOURCE_FACTORS.values()}
        if numbers["vol20"] < 0:
            raise RankingError(f"{ticker}.vol20 不可為負數")
        converted.append(numbers)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        scores = {factor: _percentile_ranks([values[SOURCE_FACTORS[factor]] for values in converted])
                  for factor in FACTORS}
        # Reverse volatility only once; the raw source remains positive vol20.
        scores["lowvol20"] = [1 - value for value in scores["lowvol20"]]
        exact_weights = {factor: Fraction(value) for factor, value in configured.items()}
        scored = []
        for index, original in enumerate(rows):
            exact_scores = {factor: scores[factor][index] for factor in FACTORS}
            exact_contributions = {factor: exact_scores[factor] * exact_weights[factor] for factor in FACTORS}
            exact_score = sum(exact_contributions.values(), Fraction(0))
            rank_scores = {factor: Decimal(value.numerator) / value.denominator for factor, value in exact_scores.items()}
            contributions = {factor: Decimal(value.numerator) / value.denominator
                             for factor, value in exact_contributions.items()}
            row = copy.deepcopy(original)
            row["values"] = {factor: str(value) for factor, value in converted[index].items()}
            row.update(rank_scores=rank_scores, contributions=contributions,
                       score=Decimal(exact_score.numerator) / exact_score.denominator,
                       analysis_included=True, formal_eligible=False)
            row["analysis_warnings"] = ["zero_volatility_requires_review"] if converted[index]["vol20"] == 0 else []
            scored.append((row, exact_score))
        # Exact fractions keep mathematical ties equal even for N=4 (thirds) or N=146 (145ths).
        scored.sort(key=lambda item: (-item[1], item[0]["ticker"]))
        result = [row for row, _ in scored]
        for rank, row in enumerate(result, 1):
            row["rank"] = rank
    return result


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def analyze_history_rankings(feature_metadata_path: Path | str,
                             profile_path: Path | str = "config/ranking.json") -> dict:
    """只讀因子 metadata 與設定，不讀 CSV、原行情、API 或帳戶。"""
    metadata_path, setting_path = Path(feature_metadata_path).resolve(), Path(profile_path).resolve()
    source, source_body = _read_json(metadata_path)
    raw_profile, profile_body = _read_json(setting_path, decimal_numbers=True)
    profile = _profile(raw_profile)
    if (source.get("analysis_format_version") != "1.0"
            or source.get("scope") != "historical_raw_price_feature_analysis"
            or source.get("submission_ready") is not False
            or source.get("price_basis") != "unadjusted_raw_close"):
        raise RankingError("只接受 1.0 歷史原價分析 metadata；不可當成正式交易候選")
    cutoff = source.get("as_of")
    try:
        if date.fromisoformat(cutoff).isoformat() != cutoff:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise RankingError("as_of 必須是 YYYY-MM-DD") from exc
    for field in ("feature_version", "universe_version", "calendar_version"):
        if not isinstance(source.get(field), str) or not source[field]:
            raise RankingError(f"缺少來源版本 {field}")
    excluded = source.get("excluded_stocks")
    if not isinstance(excluded, list) or any(not isinstance(row, dict) for row in excluded):
        raise RankingError("metadata 必須保留 excluded_stocks 清單")
    ranked = calculate_factor_rankings(source.get("rows"), profile["weights"])
    excluded_tickers = [row.get("ticker") for row in excluded]
    if (any(not isinstance(ticker, str) or not ticker for ticker in excluded_tickers)
            or len(set(excluded_tickers)) != len(excluded_tickers)
            or set(excluded_tickers) & {row["ticker"] for row in ranked}):
        raise RankingError("排除清單代號不完整、重複或同時出現在排名母體")
    summary = source.get("summary")
    if not isinstance(summary, dict) or summary != {
            "stock_count": len(ranked) + len(excluded), "analyzed_stock_count": len(ranked),
            "excluded_stock_count": len(excluded)}:
        raise RankingError("因子摘要數量與完整母體／排除清單不一致")
    limitations = source.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise RankingError("metadata 必須保留原分析限制")
    for row in ranked:
        row["rank_scores"] = {factor: str(value) for factor, value in row["rank_scores"].items()}
        row["contributions"] = {factor: str(value) for factor, value in row["contributions"].items()}
        row["score"] = str(row["score"])
    identity = {
        "definition_version": "price-rankings-v1", "input_feature_metadata_sha256": _sha256(source_body),
        "profile": profile, "decimal_precision": DECIMAL_PRECISION, "rounding": "ROUND_HALF_EVEN",
        "percentile_formula": "(average_rank - 1) / (N - 1); all_equal_or_N1 = 0.5",
        "lowvol_formula": "1 - percentile_rank(vol20)", "tie_breaker": "ticker_ascending",
        "score_ordering": "exact_fraction_before_decimal_output",
    }
    digest = _sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    report = {
        "analysis_format_version": "1.0", "scope": "historical_raw_price_factor_ranking", "as_of": cutoff,
        "ranking_version": "price-rankings-v1-" + digest[:12],
        "input_feature_metadata": {"path": str(metadata_path), "sha256": _sha256(source_body)},
        "input_profile": {"path": str(setting_path), "sha256": _sha256(profile_body)}, "profile": profile,
        "feature_version": source["feature_version"], "universe_version": source["universe_version"],
        "calendar_version": source["calendar_version"], "price_basis": source["price_basis"],
        "decimal_precision": DECIMAL_PRECISION, "calculation_rounding": "ROUND_HALF_EVEN",
        "ranking_rules": {"percentile_formula": identity["percentile_formula"],
                          "lowvol_formula": identity["lowvol_formula"], "tie_breaker": identity["tie_breaker"],
                          "score_ordering": identity["score_ordering"]},
        "units": {"internal_features": "ratio; 0.1 = 10%", "internal_scores": "relative_score_0_to_1",
                  "csv_features": "percent; 10.000000 = 10%",
                  "csv_rank_contribution_score": "relative_points_0_to_100; not return percentages"},
        "csv_display": {"decimal_places": 6, "rounding": "ROUND_HALF_UP"},
        "summary": {"stock_count": len(ranked) + len(excluded), "ranked_stock_count": len(ranked),
                    "excluded_stock_count": len(excluded)},
        "rows": ranked, "excluded_stocks": copy.deepcopy(excluded),
        "limitations": [*limitations, "此 profile 權重為專案基準設定，並非業界標準、最佳權重或官方規定。",
                        "排名是同截止日分析母體的相對分數；尚未完成正式資格、流動性與投資配置驗證。"],
        "submission_ready": False,
    }
    for field in ("input_window_report", "input_manifest", "daily_inputs", "calendar_basis", "calendar_markets"):
        if field in source:
            report[field] = copy.deepcopy(source[field])
    return report


def _display(value: str | Decimal) -> str:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return format((Decimal(value) * 100).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")


def write_ranking_analysis(report: dict, output_dir: Path | str) -> dict:
    """以新 run 保存排名 CSV／JSON；分數呈現與排序分開。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / report["as_of"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    rankings_csv, metadata_json = (run_dir / name for name in ("rankings.csv", "metadata.json"))
    with rankings_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RANKING_CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in report["rows"]:
            displayed = {key: row.get(key, "") for key in ("rank", "ticker", "name", "market")}
            displayed.update({"mom20_pct": _display(row["values"]["mom20"]),
                              "trend20_pct": _display(row["values"]["trend20"]),
                              "vol20_annual_pct": _display(row["values"]["vol20"]),
                              "score_pct": _display(row["score"]),
                              "analysis_included": "true", "formal_eligible": "false"})
            for factor in FACTORS:
                displayed[f"rank_{factor}_pct"] = _display(row["rank_scores"][factor])
                displayed[f"contribution_{factor}_pct"] = _display(row["contributions"][factor])
            writer.writerow(displayed)
    stored = {**report, "created_at": now.isoformat(), "run_id": run_id,
              "artifacts": {"rankings_csv": rankings_csv.name}}
    metadata_json.write_text(json.dumps(stored, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")
    return {"run_dir": str(run_dir), "rankings_csv": str(rankings_csv), "metadata_json": str(metadata_json)}
