"""離線合約示例、官方歷史下載與快取重新匯出；正式完整流程尚待後續批次。"""

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
from etf_agent.history import download_history_sample, export_history_sample
from etf_agent.providers.monthly import HistoryDataError


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
    parser = argparse.ArgumentParser(description="玉山 ETF MVP：資料合約示例與官方歷史樣本")
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
    args = parser.parse_args(argv)
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
