"""test_agent 隔離流程：封存閘門 → 單日行情 → 模擬／事後配置。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from math import isfinite
from pathlib import Path
from uuid import uuid4

from etf_agent.sub_agents.test_agent.evaluation import (
    EvaluationError, hindsight_ranking, read_json, sha256, simulate, verify_frozen, verify_unchanged,
)
from etf_agent.sub_agents.test_agent.hindsight import optimize_hindsight
from etf_agent.sub_agents.test_agent.providers.daily import daily_url, parse_daily
from etf_agent.providers.http import get_https
from etf_agent.reports import write_csv_view
from etf_agent.paths import project_root


def _write(path: Path, obj: dict):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _market(frozen: dict, run: Path, *, transport: str, cache_manifest: Path | None,
            progress) -> tuple[dict, dict]:
    """只持久化指定日，來源使用單日全市場報表，隔離manifest驗證後可重播。"""
    trade_date = frozen["trade_date"]
    cached = read_json(cache_manifest) if cache_manifest else None
    if cached and (cached.get("scope") != "evaluation_quarantine_market" or cached.get("trade_date") != trade_date):
        raise EvaluationError("隔離行情manifest日期或用途不符")
    raw_dir = run / "raw"
    raw_dir.mkdir()
    quotes, sources = {}, []
    wanted = set(frozen["packet"]["allowed_tickers"]) | set(frozen["packet"]["held_tickers"])
    markets = {row["ticker"]: row["market"] for row in frozen["packet"]["data_report"]["rankings"]}
    for market in ("TWSE", "TPEX"):
        url = daily_url(market, trade_date)
        if cached:
            entry = next((s for s in cached["sources"] if s["market"] == market), None)
            if not entry or entry["requested_url"] != url:
                raise EvaluationError("隔離行情來源索引不符")
            path = (cache_manifest.parent / entry["raw_file"]).resolve()
            if cache_manifest.parent.resolve() not in path.parents or sha256(path) != entry["raw_sha256"]:
                raise EvaluationError("隔離行情raw路徑或hash不符")
            body = path.read_bytes()
            source = dict(entry)
            source["cache_hit"] = True
        else:
            progress(f"test_agent：取得 {market} {trade_date} 單日官方行情，存至隔離區")
            response = get_https(url, transport=transport, timeout=30)
            body = response.body
            if response.status != 200:
                raise EvaluationError(f"{market} HTTP {response.status}，停止評估")
            source = {"market": market, "requested_url": url, "effective_url": response.url,
                      "fetched_at": response.fetched_at.isoformat(), "http_status": response.status,
                      "content_type": response.content_type, "transport": response.transport, "cache_hit": False}
        raw_path = raw_dir / f"{market}.json"
        raw_path.write_bytes(body)
        source.update(raw_file=str(raw_path.relative_to(run)).replace("\\", "/"), raw_sha256=sha256(raw_path))
        _write(run / f"{market}_source.json", source)
        parsed = parse_daily(body, market=market, trade_date=trade_date)
        selected = {t: row for t, row in parsed.items() if t in wanted and markets.get(t) == market}
        if set(quotes) & set(selected):
            raise EvaluationError("兩市場行情發現重複候選股票")
        quotes.update(selected)
        source.update(raw_file=str(raw_path.relative_to(run)).replace("\\", "/"),
                      raw_sha256=sha256(raw_path), source_row_count=len(parsed), retained_row_count=len(selected),
                      units={"volume": "shares", "amount": "TWD", "price": "TWD/share"})
        sources.append(source)
        progress(f"test_agent：{market} 保留 {len(selected)} 檔候選，量值／日期核對通過")
    manifest = {"manifest_version": "1.0", "scope": "evaluation_quarantine_market", "trade_date": trade_date,
                "sources": sources, "network_requests": 0 if cached else 2,
                "missing_tickers": sorted(wanted - set(quotes)), "row_count": len(quotes),
                "decision_input_allowed": False}
    _write(run / "market_manifest.json", manifest)
    _write(run / "market_quotes.json", {"trade_date": trade_date, "quotes": quotes})
    return quotes, manifest


def evaluate_frozen_plan(workspace_path: Path | str, *, output_dir: Path | str,
                         cache_manifest: Path | str | None = None, transport: str = "auto",
                         time_limit: float = 120, progress=None) -> dict:
    """獨立評估入口；本批沒有新LLM呼叫，也不把事後報告送回當日packet。"""
    progress = progress or (lambda message: None)
    if not isfinite(time_limit) or time_limit <= 0:
        raise EvaluationError("求解時間上限須為有限正數，拒絕先下載再報參數錯誤")
    frozen = verify_frozen(workspace_path)
    output = Path(output_dir).resolve()
    original = Path(frozen["root"])
    if output == original or original in output.parents or output in original.parents:
        raise EvaluationError("評估目錄必須與原決策根目錄隔離，不能在其內或父目錄")
    cached = Path(cache_manifest).resolve() if cache_manifest else None
    if cached and (original == cached.parent or original in cached.parents):
        raise EvaluationError("評估行情不能從原決策根目錄讀取")
    now = datetime.now(timezone(timedelta(hours=8)))
    run = output / frozen["trade_date"] / (now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8])
    run.mkdir(parents=True)
    from etf_agent.decision.dplan import archive_code
    version = archive_code(project_root(), run / "code")
    freeze = {"scope": "post_decision_evaluation_gate", "checked_at": now.isoformat(),
              "as_of": frozen["as_of"], "trade_date": frozen["trade_date"],
              "original_workspace": frozen["workspace_path"], "frozen_sha256": frozen["frozen_sha256"],
              "evaluation_code_archive": version,
              "real_agent_decision": True, "accepted_demo_plan": True, "decision_input_allowed": False}
    _write(run / "freeze_gate.json", freeze)
    try:
        quotes, market = _market(frozen, run, transport=transport, cache_manifest=cached, progress=progress)
        account, previous, trade_date = frozen["account"], frozen["previous_closes"], frozen["trade_date"]
        no_trade = simulate(account, [], quotes, trade_date=trade_date, previous_closes=previous, scenario="no_trade")
        actual = simulate(account, frozen["plan"]["orders"], quotes, trade_date=trade_date,
                          previous_closes=previous, scenario="frozen_dplan")
        progress(f"test_agent：固定 D-Plan 模擬完成；搜尋全部 {len(frozen['packet']['allowed_tickers'])} 檔整張配置")
        oracle = optimize_hindsight(account, frozen["packet"]["allowed_tickers"], previous, quotes,
                                    trade_date=trade_date, time_limit=time_limit)
        ranking = hindsight_ranking(frozen["packet"]["allowed_tickers"], quotes, previous)
        summaries = [no_trade["summary"], actual["summary"]]
        accepted_oracle = oracle["status"] in ("optimal", "feasible_limit_reached")
        if accepted_oracle:
            summaries.append(oracle["solution"]["summary"])
        with localcontext() as context:
            context.prec = 50
            baseline = no_trade["summary"]["end_nav_twd"]
            nav_actual = actual["summary"]["end_nav_twd"]
            benefit = str(Decimal(nav_actual) - Decimal(baseline)) if nav_actual and baseline else None
            best_nav = oracle["solution"]["summary"]["end_nav_twd"] if accepted_oracle else None
            shortfall = str(Decimal(best_nav) - Decimal(nav_actual)) if best_nav and nav_actual else None
        recommendations = []
        target = {p["ticker"]: p["end_shares"] for p in oracle["solution"]["positions"]} if accepted_oracle else {}
        for fill in actual["fills"]:
            recommendations.append({"ticker": fill["ticker"], "planned_side": fill["side"],
                                    "planned_shares": fill["requested_shares"], "fill_status": fill["fill_status"],
                                    "benefit_vs_skip_twd": fill["benefit_vs_skip_twd"],
                                    "hindsight_target_shares": target.get(fill["ticker"], 0) if accepted_oracle else None,
                                    "basis": "T_day_VWAP_and_close_hindsight_only",
                                    "recommendation": "事後個別比較宜取消" if fill["benefit_vs_skip_twd"] is not None
                                    and Decimal(fill["benefit_vs_skip_twd"]) < 0 else "事後個別比較有利"
                                    if fill["benefit_vs_skip_twd"] is not None else "資料不足"})
        report = {"report_version": "1.0", "role": "test_agent", "scope": "isolated_post_decision_evaluation",
                  "status": "evaluated" if actual["summary"]["end_nav_twd"] is not None else "partial_missing_valuation",
                  "as_of": trade_date, "data_through": trade_date, "decision_as_of": frozen["as_of"],
                  "scenario_summaries": summaries, "frozen_dplan_benefit_vs_no_trade_twd": benefit,
                  "hindsight_opportunity_vs_frozen_dplan_twd": shortfall,
                  "hindsight_status": oracle["status"], "recommendations": recommendations,
                  "frozen_dplan_constraint_checks": actual["checks"],
                  "frozen_dplan_constraint_checks_ok": actual["constraint_checks_ok"],
                  "issues": actual["issues"], "demo": True, "formal_eligible": False, "submission_ready": False,
                  "decision_input_allowed": False,
                  "assumptions": ["同一9/30人工期初帳與1,000,000,000元NAV；10/1價格是後驗真實官方資料。",
                                  "委託股數固定，不以10/1行情重算原D-Plan；有精確量值者按日均價全數模擬成交。",
                                  "買賣各0.1425%費用、賣出0.3%稅；50位Decimal，不做未確認的結算取整。",
                                  "以10/1收盤價估NAV，不計未核對股利／公司行動；這是價格收益模擬。",
                                  "採同日現金淨額結算，未模擬撮合順序／容量／滑價；不是主辦方實際成交或庫存。",
                                  "個別委託執行／取消比較不代表整組取消後仍滿足現金與持股限制。",
                                  "事後配置未承襲原模型12%現金目標，而在明列財務限制內重新搜尋；未改策略設定。",
                                  "歷史報表於模型封存後下載；不保證報表沒有事後修訂。"]}
        if any(s.get("source_metadata_recovered") for s in market["sources"]):
            report["assumptions"].append("首次TPEx解析失敗後重用隔離raw，未保存的fetched_at／content_type／effective_url維持null。")
        _write(run / "review_report.json", report)
        _write(run / "frozen_dplan_simulation.json", actual)
        _write(run / "no_trade_simulation.json", no_trade)
        _write(run / "hindsight_optimization.json", oracle)
        _write(run / "hindsight_ranking.json", {"rows": ranking})
        if actual["account_snapshot"]:
            _write(run / "simulated_account.json", actual["account_snapshot"])
        if accepted_oracle:
            _write(run / "hindsight_account.json", oracle["solution"]["account_snapshot"])
        csvs = {}

        def csv(name, columns, rows):
            csvs[name] = write_csv_view(run / name, columns, rows)

        quote_columns = ("ticker", "name", "market", "trade_date", "trading_status", "close_twd_per_share", "volume_shares",
                         "amount_twd", "vwap_twd_per_share", "source_key", "source_url", "raw_sha256")
        csv("market_quotes.csv", quote_columns, [quotes[t] for t in sorted(quotes)])
        csv("performance.csv", tuple(summaries[0]), summaries)
        fill_columns = ("ticker", "side", "requested_shares", "filled_shares", "fill_status", "vwap_twd_per_share",
                        "notional_twd", "fee_twd", "tax_twd", "cash_delta_twd", "decision_ref", "benefit_vs_skip_twd")
        csv("fills.csv", fill_columns, actual["fills"])
        position_columns = ("ticker", "initial_shares", "end_shares", "previous_close_twd_per_share",
                            "close_twd_per_share", "market_value_twd")
        csv("end_positions.csv", position_columns, actual["positions"])
        csv("hindsight_ranking.csv", tuple(ranking[0]), ranking)
        csv("hindsight_orders.csv", ("ticker", "side", "shares"), oracle["orders"] if accepted_oracle else [])
        csv("hindsight_positions.csv", position_columns, oracle["solution"]["positions"] if accepted_oracle else [])
        csv("review_recommendations.csv", ("ticker", "planned_side", "planned_shares", "fill_status", "benefit_vs_skip_twd",
                                          "hindsight_target_shares", "basis", "recommendation"), recommendations)
        verify_unchanged(frozen["frozen_sha256"])
        artifacts = {str(p.relative_to(run)).replace("\\", "/"): sha256(p) for p in run.rglob("*") if p.is_file()}
        manifest = {"manifest_version": "1.0", "scope": "evaluation_quarantine", "created_at": now.isoformat(),
                    "completed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                    "as_of": trade_date, "decision_as_of": frozen["as_of"], "decision_input_allowed": False,
                    "original_frozen_unchanged": True, "frozen_file_count": len(frozen["frozen_sha256"]),
                    "original_plan_path": str(frozen["files"]["dplan"]),
                    "original_plan_sha256": frozen["frozen_sha256"][str(frozen["files"]["dplan"])],
                    "evaluation_code_archive": version,
                    "artifact_sha256": artifacts, "hindsight_status": oracle["status"],
                    "real_market_data": True, "real_fills": False, "new_model_calls": 0,
                    "formal_eligible": False, "submission_ready": False}
        _write(run / "manifest.json", manifest)
        progress(f"test_agent：{oracle['status']}；原決策 {len(frozen['frozen_sha256'])} 檔hash未變")
        return {"run_dir": str(run), "report_json": str(run / "review_report.json"),
                "market_manifest": str(run / "market_manifest.json"), "manifest_json": str(run / "manifest.json"),
                "network_requests": market["network_requests"], "hindsight_status": oracle["status"],
                "original_frozen_unchanged": True, "scenarios": summaries,
                "frozen_dplan_benefit_vs_no_trade_twd": benefit, "hindsight_opportunity_vs_frozen_dplan_twd": shortfall,
                "csv_files": [str(run / name) for name in csvs], "submission_ready": False}
    except Exception as exc:
        _write(run / "failure.json", {"error_type": type(exc).__name__, "message": str(exc),
                                      "decision_input_allowed": False, "submission_ready": False})
        verify_unchanged(frozen["frozen_sha256"])
        raise
