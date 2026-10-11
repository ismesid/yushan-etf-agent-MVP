"""離線合約示例、官方白名單核對及歷史樣本；正式完整流程尚待後續批次。"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from etf_agent.agent.base import AgentResult
from etf_agent.contracts import (
    AccountSnapshot, AgentDraft, ContractError, DatasetSplitPlan, FeatureTable,
    MarketSnapshot, PortfolioProposal, ValidationReport,
)
from etf_agent.coverage import PriceCoverageError, check_daily_prices, write_coverage_report
from etf_agent.history import download_history_sample, download_history_universe, export_history_sample
from etf_agent.providers.monthly import HistoryDataError
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
    parser = argparse.ArgumentParser(description="玉山 ETF MVP：資料合約示例、官方白名單與歷史樣本")
    commands = parser.add_subparsers(dest="command", required=True)
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
    args = parser.parse_args(argv)
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
            print(f"閱讀報告：{outputs['report_md']}")
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
