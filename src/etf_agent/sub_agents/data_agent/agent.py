"""資料角色：從已保存的歷史資料整理因子與排名，不抓行情、不估值帳戶。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from urllib.parse import urlparse

from etf_agent.prices import load_history_closes
from etf_agent.universe import Universe


class DataAgentError(ValueError):
    """資料包不一致；不能用補值、換日期或自行重新配重繼續。"""


def trade_date(value: str) -> str:
    try:
        if type(value) is not str or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise DataAgentError("日期須為有效 YYYY-MM-DD") from exc
    return value


def _json(path: Path) -> tuple[dict, bytes]:
    try:
        body = path.read_bytes()
        value = json.loads(body.decode("utf-8-sig"))
        if type(value) is not dict:
            raise ValueError("須為 JSON object")
        return value, body
    except (OSError, UnicodeError, ValueError) as exc:
        raise DataAgentError(f"資料讀取失敗：{path}: {exc}") from exc


def _number(value, label: str) -> Decimal:
    try:
        if type(value) is not str:
            raise ValueError("須為十進位字串")
        result = Decimal(value)
        if not result.is_finite():
            raise ValueError("須為有限值")
        return result
    except (InvalidOperation, ValueError) as exc:
        raise DataAgentError(f"{label}: {exc}") from exc


def prepare_data(ranking_metadata_path: Path | str, *, as_of: str, universe: Universe,
                 price_context: dict | None = None) -> dict:
    """將既有歷史因子與排名整理成同日期、可回查的市場報告。

    目前僅支援 historical replay；新增來源、增量合併與新因子另行接入。
    帳戶匯入與估值由 account_agent 負責；本角色不接收或讀取帳戶。
    """
    cutoff = trade_date(as_of)
    ranking_path = Path(ranking_metadata_path).resolve()
    ranking, ranking_body = _json(ranking_path)
    if (ranking.get("as_of") != cutoff or ranking.get("analysis_format_version") != "1.0"
            or ranking.get("scope") != "historical_raw_price_factor_ranking"
            or ranking.get("price_basis") != "unadjusted_raw_close"
            or ranking.get("submission_ready") is not False
            or ranking.get("universe_version") != universe.universe_version):
        raise DataAgentError("排名日期、scope、原價基礎或白名單版本不符；不讀行情")
    for field in ("ranking_version", "feature_version", "calendar_version"):
        if not isinstance(ranking.get(field), str) or not ranking[field]:
            raise DataAgentError(f"排名缺少 {field}")
    rows, excluded = ranking.get("rows"), ranking.get("excluded_stocks")
    if not isinstance(rows, list) or not rows or not isinstance(excluded, list):
        raise DataAgentError("排名須包含完整 rows 與 excluded_stocks")
    prices = (load_history_closes(ranking_path, as_of=cutoff, universe=universe)
              if price_context is None else price_context)
    if prices.get("as_of") != cutoff or prices.get("universe_version") != universe.universe_version:
        raise DataAgentError("共用行情日期或白名單版本不符")
    ranking_hash = hashlib.sha256(ranking_body).hexdigest()
    if prices["inputs"]["ranking_metadata"]["sha256"] != ranking_hash:
        raise DataAgentError("排名在資料整理期間已變更")
    stocks, quotes, seen, ranked = prices["stocks"], prices["quotes"], set(), []
    for index, row in enumerate(rows, 1):
        if type(row) is not dict:
            raise DataAgentError("排名列須為物件")
        ticker = row.get("ticker")
        if (ticker not in stocks or ticker in seen or type(row.get("rank")) is not int
                or row["rank"] != index or row.get("market") != stocks[ticker]["market"]
                or row.get("analysis_included") is not True or row.get("formal_eligible") is not False):
            raise DataAgentError(f"排名代號、市場、順序或分析狀態錯誤：{ticker}")
        seen.add(ticker)
        values = row.get("values")
        if type(values) is not dict or set(values) != {"mom20", "trend20", "vol20"}:
            raise DataAgentError(f"{ticker} 須有完整三因子")
        numbers = {key: _number(value, f"{ticker}.{key}") for key, value in values.items()}
        score = _number(row.get("score"), f"{ticker}.score")
        if numbers["vol20"] < 0 or not 0 <= score <= 1:
            raise DataAgentError(f"{ticker} 波動或分數不合法")
        quote = quotes.get(ticker)
        source_metadata = row.get("source_metadata")
        if type(source_metadata) is not dict:
            raise DataAgentError(f"{ticker} 缺少特徵來源")
        if quote is not None and (quote["source_key"] not in source_metadata.get("source_keys", [])
                                 or quote["data_version"] not in source_metadata.get("data_versions", [])):
            raise DataAgentError(f"{ticker} 排名與截止日行情來源不一致")
        eligible = quote is not None and quote["price_valid"] is True
        ranked.append({"ticker": ticker, "name": stocks[ticker]["name"], "market": stocks[ticker]["market"],
                       "rank": index, "values": {key: str(value) for key, value in numbers.items()},
                       "score": str(score), "close_twd_per_share": str(quote["close_twd_per_share"]) if eligible else None,
                       "source_key": quote["source_key"] if quote else None,
                       "data_version": quote["data_version"] if quote else None,
                       "demo_candidate": eligible, "formal_eligible": False,
                       "limitations": ["known_at_unverified", "corporate_actions_unverified", "formal_tradability_unverified"]})
    excluded_tickers = [row.get("ticker") for row in excluded if type(row) is dict]
    if (len(excluded_tickers) != len(excluded) or any(t not in stocks for t in excluded_tickers)
            or len(set(excluded_tickers)) != len(excluded_tickers) or set(excluded_tickers) & seen
            or seen | set(excluded_tickers) != set(stocks)
            or ranking.get("summary") != {"stock_count": len(stocks), "ranked_stock_count": len(ranked),
                                           "excluded_stock_count": len(excluded)}):
        raise DataAgentError("排名與排除清單須完整且互斥涵蓋白名單，不重新查核缺件")
    # 同機構、同歷史 endpoint 的查詢系列分組；保留每個實際 URL/hash。
    sources = []
    for market in ("TWSE", "TPEX"):
        members = []
        endpoint_paths = set()
        for ticker, quote in sorted(quotes.items()):
            if quote["market"] != market:
                continue
            url = quote.get("requested_url")
            parsed = urlparse(url or "")
            domain = "twse.com.tw" if market == "TWSE" else "tpex.org.tw"
            if parsed.scheme != "https" or not parsed.hostname or not (
                    parsed.hostname == domain or parsed.hostname.endswith("." + domain)):
                raise DataAgentError(f"{ticker} 缺少可回查的官方來源 URL")
            endpoint_paths.add(parsed.path)
            members.append({"ticker": ticker, "source_key": quote["source_key"], "url": url,
                            "data_version": quote["data_version"], "raw_sha256": quote["raw_sha256"],
                            "fetched_at": quote["fetched_at"]})
        if members:
            if len(endpoint_paths) != 1:
                raise DataAgentError(f"{market} 來源系列須為同一 endpoint，不能合併不同內容來源")
            sources.append({"source_id": f"S{len(sources) + 1}", "authority": market.lower(),
                            "name": f"{market} {cutoff[:7]} 個股歷史月報查詢系列",
                            "url": members[0]["url"], "content_as_of_trade_date": cutoff,
                            "known_at": None, "members": members,
                            "grouping_status": "demo_series_grouping_not_officially_confirmed"})
    candidate_tickers = [row["ticker"] for row in ranked if row["demo_candidate"]]
    with localcontext() as context:
        context.prec = 50
        positive_mom = sum(Decimal(row["values"]["mom20"]) > 0 for row in ranked)
        positive_trend = sum(Decimal(row["values"]["trend20"]) > 0 for row in ranked)
        market_summary = {"scope": "ranked_analysis_universe_not_market_index", "stock_count": len(ranked),
                          "positive_mom20_count": positive_mom, "positive_trend20_count": positive_trend,
                          "positive_mom20_ratio": str(Decimal(positive_mom) / len(ranked)),
                          "positive_trend20_ratio": str(Decimal(positive_trend) / len(ranked))}
    issues = list(prices["issues"])
    missing_ranked = [row["ticker"] for row in ranked if not row["demo_candidate"]]
    if missing_ranked:
        issues.append({"code": "ranked_close_missing", "severity": "WARN", "ticker": None,
                       "message": f"{len(missing_ranked)} 檔排名股缺截止日收盤，不能新買；原持股仍保留"})
    ready = len(candidate_tickers) >= 20 and not any(row.get("severity") == "BLOCK" for row in issues)
    return {"report_version": "1.0", "role": "data_agent", "scope": "historical_replay_data",
            "as_of": cutoff, "mode": "historical_demo", "network_used": False,
            "rankings": ranked, "excluded_stocks": excluded, "allowed_tickers": candidate_tickers,
            "sources": sources, "market_summary": market_summary,
            "issues": issues, "demo_decision_ready": ready,
            "profile": ranking.get("profile"), "ranking_version": ranking["ranking_version"],
            "feature_version": ranking["feature_version"], "calendar_version": ranking["calendar_version"],
            "universe_version": universe.universe_version,
            "inputs": {**prices["inputs"], "upstream_feature_reference": ranking.get("input_feature_metadata")},
            "limitations": ["重用已保存分析；未重新下載、重算因子或核實四檔缺件。",
                            "demo_candidate 只表示具備白名單、原價因子及截止日收盤，不等於正式資格或流動性通過。",
                            "歷史公開時間、公司行動及系列來源分組的正式接受仍未核實。"],
            "formal_eligible": False, "submission_ready": False}
