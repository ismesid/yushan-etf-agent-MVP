"""獨立帳戶匯入與歷史原價估值；不抓行情、不交易、不確認官方庫存。"""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

from etf_agent.contracts import AccountSnapshot, ContractError
from etf_agent.universe import Universe


POSITION_CSV_COLUMNS = (
    "ticker", "name", "market", "shares", "close_twd_per_share", "market_value_twd",
    "weight_of_input_nav", "valuation_status", "source_key", "data_version",
)
DECIMAL_PRECISION = 50


class AccountError(ValueError):
    """帳戶或歷史估值輸入無法讀取；不得自動補值或更改帳戶。"""


def _date(value: date | str) -> str:
    if type(value) is date:
        return value.isoformat()
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise AccountError("估值日期須為有效 YYYY-MM-DD") from exc
    return value


def _read_json(path: Path) -> tuple[dict, bytes]:
    try:
        body = path.read_bytes()
        value = json.loads(body.decode("utf-8-sig"))
        if type(value) is not dict:
            raise AccountError(f"{path.name} 須為 JSON object")
        return value, body
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AccountError(f"JSON 讀取失敗：{path}: {exc}") from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _load_account(path: Path) -> tuple[AccountSnapshot, bytes]:
    value, body = _read_json(path)
    try:
        return AccountSnapshot.from_dict(value), body
    except ContractError as exc:
        raise AccountError(f"帳戶合約錯誤：{exc}") from exc


def load_account_json(path: Path | str) -> AccountSnapshot:
    """只接受單一 AccountSnapshot 1.0；保留股數、NAV 與 demo／核對身分。"""
    return _load_account(Path(path).resolve())[0]


def load_history_closes(ranking_metadata_path: Path | str, *, as_of: date | str,
                        universe: Universe) -> dict:
    """Use the common read-only market reader, preserving the account error interface."""
    from etf_agent.prices import PriceContextError, load_history_closes as read_closes
    try:
        return read_closes(ranking_metadata_path, as_of=as_of, universe=universe)
    except PriceContextError as exc:
        raise AccountError(str(exc)) from exc


def _close(value) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, (str, Decimal)):
        raise AccountError("估值價格須為 Decimal 或十進位字串")
    try:
        result = Decimal(value)
        if not result.is_finite() or result <= 0:
            raise InvalidOperation
        return result
    except InvalidOperation as exc:
        raise AccountError("估值價格須為有限正值") from exc


def value_account(account: AccountSnapshot, price_context: dict) -> dict:
    """純計算：所有原持股保留，缺價時完整總值未知，絕不覆寫輸入 NAV。"""
    cutoff = _date(price_context["as_of"])
    stocks, quotes = price_context["stocks"], price_context["quotes"]
    issues = [dict(item) for item in price_context.get("issues", [])]

    def issue(code, message, ticker=None, severity="BLOCK"):
        issues.append({"code": code, "severity": severity, "ticker": ticker, "message": message})

    date_matches = account.as_of_trade_date.isoformat() == cutoff
    if not date_matches:
        issue("account_date_mismatch", f"帳戶日期 {account.as_of_trade_date} 與估值日 {cutoff} 不一致")
    with localcontext() as context:
        context.prec, context.rounding = DECIMAL_PRECISION, ROUND_HALF_EVEN
        positions, known_value, cap_results = [], Decimal(0), []
        for position in account.positions:
            stock, quote = stocks.get(position.ticker), quotes.get(position.ticker)
            if stock is None:
                issue("position_outside_universe", "原持股不在 F05；保留股數等待處理", position.ticker)
            price = None
            if date_matches and stock is not None and quote is not None:
                if quote.get("trade_date", cutoff) != cutoff or quote.get("market") != stock["market"]:
                    issue("position_price_identity", "持股行情日期或市場不一致", position.ticker)
                elif quote.get("price_valid") is True:
                    price = _close(quote.get("close_twd_per_share"))
            if price is None:
                issue("position_close_missing", "原持股缺少同日有效收盤；市值未知，股數保留", position.ticker)
            market_value = position.shares * price if price is not None else None
            weight = market_value / account.nav_twd if market_value is not None else None
            cap = Decimal("0.25") if position.ticker == "2330" else Decimal("0.10")
            cap_results.append(weight is not None and weight <= cap)
            if weight is not None and weight > cap:
                issue("position_weight_cap", f"持股權重超過 {cap}（以輸入 NAV 為分母）", position.ticker)
            if market_value is not None:
                known_value += market_value
            if quote is not None and price is not None:
                for key, code, message in (
                    ("known_at", "known_at_unverified", "歷史公開可知時間未核實"),
                    ("tradable", "tradability_unverified", "原行情未確認正式可交易資格"),
                ):
                    if not quote.get(key):
                        issue(code, message, position.ticker, "WARN")
                if quote.get("adjustment_status") == "unresolved":
                    issue("corporate_actions_unverified", "公司行動未核實", position.ticker, "WARN")
            positions.append({
                "ticker": position.ticker, "name": stock["name"] if stock else None,
                "market": stock["market"] if stock else None, "shares": position.shares,
                "close_twd_per_share": str(price) if price is not None else None,
                "market_value_twd": str(market_value) if market_value is not None else None,
                "weight_of_input_nav": str(weight) if weight is not None else None,
                "valuation_status": "valued" if price is not None else "unknown",
                **{key: quote.get(key) if quote else None for key in
                   ("source_key", "data_version", "known_at", "fetched_at", "raw_sha256", "requested_url")},
            })
        complete = date_matches and all(row["market_value_twd"] is not None for row in positions)
        calculated_nav = account.cash_twd + known_value if complete else None
        difference = calculated_nav - account.nav_twd if calculated_nav is not None else None
        nav_matches = difference == 0 if difference is not None else None
        if nav_matches is False:
            issue("nav_mismatch", f"計算 NAV 減輸入 NAV 差異為 {difference} 元；輸入保持原值")
        cash_ratio = account.cash_twd / calculated_nav if calculated_nav is not None and calculated_nav > 0 else None
        checks = {
            "holdings_count_passed": 20 <= len(positions) <= 30,
            "whitelist_passed": all(position.ticker in stocks for position in account.positions),
            "stock_caps_passed": all(cap_results) if complete else None,
            "cash_range_passed": Decimal(0) <= cash_ratio <= Decimal("0.25") if cash_ratio is not None else None,
        }
        if not checks["holdings_count_passed"]:
            issue("holdings_count", "期初示例持股檔數須在 20～30 檔")
        if checks["cash_range_passed"] is False:
            issue("cash_range", "期初示例現金占計算 NAV 的比例不在 0～25%")
        checks["passed"] = all(value is True for value in checks.values())
        # 基本期初組合檢查與算術核對各自呈現；小範例仍可算出正確 NAV。
        valuation_blockers = {"account_date_mismatch", "position_outside_universe", "position_price_identity",
                              "position_close_missing", "nav_mismatch"}
        data_blockers = any(item.get("severity") == "BLOCK" for item in price_context.get("issues", []))
        valuation_ok = complete and nav_matches is True and not data_blockers and not any(
            item["code"] in valuation_blockers for item in issues)
        return {
            "report_format_version": "1.0", "scope": "historical_account_valuation", "as_of": cutoff,
            "account_snapshot": account.to_dict(), "account_status": account.status,
            "demo": account.demo, "reconciled": account.reconciled, "holdings_count": len(positions),
            "positions": positions, "cash_twd": str(account.cash_twd), "input_nav_twd": str(account.nav_twd),
            "known_stock_value_twd": str(known_value),
            "stock_value_twd": str(known_value) if complete else None,
            "calculated_nav_twd": str(calculated_nav) if calculated_nav is not None else None,
            "nav_difference_twd": str(difference) if difference is not None else None,
            "cash_ratio": str(cash_ratio) if cash_ratio is not None else None,
            "date_matches": date_matches, "valuation_complete": complete, "nav_matches": nav_matches,
            "valuation_ok": valuation_ok, "initial_constraints": checks, "issues": issues,
            "units": {"shares": "shares", "close": "TWD/share", "money": "TWD", "weight": "ratio"},
            "calculation": {"decimal_precision": DECIMAL_PRECISION, "rounding": "ROUND_HALF_EVEN",
                            "nav_difference": "calculated_nav_twd - input_nav_twd", "nav_tolerance_twd": "0"},
            "rule_basis": {"source": "F07 v4.2", "holdings_range": [20, 30],
                           "stock_cap": "0.10", "stock_2330_cap": "0.25", "cash_range": ["0", "0.25"],
                           "scope": "basic_initial_portfolio_only"},
            "inputs": price_context.get("inputs", {}), "universe_version": price_context.get("universe_version"),
            "submission_ready": False,
            "limitations": ["歷史收盤估值與 NAV 等式不等於主辦方結算核對，不改帳戶 reconciled。",
                            "期初組合只檢查白名單、檔數、單股及現金；不是完整交易／D-Plan 合規。",
                            "不核實歷史公開版本、公司行動或正式期初帳戶；不產生正式 MarketSnapshot。",
                            "未計算當日交易、費用或效益；未下載或讀入決策日行情。"],
        }


def analyze_account(account_path: Path | str, ranking_metadata_path: Path | str,
                    *, as_of: date | str, universe: Universe) -> dict:
    """讀檔邊界組合既有歷史來源與純估值，保留輸入內容版本。"""
    path = Path(account_path).resolve()
    account, body = _load_account(path)
    prices = load_history_closes(ranking_metadata_path, as_of=as_of, universe=universe)
    report = value_account(account, prices)
    report["input_account"] = {"path": str(path), "sha256": _sha256(body)}
    identity = {"definition_version": "historical-account-valuation-v1", "as_of": report["as_of"],
                "account_sha256": _sha256(body), "inputs": prices["inputs"],
                "calculation": report["calculation"], "rule_basis": report["rule_basis"]}
    digest = _sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    report["valuation_version"] = "account-valuation-v1-" + digest[:12]
    return report


def build_weak_demo_account(ranking_metadata_path: Path | str, *, universe: Universe,
                            as_of: date | str = "2025-09-30") -> dict:
    """Build an artificial one-billion account from the lowest 25 factor ranks.

    Weak means lower September combined-factor rank only. This is an initial
    demonstration account, not a model decision or evidence of future returns.
    """
    cutoff = _date(as_of)
    if cutoff != "2025-09-30":
        raise AccountError("弱期初 demo 僅使用 2025-09-30；禁止讀入 10/1 行情")
    ranking_path = Path(ranking_metadata_path).resolve()
    ranking, ranking_body = _read_json(ranking_path)
    prices = load_history_closes(ranking_path, as_of=cutoff, universe=universe)
    if prices["inputs"]["ranking_metadata"]["sha256"] != _sha256(ranking_body):
        raise AccountError("排名在帳戶建構期間已變更")
    rows = ranking.get("rows")
    if not isinstance(rows, list) or len(rows) < 25:
        raise AccountError("弱期初 demo 需要至少 25 檔已完成排名")
    seen = set()
    for index, row in enumerate(rows, 1):
        if (type(row) is not dict or type(row.get("rank")) is not int or row["rank"] != index
                or row.get("ticker") not in prices["stocks"] or row["ticker"] in seen
                or row.get("market") != prices["stocks"][row["ticker"]]["market"]
                or row.get("analysis_included") is not True or row.get("formal_eligible") is not False):
            raise AccountError("排名須按連續名次排列、股票唯一且身分與 F05 相符")
        seen.add(row["ticker"])
    selected = rows[-25:]
    nav, budget = Decimal("1000000000.00"), Decimal("36000000.00")
    selection_rows, positions = [], []
    with localcontext() as context:
        context.prec, context.rounding = DECIMAL_PRECISION, ROUND_HALF_EVEN
        stock_value = Decimal(0)
        for row in selected:
            ticker = row["ticker"]
            quote = prices["quotes"].get(ticker)
            if quote is None or quote.get("price_valid") is not True:
                raise AccountError(f"末 25 檔的 {ticker} 缺有效 9/30 收盤；不換股或補值")
            close = _close(quote.get("close_twd_per_share"))
            if close is None:
                raise AccountError(f"末 25 檔的 {ticker} 缺收盤")
            try:
                values = row["values"]
                if type(values) is not dict or set(values) != {"mom20", "trend20", "vol20"}:
                    raise ValueError
                factor_values = {key: Decimal(value) for key, value in values.items()
                                 if type(value) is str}
                score = Decimal(row["score"]) if type(row.get("score")) is str else None
                if (set(factor_values) != set(values) or any(not value.is_finite() for value in factor_values.values())
                        or factor_values["vol20"] < 0 or score is None or not score.is_finite() or not 0 <= score <= 1):
                    raise ValueError
            except (KeyError, ValueError, InvalidOperation) as exc:
                raise AccountError(f"{ticker} 的排名或因子值無效") from exc
            exact_lots = Fraction(budget) / Fraction(close) / 1000
            shares = (exact_lots.numerator // exact_lots.denominator) * 1000
            if shares <= 0:
                raise AccountError(f"{ticker} 預算不足一張；不能更換末 25 檔或生成零持股")
            market_value = shares * close
            stock_value += market_value
            positions.append({"ticker": ticker, "shares": shares})
            selection_rows.append({
                "ticker": ticker, "name": prices["stocks"][ticker]["name"], "market": row["market"],
                "rank": row["rank"], "score": str(score),
                **{key: str(value) for key, value in factor_values.items()},
                "budget_twd": str(budget), "shares": shares, "close_twd_per_share": str(close),
                "market_value_twd": str(market_value), "weight_of_input_nav": str(market_value / nav),
                "source_key": quote.get("source_key"), "data_version": quote.get("data_version"),
            })
        account = AccountSnapshot.from_dict({
            "contract_version": "1.0", "snapshot_id": "DEMO_WEAK_20250930_NAV1B_" + _sha256(ranking_body)[:12],
            "as_of_trade_date": cutoff, "status": "demo", "cash_twd": str(nav - stock_value),
            "nav_twd": str(nav), "positions": positions, "origin": "synthetic_weak_historical_initial_account",
            "reconciled": False, "demo": True, "origin_ref": None,
        })
    valuation = value_account(account, prices)
    if not valuation["valuation_ok"] or not valuation["initial_constraints"]["passed"]:
        raise AccountError("弱期初 demo 未通過完整估值或基本組合限制，不輸出成功帳戶")
    construction = {
        "construction_version": "1.0", "scope": "synthetic_weak_initial_account", "as_of": cutoff,
        "selection_method": "lowest_25_combined_factor_ranks", "selected_stock_count": 25,
        "ranked_stock_count": len(rows), "selected_rank_range": [selected[0]["rank"], selected[-1]["rank"]],
        "nav_twd": str(nav), "per_stock_budget_twd": str(budget), "construction_stock_budget_ratio": "0.90",
        "shares_formula": "floor(36000000 / September_30_close_twd_per_share / 1000) * 1000",
        "cash_formula": "1000000000 - sum(shares * September_30_close_twd_per_share)",
        "ranking_version": ranking.get("ranking_version"), "ranking_profile": deepcopy(ranking.get("profile")),
        "input_ranking_metadata": {"path": str(ranking_path), "sha256": _sha256(ranking_body)},
        "inputs": deepcopy(prices["inputs"]), "demo": True, "reconciled": False, "submission_ready": False,
        "limitations": ["弱僅指九月三因子加權排名末段，不表示10/1必然下跌或模型必須賣出。",
                        "90%及每股同預算僅建構人工期初帳戶，不修改因子權重或投資策略。",
                        "不重查四檔已知因子缺失，不補值、不讀決策日行情、不呼叫模型。"],
    }
    return {"account_snapshot": account.to_dict(), "valuation": valuation,
            "construction": construction, "selection_rows": selection_rows}


def write_weak_demo_account(report: dict, output_dir: Path | str) -> dict:
    """Save the weak demo plus construction evidence; do not overwrite a fixture."""
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / _date(report["construction"]["as_of"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    account_json, positions_csv, construction_json, valuation_json = (
        run_dir / name for name in ("account_snapshot.json", "initial_positions.csv", "construction.json", "valuation.json"))
    for path, value in ((account_json, report["account_snapshot"]), (valuation_json, report["valuation"])):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8", newline="\n")
    columns = ("ticker", "name", "market", "rank", "score", "mom20", "trend20", "vol20", "budget_twd",
               "shares", "close_twd_per_share", "market_value_twd", "weight_of_input_nav", "source_key", "data_version")
    with positions_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["selection_rows"])
    construction = {**report["construction"], "created_at": now.isoformat(), "run_id": run_id,
                    "artifact_sha256": {path.name: _sha256(path.read_bytes())
                                        for path in (account_json, positions_csv, valuation_json)}}
    construction_json.write_text(json.dumps(construction, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8", newline="\n")
    return {"run_dir": str(run_dir), "account_json": str(account_json), "positions_csv": str(positions_csv),
            "construction_json": str(construction_json), "valuation_json": str(valuation_json)}


def write_account_report(report: dict, output_dir: Path | str) -> dict:
    """每次新增 CSV／JSON 版本；缺價或差額報告亦可保存，不覆寫帳戶。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / _date(report["as_of"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    account_json, positions_csv, report_json = (run_dir / name for name in
                                               ("account_snapshot.json", "positions.csv", "valuation.json"))
    account_json.write_text(json.dumps(report["account_snapshot"], ensure_ascii=False, indent=2,
                                       allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    with positions_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=POSITION_CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in POSITION_CSV_COLUMNS} for row in report["positions"])
    stored = {**report, "created_at": now.isoformat(), "run_id": run_id,
              "artifacts": {"account_json": account_json.name, "positions_csv": positions_csv.name},
              "artifact_sha256": {"account_json": _sha256(account_json.read_bytes()),
                                  "positions_csv": _sha256(positions_csv.read_bytes())}}
    report_json.write_text(json.dumps(stored, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8", newline="\n")
    return {"run_dir": str(run_dir), "account_json": str(account_json),
            "positions_csv": str(positions_csv), "report_json": str(report_json)}
