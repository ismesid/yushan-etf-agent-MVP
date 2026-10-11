"""離線合約示例、官方白名單核對及歷史樣本；正式完整流程尚待後續批次。"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from etf_agent.sub_agents.account_agent.account import AccountError, analyze_account, write_account_report
from etf_agent.decision.providers.base import AgentResult
from etf_agent.calendar import CalendarError, download_calendar, load_calendar
from etf_agent.contracts import (
    AccountSnapshot, AgentDraft, ContractError, DatasetSplitPlan, FeatureTable,
    MarketSnapshot, PortfolioProposal, ValidationReport, WeightedAgentDraft,
)
from etf_agent.coverage import PriceCoverageError, check_daily_prices, write_coverage_report
from etf_agent.evidence import EvidenceError, prepare_decision, write_decision_packet
from etf_agent.sub_agents.data_agent.features import FeatureAnalysisError, analyze_history_features, write_feature_analysis
from etf_agent.sub_agents.test_agent.history import download_history_sample, download_history_universe, export_history_sample
from etf_agent.sub_agents.data_agent.history_windows import HistoryWindowError, check_history_windows, write_window_report
from etf_agent.sub_agents.test_agent.providers.monthly import HistoryDataError
from etf_agent.sub_agents.data_agent.ranking import RankingError, analyze_history_rankings, write_ranking_analysis
from etf_agent.sub_agents.data_agent import DataAgentError
from etf_agent.sub_agents.test_agent import ReviewReportError
from etf_agent.universe import UniverseError, load_universe


DEMO_TYPES = {
    "market_snapshot": MarketSnapshot,
    "account_snapshot": AccountSnapshot,
    "feature_table": FeatureTable,
    "agent_draft": AgentDraft,
    "portfolio_proposal": PortfolioProposal,
    "validation_report": ValidationReport,
    "dataset_split_plan": DatasetSplitPlan,
    "agent_result": AgentResult,
}


def load_demo(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if type(raw) is not dict or set(raw) != {"note", *DEMO_TYPES}:
        raise ContractError("fixture 須包含 note 與所有約定合約，不接受額外欄位")
    if type(raw["note"]) is not str or not raw["note"].strip():
        raise ContractError("fixture 須明示測試資料用途")
    loaded = {name: model.from_dict(raw[name]) for name, model in DEMO_TYPES.items()}
    for name, model in DEMO_TYPES.items():
        if model.from_dict(json.loads(json.dumps(loaded[name].to_dict(), allow_nan=False))) != loaded[name]:
            raise ContractError(f"{name}: JSON往返不一致")

    market, account = loaded["market_snapshot"], loaded["account_snapshot"]
    features, draft = loaded["feature_table"], loaded["agent_draft"]
    proposal, report = loaded["portfolio_proposal"], loaded["validation_report"]
    result, split = loaded["agent_result"], loaded["dataset_split_plan"]
    if not (market.data_origin == features.origin == result.provider == "fixture"
            and proposal.allocation_method == "fixture" and account.demo and account.status == "demo"
            and not account.reconciled and report.mode == "demo" and not report.submission_ready):
        raise ContractError("contracts-demo 只接受明示測試資料、測試帳與fixture草稿")
    if result.draft != draft:
        raise ContractError("AgentResult 必須對應同一份草稿")
    if not (features.snapshot_id == proposal.market_snapshot_id == market.snapshot_id
            and proposal.account_snapshot_id == account.snapshot_id
            and features.dataset_version == split.dataset_version == market.dataset_version):
        raise ContractError("合約間快照或資料版本不一致")
    if account.as_of_trade_date != market.previous_trade_date:
        raise ContractError("帳戶日期不符合前一交易日")
    if any(row.window_end > market.previous_trade_date for row in features.rows):
        raise ContractError("因子視窗含未來日期")

    held = {position.ticker for position in account.positions}
    allowed = {bar.ticker for bar in market.prices}
    observations = {ref for row in features.rows for ref in row.observation_ids}
    draft.validate_context(allowed_tickers=allowed, held_tickers=held, observation_ids=observations)
    proposal.validate_context(held_tickers=held, selected_tickers={s.ticker for s in draft.selections})
    closes = {bar.ticker: bar.close_raw for bar in market.prices if bar.trade_date == market.previous_trade_date}
    if any(closes.get(position.ticker) is None for position in account.positions):
        raise ContractError("demo期初持股缺少前收")
    stock_value = sum((position.shares * closes[position.ticker] for position in account.positions), Decimal(0))
    if account.cash_twd + stock_value != account.nav_twd:
        raise ContractError("demo期初NAV不等於現金加持股市值")
    loaded["stock_value_twd"] = stock_value
    loaded["note"] = raw["note"]
    return loaded


def demo_summary(loaded: dict) -> dict:
    market, account = loaded["market_snapshot"], loaded["account_snapshot"]
    features, draft = loaded["feature_table"], loaded["agent_draft"]
    proposal, report = loaded["portfolio_proposal"], loaded["validation_report"]
    result, split = loaded["agent_result"], loaded["dataset_split_plan"]
    return {
        "mode": "demo", "note": loaded["note"], "contract_version": "1.0",
        "contracts_loaded": list(DEMO_TYPES), "roundtrip": "PASS",
        "trade_date": market.trade_date.isoformat(), "snapshot_cutoff": market.snapshot_cutoff.isoformat(),
        "data_origin": market.data_origin, "price_rows": len(market.prices),
        "price_dates": sorted({bar.trade_date.isoformat() for bar in market.prices}),
        "holdings_count": len(account.positions), "cash_twd": str(account.cash_twd),
        "stock_value_twd": str(loaded["stock_value_twd"]), "nav_twd": str(account.nav_twd),
        "nav_identity": "PASS", "account_status": account.status, "reconciled": account.reconciled,
        "features_origin": features.origin, "feature_rows": len(features.rows),
        "selected_count": len(draft.selections), "held_review_count": len(draft.held_reviews),
        "allocation_method": proposal.allocation_method, "cash_target": str(proposal.cash_target),
        "provider": result.provider, "actual_model_version": result.actual_model_version,
        "usage": result.usage, "validation_scope": report.scope,
        "submission_ready": report.submission_ready, "dataset_split_plan": split.to_dict(),
        "research_history_ready": False, "trading_day_gap_verified": False,
        "pending": ["真實行情/交易日曆", "21日因子計算", "真實投資模型決策", "配置及官方股數推導",
                    "D-Plan結構與語意驗證", "SQLite帳務與核對", "回測/標籤/時間切分執行"],
    }


def _show_summary(summary: dict):
    print("離線共用合約示例（全部為人工測試資料）")
    print(f"載入：六種核心合約、研究切分設定、AgentResult；JSON往返：{summary['roundtrip']}")
    print(f"測試決策日：{summary['trade_date']}；截止：{summary['snapshot_cutoff']}（自訂測試時間）")
    print(f"行情：{summary['price_rows']}列，日期：{', '.join(summary['price_dates'])}")
    print(f"持股：{summary['holdings_count']}檔；現金：{summary['cash_twd']}元；股票市值：{summary['stock_value_twd']}元")
    print(f"NAV：{summary['nav_twd']}元；現金＋股票市值核對：{summary['nav_identity']}")
    print(f"帳戶：{summary['account_status']}；reconciled={str(summary['reconciled']).lower()}")
    print(f"因子：{summary['features_origin']}假值；選股：{summary['selected_count']}檔；原持股review：{summary['held_review_count']}筆")
    print("草稿為人工fixture；模型版本=null；用量=null；沒有真實投資模型呼叫")
    split = summary["dataset_split_plan"]
    print(f"研究切分示例：train {split['train_start']}～{split['train_end']}；"
          f"validation {split['validation_start']}～{split['validation_end']}；"
          f"test {split['test_start']}～{split['test_end']}")
    print("日期順序/不重疊設定已檢查；歷史資料、交易日gap、回測與訓練尚未實作")
    print(f"驗證範圍：{summary['validation_scope']}；submission_ready=false")


def _show_history_summary(result: dict, *, offline: bool = False):
    if offline:
        print("已保存官方歷史資料離線重新匯出（無新下載；fetched_at 保留原資料取得時間）")
    else:
        print("官方歷史資料下載樣本（真實價量；未核實公司行動／歷史已知時間，不是正式提交或回測結果）")
    for source in result["sources"]:
        if source["status"] == "success":
            print(f"{source['market']} {source['ticker']}：{source['row_count']}列，"
                  f"{source['first_trade_date']}～{source['last_trade_date']}；"
                  f"原單位={source['units']['source_volume']}/{source['units']['source_amount']}；"
                  f"精確量值={str(source['exact_volume_amount']).lower()}")
            if source.get("fetched_at"):
                print(f"原資料取得時間：{source['fetched_at']}")
        else:
            print(f"{source['market']} {source['ticker']}：失敗，{source.get('error')}", file=sys.stderr)
    print(f"每日價量：{len(result['daily_prices'])}個日檔，共{result['row_count']}列；{result['daily_dir']}")
    if result["daily_prices"]:
        print(f"首個日檔：{result['daily_prices'][0]['prices_csv']}")
    print(f"個股月表：{result['monthly_dir']}")
    print(f"來源網址與原始資料索引：{result['manifest']}")
    print("CSV成交量以張表示並保留小數；價格／均價為千元／張，金額為千元；原單位、網址與hash保存在manifest。")
    print("日表與月表來自同一清洗結果；日表作讀取入口，月表供查閱，勿同時合併兩者。")
    print("均價=成交金額÷成交量，顯示8位小數；TPEx reported均價是報表估算，精確量值／均價留空。")
    print("CSV空欄代表未知，不能當成0；當日均價供收盤後參考，不可用於當日盤前決策。")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="玉山 ETF MVP：資料合約、歷史分析與帳戶市值核對")
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("evaluate-plan", help="test_agent封存後隔離取得交易日行情，核算收益與全候選事後最佳化")
    evaluate.add_argument("--workspace", type=Path, required=True, help="真實決策已驗收的共用workspace.json")
    evaluate.add_argument("--output", type=Path, default=Path("data/cache/evaluation_quarantine"))
    evaluate.add_argument("--market-manifest", type=Path, help="重播明確指定的隔離行情，不新下載")
    evaluate.add_argument("--transport", choices=("auto", "urllib", "curl"), default="auto")
    evaluate.add_argument("--time-limit", type=float, default=120, help="事後整數配置求解秒數上限")
    evaluate.add_argument("--json", action="store_true")
    refresh = commands.add_parser("refresh-decision", help="重新下載九月資料並建立四個角色共用的歷史決策輸入")
    refresh.add_argument("--month", default="2025-09")
    refresh.add_argument("--as-of", default="2025-09-30")
    refresh.add_argument("--trade-date", default="2025-10-01")
    refresh.add_argument("--account", type=Path, required=True)
    refresh.add_argument("--calendar", type=Path, required=True)
    refresh.add_argument("--profile", type=Path, default=Path("config/ranking.json"))
    refresh.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    refresh.add_argument("--universe-manifest", type=Path)
    refresh.add_argument("--output", type=Path, default=Path("data/cache/integrated_runs"))
    refresh.add_argument("--json", action="store_true")
    decide = commands.add_parser("decide-plan", help="以凍結資料呼叫真實Codex，驗證並封存demo計畫")
    decide.add_argument("--packet", type=Path, required=True)
    decide.add_argument("--output", type=Path, required=True)
    decide.add_argument("--team-id", default="DEMO")
    decide.add_argument("--max-attempts", type=int, choices=(1, 2), default=2)
    decide.add_argument("--model", help="本次明確選用的模型ID；不更改本機全域設定")
    decide.add_argument("--json", action="store_true")
    demo_account = commands.add_parser("build-demo-account", help="以九月三因子末25名建立10億元人工期初帳戶與檢查CSV")
    demo_account.add_argument("--ranking-metadata", type=Path, required=True)
    demo_account.add_argument("--as-of", default="2025-09-30")
    demo_account.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    demo_account.add_argument("--universe-manifest", type=Path)
    demo_account.add_argument("--output", type=Path, default=Path("data/cache/account_demo"))
    demo_account.add_argument("--account-output", type=Path, help="明確指定要寫入或替換的demo帳戶JSON")
    demo_account.add_argument("--json", action="store_true")
    demo = commands.add_parser("contracts-demo", help="讀取fixture、檢查合約並展示demo帳")
    demo.add_argument("--fixture", type=Path, default=Path("tests/fixtures/contracts_demo.json"))
    demo.add_argument("--json", action="store_true", help="以JSON輸出示例摘要")
    history = commands.add_parser("history-sample", help="連網下載2330與5274的一個已完成月份，保存原始資料與CSV")
    history.add_argument("--month", required=True, help="歷史月份 YYYY-MM，如2025-09")
    history.add_argument("--output", type=Path, default=Path("data/cache/history_sample"))
    history.add_argument("--transport", choices=("auto", "urllib", "curl"), default="auto",
                         help="HTTPS工具：auto優先使用既有curl，否則Python urllib；都保留憑證驗證")
    export = commands.add_parser("history-export", help="以已保存官方原始JSON離線重新匯出CSV，不連網")
    export.add_argument("--manifest", required=True, type=Path, help="既有歷史樣本的manifest.json")
    export.add_argument("--output", type=Path, default=Path("data/cache/history_sample"))
    full_history = commands.add_parser("history-universe", help="低速下載 F05 全 150 檔的一個已完成月份")
    full_history.add_argument("--month", required=True, help="資料月份 YYYY-MM")
    full_history.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    full_history.add_argument("--universe-manifest", type=Path)
    full_history.add_argument("--cache-manifest", type=Path, help="優先核對並重用既有成功 raw，壞快取阻擋")
    full_history.add_argument("--output", type=Path, default=Path("data/cache/history_universe"))
    full_history.add_argument("--transport", choices=("auto", "urllib", "curl"), default="auto")
    whitelist = commands.add_parser("universe-check", help="離線核對 F05 股票白名單與來源版本")
    whitelist.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    whitelist.add_argument("--manifest", type=Path, help="預設使用白名單同名 .manifest.json")
    whitelist.add_argument("--json", action="store_true", help="以 JSON 輸出白名單核對摘要")
    prices = commands.add_parser("prices-check", help="離線核對每日 CSV 的白名單覆蓋、價格與缺件")
    prices.add_argument("--prices", type=Path, required=True, help="整理後 CSV 4.0 每日價量檔")
    prices.add_argument("--date", required=True, help="預期資料日 YYYY-MM-DD，不是決策日")
    prices.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    prices.add_argument("--universe-manifest", type=Path, help="白名單來源版本紀錄")
    prices.add_argument("--output", type=Path, default=Path("data/cache/coverage"))
    prices.add_argument("--json", action="store_true", help="以 JSON 輸出報告及產物路徑")
    calendar_command = commands.add_parser("calendar-download", help="取得官方年度開休市表，保存指定月份日曆")
    calendar_command.add_argument("--month", required=True, help="已完成月份 YYYY-MM")
    calendar_command.add_argument("--output", type=Path, default=Path("data/cache/calendar"))
    calendar_command.add_argument("--transport", choices=("auto", "urllib", "curl"), default="auto")
    windows = commands.add_parser("history-window-check", help="離線核對各股截至資料日的 21 筆價格視窗")
    windows.add_argument("--manifest", required=True, type=Path, help="全股票歷史下載 manifest.json")
    windows.add_argument("--calendar", required=True, type=Path, help="calendar-download 保存的 calendar.json")
    windows.add_argument("--as-of", required=True, help="已完成歷史資料截止日，非盤前決策日 YYYY-MM-DD")
    windows.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    windows.add_argument("--universe-manifest", type=Path)
    windows.add_argument("--output", type=Path, default=Path("data/cache/history_windows"))
    features = commands.add_parser("history-features", help="依既有價格視窗離線產生原價三因子分析")
    features.add_argument("--window-report", required=True, type=Path, help="已保存的 window_report.json")
    features.add_argument("--output", type=Path, default=Path("data/cache/features"))
    rankings = commands.add_parser("history-rankings", help="依既有精確因子值離線排名，保存各因子貢獻與總分")
    rankings.add_argument("--feature-metadata", required=True, type=Path, help="history-features 保存的 metadata.json")
    rankings.add_argument("--profile", type=Path, default=Path("config/ranking.json"), help="統一因子方向與權重設定")
    rankings.add_argument("--output", type=Path, default=Path("data/cache/rankings"))
    account_check = commands.add_parser("account-check", help="離線匯入獨立帳戶 JSON，以指定歷史收盤核對市值與 NAV")
    account_check.add_argument("--account", required=True, type=Path, help="AccountSnapshot 1.0 JSON；非整包合約 fixture")
    account_check.add_argument("--ranking-metadata", required=True, type=Path, help="既有排名 metadata 的日表來源與驗收 hash")
    account_check.add_argument("--as-of", required=True, help="明確指定估值日 YYYY-MM-DD；只讀該日日表")
    account_check.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    account_check.add_argument("--universe-manifest", type=Path)
    account_check.add_argument("--output", type=Path, default=Path("data/cache/account_checks"))
    account_check.add_argument("--json", action="store_true", help="以 JSON 輸出完整核對報告與產物路徑")
    prepare = commands.add_parser("prepare-decision", help="離線整合資料與前日檢視，凍結主 Agent 的歷史 demo 輸入")
    prepare.add_argument("--account", required=True, type=Path)
    prepare.add_argument("--ranking-metadata", required=True, type=Path)
    prepare.add_argument("--as-of", required=True, help="市場資料截止日，不讀較晚行情")
    prepare.add_argument("--trade-date", required=True, help="預定決策日，須晚於資料截止日")
    prepare.add_argument("--universe", type=Path, default=Path("data/universe.csv"))
    prepare.add_argument("--universe-manifest", type=Path)
    prepare.add_argument("--output", type=Path, default=Path("data/cache/decision_packets"))
    prepare.add_argument("--workspace-root", type=Path, help="重用指定shared run九月資料，替換帳戶並更新共用索引")
    prepare.add_argument("--json", action="store_true")
    compile_plan = commands.add_parser("compile-plan", help="將權重草稿編譯為前收估算與D-Plan候選，執行本地驗證")
    compile_plan.add_argument("--packet", required=True, type=Path)
    compile_plan.add_argument("--draft", required=True, type=Path)
    compile_plan.add_argument("--agent-metadata", type=Path, help="實際模型執行資訊；缺少時保存BLOCK，不填假模型")
    compile_plan.add_argument("--decision-source", choices=("fixture", "real"), default="fixture")
    compile_plan.add_argument("--team-id", default="DEMO")
    compile_plan.add_argument("--output", type=Path, default=Path("data/cache/plans"))
    compile_plan.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "build-demo-account":
        from etf_agent.sub_agents.account_agent.account import build_weak_demo_account, write_weak_demo_account
        try:
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            report = build_weak_demo_account(args.ranking_metadata, as_of=args.as_of, universe=universe)
            outputs = write_weak_demo_account(report, args.output)
            if args.account_output is not None:
                args.account_output.parent.mkdir(parents=True, exist_ok=True)
                args.account_output.write_bytes(Path(outputs["account_json"]).read_bytes())
                outputs["fixture_account_json"] = str(args.account_output.resolve())
        except (AccountError, UniverseError, OSError, ValueError) as exc:
            print(f"弱期初帳戶建立失敗：{exc}", file=sys.stderr)
            return 2
        print(json.dumps({"construction": report["construction"],
                          "account": report["account_snapshot"], "outputs": outputs},
                         ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if args.command == "evaluate-plan":
        from etf_agent.sub_agents.test_agent import evaluate_trade_day
        try:
            result = evaluate_trade_day(args.workspace, output_dir=args.output,
                                        cache_manifest=args.market_manifest, transport=args.transport,
                                        time_limit=args.time_limit,
                                        progress=lambda message: print(message, file=sys.stderr, flush=True))
        except ImportError:
            print('缺少隔離評估套件，使用 .venv 安裝專案的 evaluation 額外依賴。', file=sys.stderr)
            return 2
        except (OSError, ValueError, KeyError) as exc:
            print(f"隔離評估未完成：{exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result["hindsight_status"] in ("optimal", "feasible_limit_reached") else 4
    if args.command == "decide-plan":
        from etf_agent.decision.providers.codex_cli import CodexProvider, CodexProviderError
        from etf_agent.decision.runner import DecisionRunError, decide_plan
        try:
            result = decide_plan(args.packet, output_dir=args.output,
                                 project_root=Path(__file__).resolve().parents[2],
                                 team_id=args.team_id, max_attempts=args.max_attempts,
                                 provider=CodexProvider(model=args.model) if args.model else None,
                                 progress=lambda message: print(message, file=sys.stderr, flush=True))
        except (CodexProviderError, DecisionRunError, OSError, ValueError) as exc:
            print(f"真實決策未完成：{exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result["accepted_demo_plan"] else 4
    if args.command == "refresh-decision":
        from etf_agent.pipeline import PipelineError, refresh_prepare
        def refresh_progress(completed, total, entry):
            print(f"[{completed}/{total}] {entry['market']} {entry['ticker']} {entry['status']}",
                  file=sys.stderr, flush=True)
        try:
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            result = refresh_prepare(month=args.month, as_of=args.as_of, trade_date=args.trade_date,
                                     account_path=args.account, output_dir=args.output, universe=universe,
                                     calendar_path=args.calendar, profile_path=args.profile,
                                     progress=refresh_progress)
        except (PipelineError, UniverseError, OSError, ValueError) as exc:
            print(f"重新取得決策資料失敗：{exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result["demo_decision_ready"] else 2
    if args.command == "compile-plan":
        from etf_agent.decision.dplan import DPlanError, compile_dplan, load_prepared_packet, write_compiled_plan
        from etf_agent.decision.portfolio import PortfolioError
        try:
            from jsonschema import Draft202012Validator, FormatChecker
            packet = load_prepared_packet(args.packet)
            schema_file = args.packet.parent / "weighted_agent_draft.schema.json"
            manifest = json.loads((args.packet.parent / "manifest.json").read_text(encoding="utf-8"))
            import hashlib
            schema_body = schema_file.read_bytes()
            if hashlib.sha256(schema_body).hexdigest() != manifest["artifact_sha256"][schema_file.name]:
                raise DPlanError("凍結草稿schema hash不一致")
            schema = json.loads(schema_body.decode("utf-8"))
            raw = json.loads(args.draft.read_text(encoding="utf-8-sig"))
            errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(raw), key=lambda e: str(e.path))
            if errors:
                raise DPlanError(f"草稿schema錯誤：{errors[0].message}")
            draft = WeightedAgentDraft.from_dict(raw)
            metadata = json.loads(args.agent_metadata.read_text(encoding="utf-8-sig")) if args.agent_metadata else None
            if metadata is not None and type(metadata) is not dict:
                raise DPlanError("模型metadata須為JSON object")
            result = compile_dplan(packet, draft, agent_metadata=metadata, team_id=args.team_id,
                                   decision_source=args.decision_source)
            outputs = write_compiled_plan(result, args.output, project_root=Path(__file__).resolve().parents[2],
                                           packet=packet, draft=draft)
        except ImportError:
            print("缺少jsonschema；請使用已安裝依賴的 .venv\\Scripts\\python.exe。", file=sys.stderr)
            return 2
        except (DPlanError, PortfolioError, ContractError, OSError, ValueError, KeyError) as exc:
            print(f"計畫編譯錯誤：{exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"result": result, "outputs": outputs}, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            finance, validation = result["portfolio"], result["validation"]
            print(f"{packet['trade_date']} 歷史demo；委託 {len(finance['orders'])} 筆、續抱 {len(finance['no_trade_tickers'])} 檔。")
            print(f"前收預估買進 {finance['buy_notional_twd']} 元、賣出 {finance['sell_notional_twd']} 元；"
                  f"手續費 {finance['fees_twd']} 元、稅 {finance['tax_twd']} 元。")
            print(f"預估現金 {finance['cash_after_twd']} 元、NAV {finance['projected_nav_twd']} 元。")
            print(f"官方結構：{'PASS' if validation['schema_ok'] else 'BLOCK'}；"
                  f"本地語意：{'PASS' if validation['semantic_ok'] else 'BLOCK'}；submission_ready=false。")
            for issue in validation.get("issues", []):
                if issue.get("severity") == "BLOCK":
                    print(f"BLOCK {issue.get('code', '')} {issue.get('message', '')}")
            print(f"候選／demo計畫：{outputs['plan_json']}")
            print(f"可讀決策說明：{outputs['plan_markdown']}")
            print(f"驗證與版本：{outputs['validation_json']}；{outputs['manifest_json']}")
            print(f"四個 agent 的計畫階段共用索引：{outputs['workspace_json']}")
            print("未計算實際成交或績效，帳戶股數與現金沒有入帳更新。")
        return 0 if result["validation"]["local_validation_ok"] else 4
    if args.command == "prepare-decision":
        try:
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            if args.workspace_root is not None:
                from etf_agent.pipeline import prepare_cached
                outputs = prepare_cached(account_path=args.account, ranking_metadata_path=args.ranking_metadata,
                                         as_of=args.as_of, trade_date=args.trade_date,
                                         shared_run_root=args.workspace_root, universe=universe)
                packet = json.loads(Path(outputs["packet_json"]).read_text(encoding="utf-8"))
            else:
                packet = prepare_decision(args.account, args.ranking_metadata, as_of=args.as_of,
                                          trade_date=args.trade_date, universe=universe)
                outputs = write_decision_packet(packet, args.output,
                                                project_root=Path(__file__).resolve().parents[2])
        except (AccountError, DataAgentError, EvidenceError, ReviewReportError, UniverseError, OSError, ValueError) as exc:
            print(f"決策資料準備錯誤：{exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"packet": packet, "outputs": outputs}, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            data = packet["data_report"]
            print(f"決策日 {packet['trade_date']}；市場資料截止 {packet['as_of']}；離線 historical demo。")
            print(f"data_agent：{len(data['rankings'])} 檔排名；{len(packet['allowed_tickers'])} 檔 demo 候選；"
                  f"完整保留 {len(packet['held_tickers'])} 檔原持股；{len(data['excluded_stocks'])} 檔排除沿用原紀錄。")
            print(f"test_agent：{packet['review_report']['status']}；尚無前日交易績效，建議為空。")
            print(f"account_agent：現金 {packet['account_report']['cash_twd']} 元；"
                  f"估算可用資金 {packet['account_report']['estimated_available_cash_twd']} 元；完整股數已保存。")
            print(f"NAV {data['account_valuation']['input_nav_twd']} 元；差異 {data['account_valuation']['nav_difference_twd']} 元。")
            print(f"內部來源系列 {len(packet['sources'])} 組；觀察 {len(packet['observations'])} 筆；"
                  "執行 compile-plan 時會裁取引用並檢查官方上限。")
            print(f"demo 決策輸入：{'可用' if packet['demo_decision_ready'] else '未通過'}；尚未呼叫模型或產生 D-Plan。")
            print(f"凍結資料包：{outputs['packet_json']}")
            print(f"版本與 hash：{outputs['manifest_json']}")
            print(f"四個 agent 的共用索引：{outputs['workspace_json']}")
            print("說明：docs/decision_workflow.md；formal_eligible=false、submission_ready=false。")
        return 0 if packet["demo_decision_ready"] else 2
    if args.command == "account-check":
        try:
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            report = analyze_account(args.account, args.ranking_metadata, as_of=args.as_of, universe=universe)
            outputs = write_account_report(report, args.output)
        except (AccountError, UniverseError, OSError) as exc:
            print(f"帳戶匯入／歷史估值錯誤：{exc}", file=sys.stderr)
            return 2
        success = report["valuation_ok"] and report["initial_constraints"]["passed"]
        if args.json:
            print(json.dumps({"report": report, "outputs": outputs}, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print(f"截至 {report['as_of']}：完整保留 {report['holdings_count']} 檔原持股；帳戶狀態 {report['account_status']}。")
            print(f"現金 {report['cash_twd']} 元；股票總市值 {report['stock_value_twd'] or '未知'} 元；"
                  f"已估值小計 {report['known_stock_value_twd']} 元。")
            print(f"輸入 NAV {report['input_nav_twd']} 元；計算 NAV {report['calculated_nav_twd'] or '未知'} 元；"
                  f"差異 {report['nav_difference_twd'] if report['nav_difference_twd'] is not None else '未知'} 元。")
            print(f"算術核對：{'PASS' if report['valuation_ok'] else '未通過'}；"
                  f"基本期初組合檢查：{'PASS' if report['initial_constraints']['passed'] else '未通過'}。")
            for issue in report["issues"]:
                if issue["severity"] == "BLOCK":
                    print(f"BLOCK {issue.get('ticker') or ''} {issue['message']}")
            warnings = sum(issue["severity"] == "WARN" for issue in report["issues"])
            print(f"資料限制 {warnings} 項；完整原因保存於 JSON。")
            print(f"獨立帳戶 JSON：{outputs['account_json']}")
            print(f"逐股市值 CSV：{outputs['positions_csv']}")
            print(f"核對報告 JSON：{outputs['report_json']}")
            print("使用說明：docs/account.md；僅歷史估值，未確認官方庫存，submission_ready=false。")
        return 0 if success else 2
    if args.command == "history-rankings":
        try:
            report = analyze_history_rankings(args.feature_metadata, profile_path=args.profile)
            outputs = write_ranking_analysis(report, args.output)
        except (RankingError, OSError) as exc:
            print(f"歷史因子排名錯誤：{exc}", file=sys.stderr)
            return 2
        print(f"截至 {report['as_of']}：排名 {len(report['rows'])} 檔；"
              f"沿用既有不足視窗紀錄 {len(report['excluded_stocks'])} 檔。")
        print(f"因子設定：{report['profile']['factor_profile']}；排名版本：{report['ranking_version']}")
        print(f"排名 CSV：{outputs['rankings_csv']}")
        print(f"設定、各因子貢獻與來源 JSON：{outputs['metadata_json']}")
        print("使用說明：docs/ranking.md")
        print("排名為歷史原價分析；正式交易資格未核實，formal_eligible=false，submission_ready=false。")
        return 0
    if args.command == "history-features":
        try:
            report = analyze_history_features(args.window_report)
            outputs = write_feature_analysis(report, args.output)
        except (FeatureAnalysisError, OSError) as exc:
            print(f"歷史因子分析錯誤：{exc}", file=sys.stderr)
            return 2
        print(f"截至 {report['as_of']}：分析 {len(report['rows'])} 檔；"
              f"沿用既有不足視窗紀錄 {len(report['excluded_stocks'])} 檔。")
        print("因子：20 日動能、20 日均線偏離、20 日年化波動；CSV 用百分數顯示。")
        print(f"分析 CSV：{outputs['features_csv']}")
        print(f"公式與來源 JSON：{outputs['metadata_json']}")
        print("使用說明：docs/factor_analysis.md")
        print("本批為歷史未調整原價分析；公司行動／歷史公開時間未核實，submission_ready=false。")
        return 0
    if args.command == "calendar-download":
        try:
            result = download_calendar(args.month, args.output, transport=args.transport)
        except (CalendarError, OSError) as exc:
            print(f"交易日曆取得錯誤：{exc}", file=sys.stderr)
            return 2
        for market, info in result["calendar"]["markets"].items():
            print(f"{market} {args.month}：官方排程 {len(info['trade_dates'])} 個交易日")
        print(f"日曆 JSON：{result['calendar_path']}")
        print(f"日曆 CSV：{result['calendar_csv']}")
        print("日曆依官方排程；臨時休市未完全核實，actual_sessions_verified=false。")
        return 0
    if args.command == "history-window-check":
        try:
            calendar = load_calendar(args.calendar)
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            report = check_history_windows(args.manifest, as_of=args.as_of, calendar=calendar, universe=universe)
            outputs = write_window_report(report, args.output)
        except (CalendarError, UniverseError, HistoryWindowError, OSError) as exc:
            print(f"價格視窗檢查錯誤：{exc}", file=sys.stderr)
            return 2
        summary = report["summary"]
        print(f"截至 {args.as_of}：完整 {summary['complete_stock_count']}／{summary['stock_count']} 檔；"
              f"不足 {summary['incomplete_stock_count']} 檔，每股需要 {report['required_bars']} 筆。")
        for stock in report["stocks"]:
            if not stock["window_complete"]:
                print(f"{stock['market']} {stock['ticker']}：有效價格 {stock['valid_price_count']} 筆；{stock['status']}")
        print(f"逐股 CSV：{outputs['report_csv']}")
        print(f"報告 JSON：{outputs['report_json']}")
        print("使用說明：docs/calendar_windows.md")
        print("窗口齊全只表示歷史價格資料完整；公司行動／公開時間／正式交易仍未核實，submission_ready=false。")
        return 0 if report["input_valid"] else 2
    if args.command == "history-universe":
        def show_progress(completed, total, entry):
            status = "快取" if entry.get("cache_hit") else "下載"
            outcome = f"{entry['row_count']} 列" if entry["status"] == "success" else entry["error"]
            print(f"[{completed}/{total}] {entry['market']} {entry['ticker']} {status}：{outcome}", flush=True)
        try:
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            result = download_history_universe(args.month, args.output, universe=universe,
                        cache_manifest=args.cache_manifest, transport=args.transport, progress=show_progress)
        except (UniverseError, HistoryDataError, OSError) as exc:
            print(f"全股票歷史下載錯誤：{exc}", file=sys.stderr)
            return 2
        count = sum(entry["status"] == "success" for entry in result["sources"])
        print(f"月份 {args.month}：成功 {count}/150，失敗 {150-count}；共 {result['row_count']} 列")
        print(f"HTTP 請求 {result['network_requests']} 次；快取命中 {result['cache_hits']} 次")
        print(f"每日表：{result['daily_dir']}；{len(result['daily_prices'])} 個日檔")
        print(f"每股月表：{result['monthly_dir']}")
        print(f"來源與逐股狀態：{result['manifest']}")
        print(f"逐日覆蓋與缺件：{result['coverage_report']}")
        print("來源回傳日的股票覆蓋完整=" + str(result["coverage_complete"]).lower()
              + "；日曆／公司行動／歷史已知時間未核實，submission_ready=false")
        return 0 if result["success"] else 2
    if args.command == "prices-check":
        try:
            universe = load_universe(args.universe, manifest_path=args.universe_manifest)
            report = check_daily_prices(args.prices, trade_date=args.date, universe=universe)
            outputs = write_coverage_report(report, args.output)
        except (UniverseError, PriceCoverageError, OSError) as exc:
            print(f"每日行情核對錯誤：{exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"report": report, "outputs": outputs}, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print(f"每日行情覆蓋報告：{report['trade_date']}（完全離線）")
            print(f"已取得：{report['present_count']}／{report['expected_count']} 檔（{report['coverage_percent']}%）；"
                  f"缺少：{report['missing_count']} 檔；有效價格：{report['valid_price_count']} 檔")
            for market, counts in report["by_market"].items():
                print(f"{market}：{counts['present_count']}／{counts['expected_count']} 檔；缺 {counts['missing_count']} 檔")
            print(f"輸入格式：{'PASS' if report['input_valid'] else 'FAIL'}；完整覆蓋={str(report['coverage_complete']).lower()}")
            print(f"原列 tradable=true：{report['tradable_flag_count']} 檔；submission_ready=false")
            print(f"錯誤：{len(report['errors'])} 項；限制：{len(report['warnings'])} 類")
            print("使用說明：docs/history_data.md")
            print(f"完整 JSON：{outputs['report_json']}")
            print(f"缺股票 CSV：{outputs['missing_csv']}")
        return 0 if report["input_valid"] else 2
    if args.command == "universe-check":
        try:
            universe = load_universe(args.universe, manifest_path=args.manifest)
            examples = [universe.lookup(ticker) for ticker in ("2330", "5274")]
        except UniverseError as exc:
            print(f"白名單錯誤：{exc}", file=sys.stderr)
            return 2
        summary = {
            "scope": "official_whitelist", "universe_version": universe.universe_version,
            "row_count": len(universe.stocks),
            "counts": {market: len(universe.select_market(market)) for market in ("TWSE", "TPEX")},
            "source_path": str(universe.source_path), "source_sha256": universe.source_sha256,
            "csv_sha256": universe.csv_sha256,
            "examples": [{"ticker": stock.ticker, "name": stock.name, "market": stock.market} for stock in examples],
            "historical_universe_verified": False,
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print("官方 F05 v1 股票白名單：格式、檔數與來源雜湊核對 PASS（完全離線）")
            print(f"版本：{universe.universe_version}")
            print(f"股票：{summary['row_count']} 檔；TWSE 100／TPEX 50；代號無重複")
            for stock in examples:
                print(f"抽查：{stock.ticker} {stock.name}／{stock.market}")
            print(f"來源：{universe.source_path}")
            print("此為競賽股票範圍；行情覆蓋與歷史時點股票池另行驗證。")
        return 0
    if args.command in ("history-sample", "history-export"):
        offline = args.command == "history-export"
        try:
            if offline:
                result = export_history_sample(args.manifest, args.output)
            else:
                result = download_history_sample(args.month, args.output, transport=args.transport)
        except (HistoryDataError, OSError, json.JSONDecodeError) as exc:
            print(f"歷史{'重新匯出' if offline else '樣本'}錯誤：{exc}", file=sys.stderr)
            return 2
        _show_history_summary(result, offline=offline)
        return 0 if result["success"] else 2
    try:
        summary = demo_summary(load_demo(args.fixture))
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(f"合約/資料錯誤：{exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        _show_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
