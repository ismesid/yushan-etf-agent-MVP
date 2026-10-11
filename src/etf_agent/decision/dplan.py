"""D-Plan 4.2 編譯與保存；股數由程式推導，不抓行情或冒充模型。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from uuid import uuid4

from etf_agent.contracts import WeightedAgentDraft
from etf_agent.decision.portfolio import build_portfolio
from etf_agent.decision.markdown import render_plan_markdown


class DPlanError(ValueError):
    """凍結資料、引用或編譯條件不完整。"""


def load_prepared_packet(path: Path | str) -> dict:
    """只讀已封存packet，對回同目錄manifest hash；不沿引用開啟行情。"""
    path = Path(path).resolve()
    try:
        body = path.read_bytes()
        packet = json.loads(body.decode("utf-8-sig"))
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
        if (type(packet) is not dict or packet.get("packet_version") != "1.0"
                or packet.get("scope") != "historical_demo_decision_input"
                or manifest.get("artifact_sha256", {}).get(path.name) != hashlib.sha256(body).hexdigest()
                or manifest.get("packet_version_id") != packet.get("packet_version_id")
                or manifest.get("as_of") != packet.get("as_of") or manifest.get("trade_date") != packet.get("trade_date")):
            raise DPlanError("資料包與凍結manifest hash／日期／版本不一致")
        return packet
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, DPlanError):
            raise
        raise DPlanError(f"凍結資料包讀取失敗：{exc}") from exc


def _numbers(values: dict) -> dict:
    result = {}
    for name, value in values.items():
        if type(value) is int:
            result[name] = value
        elif type(value) in (str, float, Decimal):
            try:
                number = float(Decimal(str(value)))
                if not math.isfinite(number):
                    raise ValueError("非有限數值")
                result[name] = number
            except (InvalidOperation, ValueError):
                # 內部值包含scope等說明欄位，官方values只保留數字。
                if name != "scope":
                    raise DPlanError(f"觀察值 {name} 不能轉成官方 JSON 數字")
    if not result:
        raise DPlanError("官方觀察須有可核對的數值；缺價帳戶不能編成行情事實")
    return result


def compile_dplan(packet: dict, draft: WeightedAgentDraft, *, agent_metadata: dict | None = None,
                  team_id: str = "DEMO", decision_source: str = "fixture") -> dict:
    """從原模型理由編譯引用閉包；未知模型資訊保留缺失並交驗證器阻擋。"""
    from etf_agent.decision.validation import validate_dplan

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", team_id):
        raise DPlanError("team_id 格式不合法")
    if decision_source not in ("fixture", "real"):
        raise DPlanError("decision_source 須為 fixture 或 real")
    portfolio = build_portfolio(packet, draft)
    reviews = {row.ticker: row for row in draft.held_reviews}
    selections = {row.ticker: row for row in draft.selections}
    contexts = sorted(set(reviews) | set(selections))
    needed_o = set(draft.market_proposal.basis_obs_ids)
    for row in (*draft.held_reviews, *draft.selections):
        needed_o.update(row.supporting_obs_ids)
    original_o = {row["obs_id"]: row for row in packet["observations"]}
    if not needed_o <= original_o.keys():
        raise DPlanError("草稿引用不在凍結觀察內")
    selected_o = [row for row in packet["observations"] if row["obs_id"] in needed_o]
    needed_s = {ref for row in selected_o for ref in row["source_ref"]}
    selected_s = [row for row in packet["sources"] if row["source_id"] in needed_s]
    if needed_s != {row["source_id"] for row in selected_s}:
        raise DPlanError("觀察引用不在凍結來源內")
    smap = {row["source_id"]: f"S{index}" for index, row in enumerate(selected_s, 1)}
    omap = {row["obs_id"]: f"O{index}" for index, row in enumerate(selected_o, 1)}
    sources = [{"source_id": smap[row["source_id"]], "authority": row["authority"],
                "url": row["url"], "name": row["name"],
                # 只描述歷史日表截至該日；不是公開時間，不填published_at。
                "content_as_of": row["content_as_of_trade_date"] + "T23:59:59+08:00"}
               for row in selected_s]
    observations = [{"obs_id": omap[row["obs_id"]], "source_ref": [smap[ref] for ref in row["source_ref"]],
                     "statement": row["statement"].split(" 人工期初持股 ")[0],
                     "values": _numbers(row["values"])} for row in selected_o]
    inferences, imap = [], {}
    for ticker in contexts:
        reasoning = [row for row in (selections.get(ticker), reviews.get(ticker)) if row is not None]
        refs = list(dict.fromkeys(ref for row in reasoning for ref in row.supporting_obs_ids))
        logic = "\n".join(dict.fromkeys(row.rationale for row in reasoning))
        counter = "\n".join(dict.fromkeys(row.counter_evidence for row in reasoning if row.counter_evidence)) or None
        inf_id = f"I{len(inferences) + 1}"
        imap[ticker] = inf_id
        inferences.append({"inf_id": inf_id, "premise_refs": [omap[ref] for ref in refs],
                           "logic": logic, "counter_evidence": counter})
    decisions = [{"decision_id": row["decision_id"], "ticker": row["ticker"], "action": row["action"],
                  "target_weight": float(Decimal(row["target_weight"])),
                  "inference_refs": [imap[row["ticker"]]]} for row in portfolio["decisions"]]
    no_trade = [{"ticker": ticker, "reason_refs": [imap[ticker]]} for ticker in portfolio["no_trade_tickers"]]
    market = draft.market_proposal
    plan = {"schema_version": "4.2", "doc_type": "D-Plan", "team_id": team_id,
            "trade_date": packet["trade_date"], "sources": sources, "observations": observations,
            "market_view": {"basis_refs": [omap[ref] for ref in market.basis_obs_ids], "logic": market.rationale,
                            "regime": market.regime, "stance": market.stance,
                            "posture": {"net_exposure_intent": market.intended_flow,
                                        "target_cash_pct_range": list(market.proposed_cash_range)},
                            "counter_evidence": market.counter_evidence},
            "inferences": inferences, "decisions": decisions, "no_trade_decisions": no_trade,
            "orders": portfolio["orders"], "agent_metadata": dict(agent_metadata or {})}
    # 不能因JSON數字序列化跨整張邊界而默默改orders。
    plan = json.loads(json.dumps(plan, ensure_ascii=False, allow_nan=False))
    validation = validate_dplan(plan, packet, portfolio=portfolio)
    real = decision_source == "real" and bool(agent_metadata)
    return {"report_format_version": "1.0", "scope": "historical_demo_dplan_compilation",
            "plan": plan, "portfolio": portfolio, "validation": validation,
            "decision_source": decision_source, "real_agent_decision": real,
            "as_of": packet["as_of"], "trade_date": packet["trade_date"], "submission_ready": False,
            "limitations": ["歷史 demo，不確認正式參賽資格、庫存或主辦方語意驗證。",
                            "content_as_of 採日表日期末23:59:59描述截至當日內容；不是已知公開時間。",
                            "同endpoint系列來源正式接受、費用取整及成交帳務尚未確認。",
                            "未讀決策日行情；portfolio是前收估算，不能當實際成交或績效。"]}


def archive_code(project_root: Path | str, destination: Path | str) -> dict:
    """保存實跑程式與參數／提示／schema的內容版本，不使用舊HEAD冒稱乾淨版。"""
    root, target = Path(project_root).resolve(), Path(destination).resolve()
    paths = [*sorted((root / "src/etf_agent").rglob("*.py")),
             *sorted((root / "config").glob("*.json")), *sorted((root / "prompts").glob("*.md")),
             *sorted((root / "specs/internal").glob("*.json")), root / "pyproject.toml",
             root / "specs/official/04_D-Plan.schema_v4.2.json", root / "specs/official/07_D-Plan_guide_v4.2.md"]
    hashes = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        body = path.read_bytes()
        saved = target / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(body)
        hashes[relative] = hashlib.sha256(body).hexdigest()
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"code_version": "sha256:" + digest[:12], "files_sha256": hashes}


def write_compiled_plan(result: dict, output_dir: Path | str, *, project_root: Path | str,
                        packet: dict, draft: WeightedAgentDraft) -> dict:
    """保存候選／有效demo計畫、投影與驗證，輸入帳戶不變。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / result["trade_date"] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    version = archive_code(project_root, run_dir / "code")
    plan = result["plan"]
    if result["real_agent_decision"]:
        plan["agent_metadata"]["code_version"] = version["code_version"]
        from etf_agent.decision.validation import validate_dplan
        result["validation"] = validate_dplan(plan, packet, portfolio=result["portfolio"])
    accepted = result["real_agent_decision"] and result["validation"]["local_validation_ok"]
    filename = f"D-Plan_{plan['team_id']}_{plan['trade_date']}.json" if accepted else "dplan_candidate.json"
    markdown_filename = Path(filename).with_suffix(".md").name
    workspace = {"workspace_version": "1.0", "scope": "shared_agent_run", "as_of": result["as_of"],
                 "trade_date": result["trade_date"], "stage": "compiled_demo_frozen" if accepted else "compiled_candidate",
                 "roles": ["data_agent", "test_agent", "account_agent", "etf_agent"],
                 "files": {"data_report": "data_report.json", "review_report": "review_report.json",
                           "account_report": "account_report.json", "evidence_packet": "evidence_packet.json",
                           "agent_draft": "agent_draft.json", "portfolio": "portfolio.json",
                           "validation": "validation.json", "dplan": filename,
                           "plan_markdown": markdown_filename, "manifest": "manifest.json"}}
    artifacts = _write_compiled_csv(result, packet, draft, run_dir)
    markdown_body = render_plan_markdown(result, packet, draft).encode("utf-8")
    (run_dir / markdown_filename).write_bytes(markdown_body)
    artifacts[markdown_filename] = hashlib.sha256(markdown_body).hexdigest()
    for csv_name in artifacts:
        if csv_name.endswith(".csv"):
            workspace["files"][csv_name.removesuffix(".csv") + "_csv"] = csv_name
    for name, value in ((filename, plan), ("portfolio.json", result["portfolio"]),
                        ("validation.json", result["validation"]), ("evidence_packet.json", packet),
                        ("agent_draft.json", draft.to_dict()), ("compilation.json", result),
                        ("data_report.json", packet["data_report"]), ("review_report.json", packet.get("review_report", {})),
                        ("account_report.json", packet.get("account_report", {})), ("workspace.json", workspace)):
        body = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        (run_dir / name).write_bytes(body)
        artifacts[name] = hashlib.sha256(body).hexdigest()
    manifest = {"manifest_version": "1.0", "run_id": run_id, "created_at": now.isoformat(),
                "as_of": result["as_of"], "trade_date": result["trade_date"], "decision_source": result["decision_source"],
                "real_agent_decision": result["real_agent_decision"], "local_validation_ok": result["validation"]["local_validation_ok"],
                "plan_file": filename, "plan_markdown_file": markdown_filename,
                "code_archive": version, "artifact_sha256": artifacts,
                "submission_ready": False}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8", newline="\n")
    return {"run_dir": str(run_dir), "plan_json": str(run_dir / filename),
            "plan_markdown": str(run_dir / markdown_filename),
            "portfolio_json": str(run_dir / "portfolio.json"), "validation_json": str(run_dir / "validation.json"),
            "manifest_json": str(run_dir / "manifest.json"), "workspace_json": str(run_dir / "workspace.json"),
            **{name.removesuffix(".csv") + "_csv": str(run_dir / name)
               for name in artifacts if name.endswith(".csv")},
            "accepted_demo_plan": accepted}


def _write_compiled_csv(result: dict, packet: dict, draft: WeightedAgentDraft, directory: Path) -> dict:
    """人工檢查視圖來自同一JSON／草稿，不回寫股數或把前收估計當成交。"""
    from etf_agent.reports import write_csv_view

    portfolio, plan = result["portfolio"], result["plan"]
    selections = {row.ticker: row for row in draft.selections}
    reviews = {row.ticker: row for row in draft.held_reviews}
    rankings = {row["ticker"]: row for row in packet["data_report"]["rankings"]}
    decisions = {row["ticker"]: row for row in portfolio["decisions"]}
    positions = {row["ticker"]: row for row in portfolio["positions"]}
    context = {"as_of": result["as_of"], "trade_date": result["trade_date"],
               "demo": True, "decision_source": result["decision_source"]}
    decision_rows, position_rows, order_rows = [], [], []
    for ticker, position in positions.items():
        selection, review = selections.get(ticker), reviews.get(ticker)
        ranked = rankings.get(ticker, {})
        action = decisions[ticker]["action"] if ticker in decisions else "KEEP"
        decision_rows.append({**context, "ticker": ticker, "name": ranked.get("name"),
                              "rank": ranked.get("rank"), "score_ratio": ranked.get("score"),
                              "held_intent": review.intent if review else None, "action": action,
                              "current_shares": position["current_shares"],
                              "target_shares": position["target_shares"],
                              "target_weight_ratio": position["target_weight"],
                              "selection_rationale": selection.rationale if selection else None,
                              "held_review_rationale": review.rationale if review else None,
                              "selection_counter_evidence": selection.counter_evidence if selection else None,
                              "held_counter_evidence": review.counter_evidence if review else None,
                              "observation_refs": list(dict.fromkeys(ref for row in (selection, review)
                                                       if row for ref in row.supporting_obs_ids)),
                              "decision_id": decisions.get(ticker, {}).get("decision_id")})
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            value = Decimal(position["close_twd_per_share"]) * position["target_shares"]
        position_rows.append({**context, **position, "name": ranked.get("name"),
                              "target_market_value_twd": str(value),
                              "delta_shares": position["target_shares"] - position["current_shares"],
                              "portfolio_ok": portfolio["portfolio_ok"]})
    for order in portfolio["orders"]:
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            close = Decimal(positions[order["ticker"]]["close_twd_per_share"])
            notional = close * order["shares"]
            fee = notional * Decimal("0.001425")
            tax = notional * Decimal("0.003") if order["side"] == "SELL" else Decimal(0)
        order_rows.append({**context, **order, "close_twd_per_share": str(close),
                           "estimated_notional_twd": str(notional), "estimated_fee_twd": str(fee),
                           "estimated_tax_twd": str(tax), "price_basis": "previous_close_estimate"})
    summary = {**context, **{key: portfolio[key] for key in (
        "cash_before_twd", "buy_notional_twd", "sell_notional_twd", "fees_twd", "tax_twd",
        "cash_after_twd", "projected_nav_twd", "net_flow_twd", "cash_ratio", "portfolio_ok", "fee_policy")},
        "original_holdings_count": len(packet["account_snapshot"]["positions"]),
        "projected_holdings_count": sum(row["target_shares"] > 0 for row in positions.values()),
        "order_count": len(portfolio["orders"]), "no_trade_count": len(portfolio["no_trade_tickers"]),
        "market_regime": draft.market_proposal.regime, "market_stance": draft.market_proposal.stance,
        "intended_flow": draft.market_proposal.intended_flow,
        "target_cash_ratio": draft.market_proposal.cash_target,
        "declared_cash_range": list(draft.market_proposal.proposed_cash_range),
        "schema_ok": result["validation"]["schema_ok"],
        "semantic_ok": result["validation"]["semantic_ok"],
        "local_validation_ok": result["validation"]["local_validation_ok"],
        "formal_eligible": False, "submission_ready": False}
    views = {
        "agent_decisions.csv": (("as_of", "trade_date", "demo", "decision_source", "ticker", "name",
                                 "rank", "score_ratio", "held_intent", "action", "current_shares", "target_shares",
                                 "target_weight_ratio", "selection_rationale", "held_review_rationale",
                                 "selection_counter_evidence", "held_counter_evidence", "observation_refs", "decision_id"), decision_rows),
        "orders.csv": (("as_of", "trade_date", "demo", "decision_source", "ticker", "side", "shares", "decision_ref",
                        "close_twd_per_share", "estimated_notional_twd", "estimated_fee_twd", "estimated_tax_twd", "price_basis"), order_rows),
        "portfolio_positions.csv": (("as_of", "trade_date", "demo", "decision_source", "ticker", "name", "current_shares",
                                     "requested_target_shares", "target_shares", "delta_shares", "close_twd_per_share",
                                     "target_weight", "projected_weight", "target_market_value_twd", "portfolio_ok"), position_rows),
        "portfolio_summary.csv": (tuple(summary), [summary]),
        "validation_checks.csv": (("as_of", "trade_date", "demo", "decision_source", "code", "severity", "message"),
                                   [{**context, **row} for row in result["validation"]["checks"]]),
    }
    return {name: write_csv_view(directory / name, columns, rows) for name, (columns, rows) in views.items()}
