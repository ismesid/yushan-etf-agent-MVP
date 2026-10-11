"""收盤後的獨立模擬；不修改原決策、期初帳或正式庫存。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

from etf_agent.contracts import AccountSnapshot


FEE = Decimal("0.001425")
SELL_TAX = Decimal("0.003")


class EvaluationError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if type(value) is not dict:
        raise EvaluationError(f"JSON 必須是 object：{path}")
    return value


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise EvaluationError("封存索引路徑超出所屬目錄")
    return path


def verify_frozen(workspace_path: Path | str) -> dict:
    """下載前檢查真實決策已驗收、日期、完整manifest以及期初NAV。"""
    workspace_path = Path(workspace_path).resolve()
    root = workspace_path.parent
    workspace = read_json(workspace_path)
    if not (workspace.get("accepted_demo_plan") is True and workspace.get("real_agent_decision") is True):
        raise EvaluationError("先封存並驗收真實模型 D-Plan，才能下載事後行情")
    files = {key: _inside(root, value) for key, value in workspace["files"].items()}
    hashes = {str(workspace_path): sha256(workspace_path)}
    for name in ("decision_manifest", "plan_manifest"):
        path = files[name]
        manifest = read_json(path)
        hashes[str(path)] = sha256(path)
        entries = manifest.get("artifact_sha256")
        if not entries:
            raise EvaluationError("封存manifest缺少產物hash")
        for relative, expected in entries.items():
            artifact = _inside(path.parent, relative)
            actual = sha256(artifact)
            if expected != actual:
                raise EvaluationError(f"封存hash不符：{artifact.name}")
            hashes[str(artifact)] = actual
        if name == "plan_manifest":
            if not (manifest.get("real_agent_decision") is True and manifest.get("local_validation_ok") is True):
                raise EvaluationError("計畫manifest沒有真實且已驗收決策")
            for relative, expected in manifest.get("code_archive", {}).get("files_sha256", {}).items():
                artifact = _inside(path.parent / "code", relative)
                if sha256(artifact) != expected:
                    raise EvaluationError(f"決策程式封存hash不符：{relative}")
                hashes[str(artifact)] = expected
    for name in ("account_snapshot", "decision_run", "agent_result", "raw_response", "model_execution"):
        hashes[str(files[name])] = sha256(files[name])
    packet = read_json(files["evidence_packet"])
    plan = read_json(files["dplan"])
    portfolio = read_json(files["portfolio"])
    validation = read_json(files["validation"])
    run = read_json(files["decision_run"])
    if not (validation.get("local_validation_ok") is True and run.get("accepted_demo_plan") is True):
        raise EvaluationError("決策未通過封存驗證")
    as_of, trade_date = packet["as_of"], packet["trade_date"]
    if not (date.fromisoformat(as_of) < date.fromisoformat(trade_date)
            and plan["trade_date"] == portfolio["trade_date"] == run["trade_date"] == trade_date):
        raise EvaluationError("封存計畫與輸入日期不符")
    if plan["orders"] != portfolio["orders"]:
        raise EvaluationError("D-Plan 與配置委託不一致")
    account = AccountSnapshot.from_dict(packet["account_snapshot"])
    if account.to_dict() != read_json(files["account_snapshot"]):
        raise EvaluationError("帳戶輸入與封存packet不同")
    if account.as_of_trade_date.isoformat() != as_of:
        raise EvaluationError("期初帳戶日期不符")
    previous = {row["ticker"]: row["close_twd_per_share"] for row in packet["data_report"]["rankings"]}
    with localcontext() as context:
        context.prec = 50
        if any(previous.get(p.ticker) is None for p in account.positions):
            raise EvaluationError("期初持股缺前收，不能驗證期初NAV")
        nav = account.cash_twd + sum((p.shares * Decimal(previous[p.ticker]) for p in account.positions), Decimal(0))
        if nav != account.nav_twd:
            raise EvaluationError("期初NAV與前收持股市值不符")
    return {"workspace_path": str(workspace_path), "root": str(root), "files": files,
            "packet": packet, "plan": plan, "account": account.to_dict(), "previous_closes": previous,
            "frozen_sha256": hashes, "as_of": as_of, "trade_date": trade_date}


def verify_unchanged(hashes: dict[str, str]) -> None:
    for name, expected in hashes.items():
        if sha256(Path(name)) != expected:
            raise EvaluationError(f"評估期間原決策遭修改：{name}")


def validate_quotes(quotes: dict, trade_date: str) -> None:
    for ticker, row in quotes.items():
        if row.get("trade_date") != trade_date or row.get("ticker") != ticker:
            raise EvaluationError("行情日期或股票代碼不符，拒絕混入其他交易日")
        for name in ("close_twd_per_share", "vwap_twd_per_share", "amount_twd"):
            if row.get(name) is not None:
                value = Decimal(str(row[name]))
                if not value.is_finite() or value <= 0:
                    raise EvaluationError(f"{ticker} {name} 非有限正值")
        volume = row.get("volume_shares")
        if volume is not None and (type(volume) is not int or volume <= 0):
            raise EvaluationError("成交股數必須為正整數或未知")
        with localcontext() as context:
            context.prec = 50
            expected = (Decimal(row["amount_twd"]) / volume
                        if row.get("amount_twd") is not None and volume is not None else None)
            supplied = Decimal(row["vwap_twd_per_share"]) if row.get("vwap_twd_per_share") is not None else None
            if expected != supplied:
                raise EvaluationError(f"{ticker} 日均價與官方成交量值不符")


def simulate(account_raw: dict, orders: list[dict], quotes: dict, *, trade_date: str,
             previous_closes: dict, scenario: str) -> dict:
    """固定委託股數，以T日日均價模擬；缺成交不執行、缺估價NAV留null。"""
    validate_quotes(quotes, trade_date)
    account = AccountSnapshot.from_dict(account_raw)
    if account.as_of_trade_date >= date.fromisoformat(trade_date):
        raise EvaluationError("評估日必須晚於期初帳戶日，不能重複入帳")
    shares = {p.ticker: p.shares for p in account.positions}
    initial = dict(shares)
    seen, fills, issues = set(), [], []
    with localcontext() as context:
        context.prec = 50
        cash, fees, tax = account.cash_twd, Decimal(0), Decimal(0)
        for order in orders:
            ticker, side, quantity = order["ticker"], order["side"], order["shares"]
            if (ticker in seen or side not in ("BUY", "SELL") or type(quantity) is not int
                    or quantity <= 0 or quantity % 1000):
                raise EvaluationError("委託重複／同股當沖、方向或整張股數錯誤")
            seen.add(ticker)
            if side == "SELL" and quantity > shares.get(ticker, 0):
                raise EvaluationError(f"{ticker} 超賣期初持股")
            quote = quotes.get(ticker, {})
            price = quote.get("vwap_twd_per_share")
            fill = {"ticker": ticker, "side": side, "requested_shares": quantity,
                    "filled_shares": 0, "fill_status": "unfilled_missing_vwap",
                    "vwap_twd_per_share": price, "notional_twd": None, "fee_twd": None,
                    "tax_twd": None, "cash_delta_twd": None, "decision_ref": order.get("decision_ref"),
                    "benefit_vs_skip_twd": None}
            if price is None:
                issues.append({"code": "order_missing_vwap", "severity": "WARN", "ticker": ticker})
            else:
                notional = Decimal(price) * quantity
                fee, sale_tax = notional * FEE, notional * SELL_TAX if side == "SELL" else Decimal(0)
                delta = -notional - fee if side == "BUY" else notional - fee - sale_tax
                cash += delta
                fees += fee
                tax += sale_tax
                sign = 1 if side == "BUY" else -1
                shares[ticker] = shares.get(ticker, 0) + sign * quantity
                close = quote.get("close_twd_per_share")
                benefit = sign * quantity * (Decimal(close) - Decimal(price)) - fee - sale_tax if close else None
                fill.update(filled_shares=quantity, fill_status="simulated_filled", notional_twd=str(notional),
                            fee_twd=str(fee), tax_twd=str(sale_tax), cash_delta_twd=str(delta),
                            benefit_vs_skip_twd=str(benefit) if benefit is not None else None)
            fills.append(fill)
        known_stock, rows, missing = Decimal(0), [], []
        for ticker in sorted(set(initial) | set(shares)):
            quantity = shares.get(ticker, 0)
            close = quotes.get(ticker, {}).get("close_twd_per_share")
            value = Decimal(close) * quantity if close is not None else Decimal(0) if quantity == 0 else None
            if value is None:
                missing.append(ticker)
                issues.append({"code": "held_missing_close", "severity": "BLOCK", "ticker": ticker})
            else:
                known_stock += value
            prior = previous_closes.get(ticker)
            rows.append({"ticker": ticker, "initial_shares": initial.get(ticker, 0), "end_shares": quantity,
                         "previous_close_twd_per_share": prior, "close_twd_per_share": close,
                         "market_value_twd": str(value) if value is not None else None})
        nav = cash + known_stock if not missing else None
        if cash < 0:
            issues.append({"code": "negative_simulated_cash", "severity": "BLOCK", "ticker": None})
        summary = {"scenario": scenario, "trade_date": trade_date, "initial_nav_twd": str(account.nav_twd),
                   "cash_twd": str(cash), "known_stock_value_twd": str(known_stock),
                   "stock_value_twd": str(known_stock) if not missing else None,
                   "end_nav_twd": str(nav) if nav is not None else None,
                   "profit_twd": str(nav - account.nav_twd) if nav is not None else None,
                   "return_ratio": str(nav / account.nav_twd - 1) if nav is not None else None,
                   "fees_twd": str(fees), "tax_twd": str(tax),
                   "cash_ratio": str(cash / nav) if nav and nav > 0 else None,
                   "holdings_count": sum(q > 0 for q in shares.values()),
                   "requested_orders": len(orders), "filled_orders": sum(f["filled_shares"] > 0 for f in fills),
                   "missing_valuation_tickers": missing}
        checks = {"complete_valuation": not missing, "cash_nonnegative": cash >= 0,
                  "positive_nav": nav is not None and nav > 0,
                  "holdings_20_to_30": 20 <= summary["holdings_count"] <= 30,
                  "orders_at_most_30": len(orders) <= 30,
                  "cash_at_most_25pct": nav is not None and nav > 0 and cash <= nav * Decimal("0.25"),
                  "closing_weight_caps": nav is not None and nav > 0 and all(
                      r["market_value_twd"] is not None and Decimal(r["market_value_twd"]) <= nav *
                      (Decimal("0.25") if r["ticker"] == "2330" else Decimal("0.10")) for r in rows)}
        snapshot = None
        if checks["complete_valuation"] and checks["cash_nonnegative"] and checks["positive_nav"]:
            snapshot = {"contract_version": "1.0", "snapshot_id": f"SIM_{scenario}_{trade_date}_" +
                        hashlib.sha256(json.dumps(orders, sort_keys=True).encode()).hexdigest()[:12],
                        "as_of_trade_date": trade_date, "status": "simulated", "cash_twd": str(cash),
                        "nav_twd": str(nav), "positions": [{"ticker": t, "shares": q} for t, q in sorted(shares.items()) if q > 0],
                        "origin": "isolated_daily_vwap_simulation", "origin_ref": None,
                        "reconciled": False, "demo": True}
            AccountSnapshot.from_dict(snapshot)
        return {"summary": summary, "fills": fills, "positions": rows, "issues": issues,
                "checks": checks, "constraint_checks_ok": all(checks.values()), "account_snapshot": snapshot}


def hindsight_ranking(allowed: list[str], quotes: dict, previous_closes: dict) -> list[dict]:
    rows = []
    with localcontext() as context:
        context.prec = 50
        for ticker in allowed:
            quote = quotes.get(ticker, {})
            close, vwap, previous = (quote.get("close_twd_per_share"), quote.get("vwap_twd_per_share"),
                                     previous_closes.get(ticker))
            signal = Decimal(close) / (Decimal(vwap) * (1 + FEE)) - 1 if close and vwap else None
            rows.append({"ticker": ticker, "trade_date": quote.get("trade_date"), "rank": None,
                         "close_twd_per_share": close, "vwap_twd_per_share": vwap,
                         "close_vs_previous_return": str(Decimal(close) / Decimal(previous) - 1) if close and previous else None,
                         "buy_vwap_to_close_after_fee_return": str(signal) if signal is not None else None,
                         "data_complete": bool(close and vwap and previous)})
        rows.sort(key=lambda r: (r["buy_vwap_to_close_after_fee_return"] is None,
                                 -Decimal(r["buy_vwap_to_close_after_fee_return"] or 0), r["ticker"]))
        for rank, row in enumerate((r for r in rows if r["data_complete"]), 1):
            row["rank"] = rank
    return rows
