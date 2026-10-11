"""Report a complete account snapshot without booking trades or claiming credit."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib

from etf_agent.contracts import AccountSnapshot, ContractError
from .account import _load_account, value_account


class AccountAgentError(ValueError):
    """The supplied snapshot or requested date does not follow its contract."""


def prepare_account(account_path: Path | str, price_context: dict, *, as_of: str) -> dict:
    """Import and value an account using the shared cutoff-price context."""
    path = Path(account_path).resolve()
    account, body = _load_account(path)
    valuation = value_account(account, price_context)
    valuation["input_account"] = {"path": str(path), "sha256": hashlib.sha256(body).hexdigest()}
    snapshot = account.to_dict()
    return {"account_snapshot": snapshot, "account_valuation": valuation,
            "account_report": report_account(snapshot, valuation, as_of=as_of)}


def _amount(value) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        number = Decimal(value)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def report_account(account_snapshot: dict, valuation: dict, *, as_of: str) -> dict:
    """Expose all holdings and cash from AccountSnapshot 1.0; never alter them.

    Available cash is an estimate for demo snapshots only. Formal available
    funds, reservations, settlement and transaction accounting are not provided
    by this snapshot/report interface.
    """
    try:
        if type(as_of) is not str or date.fromisoformat(as_of).isoformat() != as_of:
            raise ValueError("as_of must be YYYY-MM-DD")
        account = AccountSnapshot.from_dict(account_snapshot)
    except (ContractError, TypeError, ValueError) as exc:
        raise AccountAgentError(str(exc)) from exc
    if type(valuation) is not dict:
        raise AccountAgentError("valuation must be an object")
    snapshot = account.to_dict()
    supplied_issues = valuation.get("issues", [])
    issues = deepcopy(supplied_issues) if isinstance(supplied_issues, list) else []

    def block(code, message, ticker=None):
        issues.append({"code": code, "severity": "BLOCK", "ticker": ticker,
                       "message": message})

    if not isinstance(supplied_issues, list) or any(type(item) is not dict for item in issues):
        issues = [item for item in issues if type(item) is dict]
        block("account_valuation_issues_invalid", "估值問題清單格式不符")
    date_matches = (snapshot["as_of_trade_date"] == as_of
                    and valuation.get("as_of") == as_of
                    and valuation.get("date_matches") is True)
    if not date_matches:
        block("account_report_date_mismatch", "帳戶、估值與要求日期不一致")
    identity_matches = valuation.get("account_snapshot") == snapshot
    if not identity_matches:
        block("account_report_identity_mismatch", "估值引用的帳戶內容與輸入快照不一致")
    money_matches = (_amount(valuation.get("cash_twd")) == account.cash_twd
                     and _amount(valuation.get("input_nav_twd")) == account.nav_twd
                     and _amount(valuation.get("calculated_nav_twd")) == account.nav_twd
                     and _amount(valuation.get("nav_difference_twd")) == Decimal(0)
                     and valuation.get("nav_matches") is True)
    if not money_matches:
        block("account_report_nav_mismatch", "估值現金、NAV 或差額尚未核對一致")

    indexed = {}
    rows = valuation.get("positions", [])
    if not isinstance(rows, list):
        rows = []
        block("account_report_positions_invalid", "估值持股清單格式不符")
    for row in rows:
        if type(row) is not dict or not isinstance(row.get("ticker"), str):
            block("account_report_positions_invalid", "估值持股缺少股票身分")
            continue
        ticker = row["ticker"]
        if ticker in indexed:
            block("account_report_position_duplicate", "估值持股重複", ticker)
        else:
            indexed[ticker] = row
    position_identity = set(indexed) == {position.ticker for position in account.positions}
    if not position_identity:
        block("account_report_positions_mismatch", "估值必須涵蓋相同的完整原持股")
    positions = []
    copied_fields = ("name", "market", "close_twd_per_share", "market_value_twd",
                     "weight_of_input_nav", "valuation_status", "source_key", "data_version")
    for position in account.positions:
        row = indexed.get(position.ticker)
        shares_match = (row is not None and type(row.get("shares")) is int
                        and row["shares"] == position.shares)
        if not shares_match:
            position_identity = False
            block("account_report_shares_mismatch", "估值股數不符；保留輸入帳戶股數", position.ticker)
        verified = row if shares_match and date_matches and identity_matches else {}
        output = {"ticker": position.ticker, "shares": position.shares,
                  **{key: deepcopy(verified.get(key)) for key in copied_fields}}
        if output["market_value_twd"] is None or output["close_twd_per_share"] is None:
            output["valuation_status"] = "unknown"
            block("account_report_position_value_missing", "原持股缺少可用估值，仍完整保留", position.ticker)
        positions.append(output)

    constraints_passed = (type(valuation.get("initial_constraints")) is dict
                          and valuation["initial_constraints"].get("passed") is True)
    account_valid = (valuation.get("valuation_ok") is True and constraints_passed
                     and date_matches and identity_matches and money_matches and position_identity
                     and not any(item.get("severity") == "BLOCK" for item in issues))
    if not constraints_passed:
        block("account_report_constraints_failed", "帳戶基本組合檢查尚未通過")
    if valuation.get("valuation_ok") is not True:
        block("account_report_valuation_failed", "帳戶估值尚未通過")

    return {
        "report_format_version": "1.0", "role": "account_agent", "as_of": as_of,
        "snapshot_id": account.snapshot_id, "status": account.status,
        "demo": account.demo, "reconciled": account.reconciled,
        "origin": account.origin, "origin_ref": account.origin_ref,
        "account_snapshot": snapshot, "account_valid": account_valid,
        "cash_twd": str(account.cash_twd), "nav_twd": str(account.nav_twd),
        "estimated_available_cash_twd": str(account.cash_twd) if account.demo else None,
        "available_cash_twd": None, "available_cash_status": "not_verified",
        "reservations_twd": "0", "reservation_status": "not_implemented",
        "current_positions": positions, "holdings_count": len(positions),
        "nav_difference_twd": valuation.get("nav_difference_twd"),
        "issues": issues, "inputs": {
            "account": deepcopy(valuation.get("input_account")),
            "valuation": deepcopy(valuation.get("inputs", {})),
            "valuation_version": valuation.get("valuation_version"),
        },
        "units": {"shares": "shares", "money": "TWD", "price": "TWD/share", "weight": "ratio"},
        "limitations": [
            "僅回報輸入快照與估值；不成交、不扣款、不更新帳戶。",
            "demo 可用現金估算假設保留額為零；尚未實作委託保留、交割與正式額度核對。",
            "不取得行情或模型決策；主 Agent 不得直接修改帳戶。",
        ], "submission_ready": False,
    }
