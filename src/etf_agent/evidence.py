"""組裝並保存決策前的凍結資料；不呼叫模型，不產生交易或 D-Plan。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import uuid4

from etf_agent.reports import write_csv_view
from etf_agent.prices import PriceContextError, load_history_closes
from etf_agent.sub_agents.data_agent import prepare_data, trade_date as parse_trade_date
from etf_agent.sub_agents.test_agent import review_previous_day, validate_review_report
from etf_agent.sub_agents.account_agent import prepare_account
from etf_agent.sub_agents.data_agent import DataAgentError
from etf_agent.universe import Universe


class EvidenceError(ValueError):
    """輸入日期或凍結資料不一致，不能交付投資決策。"""


def prepare_decision(account_path: Path | str, ranking_metadata_path: Path | str,
                     *, as_of: str, trade_date: str, universe: Universe) -> dict:
    cutoff, decision_day = parse_trade_date(as_of), parse_trade_date(trade_date)
    if decision_day <= cutoff:
        raise EvidenceError("決策日須晚於資料截止日；不得使用決策當日行情")
    try:
        prices = load_history_closes(ranking_metadata_path, as_of=cutoff, universe=universe)
    except PriceContextError as exc:
        raise DataAgentError(str(exc)) from exc
    data = prepare_data(ranking_metadata_path, as_of=cutoff, universe=universe, price_context=prices)
    account = prepare_account(account_path, prices, as_of=cutoff)
    valuation = account["account_valuation"]
    account_report = account["account_report"]
    # Keep packet 1.0 compatible: the main workflow joins account context here.
    held = {row["ticker"]: row for row in valuation["positions"]}
    for row in data["rankings"]:
        position = held.get(row["ticker"])
        row.update(held=position is not None,
                   current_shares=position["shares"] if position else 0,
                   current_weight=position["weight_of_input_nav"] if position else "0")
    market_issues = [row for row in data["issues"] if row["code"] == "ranked_close_missing"]
    data.update(account_snapshot=account["account_snapshot"], account_valuation=valuation,
                held_positions=valuation["positions"], issues=[*valuation["issues"], *market_issues],
                demo_decision_ready=valuation["valuation_ok"] and valuation["initial_constraints"]["passed"]
                                    and len(data["allowed_tickers"]) >= 20)
    data["inputs"]["account"] = valuation["input_account"]
    review = review_previous_day(as_of=cutoff)
    validate_review_report(review, as_of=cutoff)
    source_ids = {row["authority"].upper(): row["source_id"] for row in data["sources"]}
    observations = [{"obs_id": "O1", "source_ref": list(source_ids.values()),
                     "statement": "已分析股票池的價格動能與均線廣度；不是加權或櫃買指數。",
                     "values": data["market_summary"], "tickers": [], "kind": "analysis_breadth"}]
    by_ticker = {}
    with localcontext() as context:
        context.prec = 50
        for row in data["rankings"]:
            if not row["demo_candidate"]:
                continue
            obs_id = f"O{len(observations) + 1}"
            statement = (f"{row['ticker']} 截至 {cutoff} 收盤 {row['close_twd_per_share']} 元／股；"
                         f"20日動能 {Decimal(row['values']['mom20']) * 100:.6f}%、"
                         f"均線偏離 {Decimal(row['values']['trend20']) * 100:.6f}%、"
                         f"年化波動 {Decimal(row['values']['vol20']) * 100:.6f}%；排名 {row['rank']}。")
            if row["held"]:
                statement += f" 人工期初持股 {row['current_shares']} 股。"
            observations.append({"obs_id": obs_id, "source_ref": [source_ids[row["market"]]],
                                 "statement": statement, "tickers": [row["ticker"]], "kind": "stock_factors",
                                 "values": {**row["values"], "close_twd_per_share": row["close_twd_per_share"],
                                            "score": row["score"], "rank": row["rank"]},
                                 "account_context": {"current_shares": row["current_shares"],
                                                     "current_weight": row["current_weight"]}})
            by_ticker[row["ticker"]] = obs_id
        for held in data["held_positions"]:
            if held["ticker"] in by_ticker:
                continue
            refs = [source_ids[held["market"]]] if held["market"] in source_ids else []
            obs_id = f"O{len(observations) + 1}"
            observations.append({"obs_id": obs_id, "source_ref": refs, "tickers": [held["ticker"]],
                                 "kind": "held_data_missing", "values": {},
                                 "statement": f"原持股 {held['ticker']} {held['shares']} 股保留；因子或收盤缺失，不能編造價格訊號。",
                                 "account_context": held})
            by_ticker[held["ticker"]] = obs_id
    packet = {"packet_version": "1.0", "scope": "historical_demo_decision_input",
              "as_of": cutoff, "trade_date": decision_day, "data_report": data, "review_report": review,
              "account_report": account_report,
              "account_snapshot": data["account_snapshot"], "allowed_tickers": data["allowed_tickers"],
              "held_tickers": [row["ticker"] for row in data["held_positions"]],
              "sources": data["sources"], "observations": observations, "stock_observation_ids": by_ticker,
              "time_policy": {"max_market_trade_date": cutoff, "decision_day_market_data_allowed": False,
                              "model_may_fetch_data": False, "known_at_verified": False,
                              "next_trading_day_verified": False},
              "decision_contract": {"name": "WeightedAgentDraft", "contract_version": "2.0",
                                    "weight_unit": "ratio_decimal_string", "model_sets_final_shares": False},
              "demo_decision_ready": data["demo_decision_ready"] and account_report["account_valid"], "real_agent_decision": False,
              "formal_eligible": False, "submission_ready": False,
              "limitations": [*data["limitations"], "首日無交易檢討或績效；此輸入階段尚未執行股數、風控或 D-Plan 編譯。",
                               "內部 observation 可超過官方數量上限；編譯器須保留實際引用並重排 ID。",
                               "只驗決策日晚於截止日；正式相鄰交易日與截止時刻尚待核實。"]}
    body = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    packet["packet_version_id"] = "decision-packet-v1-" + hashlib.sha256(body).hexdigest()[:12]
    return packet


def _csv_views(packet: dict) -> dict:
    """僅整理同份JSON欄位供檢查；不計算新因子、補資料或提出建議。"""
    dates = {"as_of": packet["as_of"], "trade_date": packet["trade_date"]}
    data, account, review = packet["data_report"], packet["account_report"], packet["review_report"]
    candidates = [{**dates, "ticker": row["ticker"], "name": row["name"], "market": row["market"],
                   "rank": row["rank"], "score_ratio": row["score"],
                   "mom20_ratio": row["values"]["mom20"], "trend20_ratio": row["values"]["trend20"],
                   "vol20_annualized_ratio": row["values"]["vol20"],
                   "close_twd_per_share": row["close_twd_per_share"], "demo_candidate": row["demo_candidate"],
                   "formal_eligible": row["formal_eligible"], "current_shares": row["current_shares"],
                   "current_weight_ratio": row["current_weight"], "source_key": row["source_key"],
                   "data_version": row["data_version"], "ranking_version": data["ranking_version"],
                   "feature_version": data["feature_version"], "universe_version": data["universe_version"],
                   "limitations": row["limitations"]} for row in data["rankings"]]
    excluded = []
    for row in data["excluded_stocks"]:
        metadata = row.get("source_metadata") or {}
        excluded.append({**dates, **{key: row.get(key) for key in
                         ("ticker", "name", "market", "status", "valid_price_count", "missing_dates",
                          "invalid_price_dates", "calendar_window_shortfall")},
                         "source_keys": metadata.get("source_keys"),
                         "data_versions": metadata.get("data_versions"),
                         "feature_version": data["feature_version"], "ranking_version": data["ranking_version"]})
    positions = []
    for row in account["current_positions"]:
        problems = [issue for issue in account["issues"] if issue.get("ticker") == row["ticker"]]
        positions.append({**dates, **{key: row.get(key) for key in
                          ("ticker", "name", "market", "shares", "close_twd_per_share", "market_value_twd",
                           "valuation_status", "source_key", "data_version")},
                          "weight_of_input_nav_ratio": row.get("weight_of_input_nav"),
                          "issue_codes": [issue.get("code") for issue in problems],
                          "issue_severities": [issue.get("severity") for issue in problems],
                          "issue_details": [issue.get("message") for issue in problems]})
    valuation = data["account_valuation"]
    summary = [{**dates, "snapshot_id": account["snapshot_id"], "account_status": account["status"],
                "account_as_of_trade_date": account["account_snapshot"]["as_of_trade_date"],
                "demo": account["demo"], "reconciled": account["reconciled"],
                "cash_twd": account["cash_twd"], "input_nav_twd": account["nav_twd"],
                "calculated_nav_twd": valuation.get("calculated_nav_twd"),
                "stock_value_twd": valuation.get("stock_value_twd"),
                "known_stock_value_twd": valuation.get("known_stock_value_twd"),
                "nav_difference_twd": account["nav_difference_twd"],
                "estimated_available_cash_twd": account["estimated_available_cash_twd"],
                "formal_available_cash_twd": account["available_cash_twd"],
                "available_cash_status": account["available_cash_status"],
                "estimated_reservations_twd": account["reservations_twd"] if account["demo"] else None,
                "reservation_status": account["reservation_status"], "holdings_count": account["holdings_count"],
                "valuation_complete": valuation["valuation_complete"], "account_valid": account["account_valid"],
                "demo_decision_ready": packet["demo_decision_ready"], "submission_ready": False,
                "limitations": account["limitations"]}]
    status = [{**dates, "role": review["role"], "status": review["status"],
               "data_through": review["data_through"], "performance": review["performance"],
               "recommendation_count": len(review["recommendations"]), "reason": review["reason"],
               "demo": review["demo"], "submission_ready": review["submission_ready"]}]
    # 目前合約只支援prior_run_missing，不能用佔位列冒充真實建議。
    validate_review_report(review, as_of=packet["as_of"])
    return {
        "data_candidates.csv": (("as_of", "trade_date", "ticker", "name", "market", "rank", "score_ratio",
                                 "mom20_ratio", "trend20_ratio", "vol20_annualized_ratio", "close_twd_per_share",
                                 "demo_candidate", "formal_eligible", "current_shares", "current_weight_ratio",
                                 "source_key", "data_version", "ranking_version", "feature_version", "universe_version",
                                 "limitations"), candidates),
        "data_issues.csv": (("as_of", "trade_date", "ticker", "name", "market", "status", "valid_price_count",
                             "missing_dates", "invalid_price_dates", "calendar_window_shortfall", "source_keys",
                             "data_versions", "feature_version", "ranking_version"), excluded),
        "account_positions.csv": (("as_of", "trade_date", "ticker", "name", "market", "shares", "close_twd_per_share",
                                   "market_value_twd", "weight_of_input_nav_ratio", "valuation_status", "source_key",
                                   "data_version", "issue_codes", "issue_severities", "issue_details"), positions),
        "account_summary.csv": (("as_of", "trade_date", "snapshot_id", "account_status", "account_as_of_trade_date", "demo", "reconciled",
                                 "cash_twd", "input_nav_twd", "calculated_nav_twd", "stock_value_twd",
                                 "known_stock_value_twd", "nav_difference_twd", "estimated_available_cash_twd",
                                 "formal_available_cash_twd", "available_cash_status", "estimated_reservations_twd",
                                 "reservation_status", "holdings_count", "valuation_complete", "account_valid",
                                 "demo_decision_ready", "submission_ready", "limitations"), summary),
        "review_status.csv": (("as_of", "trade_date", "role", "status", "data_through", "performance",
                               "recommendation_count", "reason", "demo", "submission_ready"), status),
        "review_recommendations.csv": (("as_of", "trade_date", "recommendation_id", "ticker", "proposal",
                                        "evidence_refs", "available_at", "limitations"), []),
    }


def write_decision_packet(packet: dict, output_dir: Path | str, *, project_root: Path | str) -> dict:
    """另存當次輸入、角色報告、prompt/schema 與 hashes，舊版本不覆寫。"""
    root = Path(project_root).resolve()
    # 在建產物前確認模板存在，避免只建半份可供呼叫的資料包。
    prompt = (root / "prompts/decision.md").read_bytes()
    schema = (root / "specs/internal/weighted_agent_draft.schema.json").read_bytes()
    json.loads(schema.decode("utf-8"))
    views = _csv_views(packet)
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / parse_trade_date(packet["trade_date"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    workspace = {"workspace_version": "1.0", "scope": "shared_agent_run", "as_of": packet["as_of"],
                 "trade_date": packet["trade_date"], "stage": "prepared",
                 "files": {"data_report": "data_report.json", "review_report": "review_report.json",
                           "account_report": "account_report.json", "evidence_packet": "evidence_packet.json",
                           "prompt": "decision.md", "draft_schema": "weighted_agent_draft.schema.json",
                           "manifest": "manifest.json", "agent_result": None, "dplan": None},
                 "roles": ["data_agent", "test_agent", "account_agent", "etf_agent"],
                 "time_policy": packet["time_policy"]}
    workspace["files"].update({name.removesuffix(".csv") + "_csv": name for name in views})
    workspace["csv_policy"] = {"role": "inspection_only", "primary_data": "JSON", "encoding": "UTF-8 BOM",
                               "unknown_values": "empty_cell", "ratios": "fraction_not_percent",
                               "money": "TWD", "price": "TWD/share", "shares": "shares"}
    for key, value in (("data_report.json", packet["data_report"]),
                       ("review_report.json", packet["review_report"]), ("evidence_packet.json", packet)):
        body = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        (run_dir / key).write_bytes(body)
        artifacts[key] = hashlib.sha256(body).hexdigest()
    for key, value in (("account_report.json", packet["account_report"]), ("workspace.json", workspace)):
        body = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        (run_dir / key).write_bytes(body)
        artifacts[key] = hashlib.sha256(body).hexdigest()
    for key, body in (("decision.md", prompt), ("weighted_agent_draft.schema.json", schema)):
        (run_dir / key).write_bytes(body)
        artifacts[key] = hashlib.sha256(body).hexdigest()
    for filename, (columns, rows) in views.items():
        artifacts[filename] = write_csv_view(run_dir / filename, columns, rows)
    manifest = {"manifest_version": "1.0", "scope": "prepared_decision_input", "created_at": now.isoformat(),
                "run_id": run_id, "packet_version_id": packet["packet_version_id"],
                "as_of": packet["as_of"], "trade_date": packet["trade_date"],
                "artifact_sha256": artifacts, "inputs": packet["data_report"]["inputs"],
                "demo_decision_ready": packet["demo_decision_ready"], "real_agent_decision": False,
                "submission_ready": False}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                            encoding="utf-8", newline="\n")
    return {"run_dir": str(run_dir), "packet_json": str(run_dir / "evidence_packet.json"),
            "manifest_json": str(run_dir / "manifest.json"), "prompt": str(run_dir / "decision.md"),
            "draft_schema": str(run_dir / "weighted_agent_draft.schema.json"),
            "workspace_json": str(run_dir / "workspace.json"), "account_report_json": str(run_dir / "account_report.json"),
            **{name.removesuffix(".csv") + "_csv": str(run_dir / name) for name in views}}
