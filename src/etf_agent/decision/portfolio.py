"""純計算的完整配置與前收估算；F07 v4.2 公式，不抓資料或改帳戶。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction

from etf_agent.contracts import AccountSnapshot, ContractError, WeightedAgentDraft


class PortfolioError(ValueError):
    """草稿、凍結上下文或行情缺件，無法計算完整配置。"""


def _decimal(value, label: str) -> Decimal:
    if not isinstance(value, (Decimal, str)):
        raise PortfolioError(f"{label} 須為 Decimal 或十進位字串")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise PortfolioError(f"{label} 不是有效十進位數值") from exc
    if not result.is_finite():
        raise PortfolioError(f"{label} 須為有限值")
    return result


def derive_target_shares(weight: Decimal, nav: Decimal, close: Decimal) -> int:
    """floor(weight × 前日NAV ÷ 前收 ÷ 1000) × 1000；精確處理整張邊界。"""
    if any(type(value) is not Decimal or not value.is_finite() for value in (weight, nav, close)):
        raise PortfolioError("股數公式只接受有限 Decimal")
    if not 0 <= weight <= 1 or nav <= 0 or close <= 0:
        raise PortfolioError("股數公式須有0～1權重、正NAV及正前收")
    lots = Fraction(weight) * Fraction(nav) / Fraction(close) / 1000
    return (lots.numerator // lots.denominator) * 1000


def build_portfolio(packet: dict, draft: WeightedAgentDraft) -> dict:
    """以凍結權重推股數；財務或意圖不符保存 BLOCK，不自動改權重或股數。"""
    if not isinstance(draft, WeightedAgentDraft):
        raise PortfolioError("只接受 WeightedAgentDraft 2.0")
    try:
        # 使用實際可封存的字串權重重新載入，再由相同公式推導。
        draft = WeightedAgentDraft.from_dict(draft.to_dict())
        account = AccountSnapshot.from_dict(packet["account_snapshot"])
        data = packet["data_report"]
        if data["account_snapshot"] != account.to_dict():
            raise PortfolioError("資料報告與凍結帳戶不一致")
        cutoff, decision_day = packet["as_of"], packet["trade_date"]
        cutoff_date, decision_date = date.fromisoformat(cutoff), date.fromisoformat(decision_day)
        if cutoff_date.isoformat() != cutoff or decision_date.isoformat() != decision_day:
            raise PortfolioError("資料或決策日期格式錯誤")
        rankings = {row["ticker"]: row for row in data["rankings"]}
        allowed = set(packet["allowed_tickers"])
        if allowed != set(data["allowed_tickers"]) or any(
                ticker not in rankings or rankings[ticker].get("demo_candidate") is not True for ticker in allowed):
            raise PortfolioError("候選池與資料報告的 demo 候選不一致")
        held = {position.ticker: position.shares for position in account.positions}
        observation_ids = {row["obs_id"] for row in packet["observations"]}
        draft.validate_context(allowed_tickers=allowed, held_tickers=held, observation_ids=observation_ids)
        if set(draft.market_proposal.basis_obs_ids) != {"O1"}:
            raise PortfolioError("市場提案須引用市場觀察 O1")
        per_stock_obs = packet["stock_observation_ids"]
        for item in (*draft.selections, *draft.held_reviews):
            if per_stock_obs.get(item.ticker) not in item.supporting_obs_ids:
                raise PortfolioError(f"{item.ticker} 的理由須包含本股觀察引用")
        price_rows = dict(rankings)
        for row in data["held_positions"]:
            ticker = row["ticker"]
            if ticker not in price_rows:
                price_rows[ticker] = row
            elif row["close_twd_per_share"] != price_rows[ticker]["close_twd_per_share"]:
                raise PortfolioError(f"{ticker} 原持股與排名價格不一致")
        selected = {row.ticker: row for row in draft.selections}
        prices = {}
        for ticker in set(held) | set(selected):
            if ticker not in price_rows or price_rows[ticker].get("close_twd_per_share") is None:
                raise PortfolioError(f"{ticker} 缺少同日有效前收；不能刪除原持股或補值")
            price = _decimal(price_rows[ticker]["close_twd_per_share"], f"{ticker} 前收")
            if price <= 0:
                raise PortfolioError(f"{ticker} 前收須為正值")
            prices[ticker] = price
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, PortfolioError):
            raise
        raise PortfolioError(f"凍結資料或草稿不完整：{exc}") from exc

    issues = []
    checks = {}

    def check(code: str, passed: bool, message: str, ticker=None):
        checks[code] = bool(passed)
        if not passed:
            issues.append({"code": code, "severity": "BLOCK", "ticker": ticker, "message": message})

    check("input_dates", account.as_of_trade_date == cutoff_date and data["as_of"] == cutoff
          and decision_date > cutoff_date, "帳戶／資料日須一致，決策日須晚於資料日")
    check("decision_input_ready", packet.get("demo_decision_ready") is True,
          "凍結資料尚未通過 demo 決策輸入檢查")
    with localcontext() as context:
        context.prec = 50
        original_value = sum((shares * prices[ticker] for ticker, shares in held.items()), Decimal(0))
        check("input_nav", account.cash_twd + original_value == account.nav_twd,
              "期初現金加全部原持股前收市值不等於輸入NAV")
        reviews = {row.ticker: row for row in draft.held_reviews}
        positions, decisions, orders, no_trade = [], [], [], []
        buy, sell = Decimal(0), Decimal(0)
        all_lots, keep_ok, positive_selected = True, True, True
        for ticker in sorted(set(held) | set(selected)):
            current = held.get(ticker, 0)
            weight = selected[ticker].target_weight if ticker in selected else Decimal(0)
            requested = derive_target_shares(weight, account.nav_twd, prices[ticker])
            target = requested
            review = reviews.get(ticker)
            if review is not None and review.intent == "keep":
                if requested != current:
                    keep_ok = False
                    issues.append({"code": "keep_target_mismatch", "severity": "BLOCK", "ticker": ticker,
                                   "message": "續抱要求保留原股數，但提議權重推導股數不同；須回Agent修訂"})
                target = current
            delta = target - current
            if current % 1000 or delta % 1000:
                all_lots = False
                issues.append({"code": "odd_lot", "severity": "BLOCK", "ticker": ticker,
                               "message": "原持股或委託不是整張；不能抹掉零股或手改股數"})
            if ticker in selected and target == 0:
                positive_selected = False
                issues.append({"code": "selected_zero_shares", "severity": "BLOCK", "ticker": ticker,
                               "message": "正目標權重推導成零股，須回Agent調整選股／權重"})
            positions.append({"ticker": ticker, "current_shares": current, "target_shares": target,
                              "requested_target_shares": requested, "close_twd_per_share": str(prices[ticker]),
                              "target_weight": str(weight)})
            if delta == 0:
                if current > 0:
                    no_trade.append(ticker)
                continue
            action = "BUY" if current == 0 else "SELL_ALL" if target == 0 else "ADD" if delta > 0 else "TRIM"
            decision_id = f"D{len(decisions) + 1}"
            decisions.append({"decision_id": decision_id, "ticker": ticker, "action": action,
                              "target_weight": str(weight)})
            side = "BUY" if delta > 0 else "SELL"
            orders.append({"ticker": ticker, "side": side, "shares": abs(delta), "decision_ref": decision_id})
            if delta > 0:
                buy += delta * prices[ticker]
            else:
                sell += -delta * prices[ticker]
        check("whole_lots", all_lots, "原持股及委託須符合已確認的整張規則")
        check("keep_intent", keep_ok, "續抱股數與Agent權重意圖不一致")
        check("selected_positive_shares", positive_selected, "選入股票不可在整張化後消失")
        check("no_overselling", all(order["shares"] <= held.get(order["ticker"], 0)
                                   for order in orders if order["side"] == "SELL"), "賣出不能超過實際原持股")
        check("no_short", all(row["target_shares"] >= 0 for row in positions), "不得放空")
        check("one_side_per_stock", len({order["ticker"] for order in orders}) == len(orders), "同股不可同日雙向交易")
        check("order_count", len(orders) <= 30 and len(decisions) <= 30 and len(no_trade) <= 30,
              "decisions、orders、no_trade各不得超過官方30筆")
        fees = (buy + sell) * Decimal("0.001425")
        tax = sell * Decimal("0.003")
        cash_after = account.cash_twd - buy + sell - fees - tax
        target_value = sum((row["target_shares"] * prices[row["ticker"]] for row in positions), Decimal(0))
        projected_nav = cash_after + target_value
        ratio = cash_after / projected_nav if projected_nav > 0 else None
        check("positive_nav", projected_nav > 0, "費用後預估NAV須為正")
        check("cash_nonnegative", cash_after >= 0, "費用後預估現金不可負值")
        check("holdings_count", 20 <= sum(row["target_shares"] > 0 for row in positions) <= 30,
              "委託後正持股須為20～30檔")
        caps_ok = projected_nav > 0
        for row in positions:
            actual_weight = row["target_shares"] * prices[row["ticker"]] / projected_nav if projected_nav > 0 else None
            row["projected_weight"] = str(actual_weight) if actual_weight is not None else None
            cap = Decimal("0.25") if row["ticker"] == "2330" else Decimal("0.10")
            if actual_weight is None or actual_weight > cap:
                caps_ok = False
                issues.append({"code": "stock_cap", "severity": "BLOCK", "ticker": row["ticker"],
                               "message": "費用後完整組合個股權重超過官方上限"})
        check("stock_caps", caps_ok, "完整組合須符合2330≤25%、其他個股≤10%")
        check("cash_range", ratio is not None and 0 <= ratio <= Decimal("0.25"), "費用後現金比須在0～25%")
        low, high = (Decimal(str(value)) for value in draft.market_proposal.proposed_cash_range)
        check("declared_cash_range", ratio is not None and low <= ratio <= high, "費用後現金比不在Agent宣告區間")
        net = buy - sell
        intent = draft.market_proposal.intended_flow
        posture_ok = net > 0 if intent == "increase" else net < 0 if intent == "reduce" else abs(net) <= account.nav_twd * Decimal("0.02")
        check("posture", posture_ok, "淨買賣須符合increase/reduce/hold（hold≤NAV的2%）")
        return {"report_format_version": "1.0", "as_of": cutoff, "trade_date": decision_day,
                "account_snapshot_id": account.snapshot_id, "allocation_method": "agent_target_weights",
                "positions": positions, "decisions": decisions, "orders": orders, "no_trade_tickers": no_trade,
                "cash_before_twd": str(account.cash_twd), "buy_notional_twd": str(buy),
                "sell_notional_twd": str(sell), "fees_twd": str(fees), "tax_twd": str(tax),
                "cash_after_twd": str(cash_after), "projected_nav_twd": str(projected_nav),
                "net_flow_twd": str(net), "cash_ratio": str(ratio) if ratio is not None else None,
                "checks": checks, "issues": issues, "portfolio_ok": all(checks.values()),
                "submission_ready": False, "fee_policy": "demo_exact_decimal_no_rounding",
                "limitations": ["以前收估算委託全成，不是10/1實際成交或已核對庫存。",
                                "費用保持Decimal全精度；正式取整與結算口徑尚未確認。"]}
