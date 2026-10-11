"""隔離的T日事後整數配置；求解結果不用來改寫當日決策。"""

from __future__ import annotations

from decimal import Decimal, localcontext
from math import isfinite

from etf_agent.contracts import AccountSnapshot
from etf_agent.sub_agents.test_agent.evaluation import EvaluationError, FEE, SELL_TAX, simulate, validate_quotes


def optimize_hindsight(account_raw: dict, allowed: list[str], previous_closes: dict,
                       quotes: dict, *, trade_date: str, time_limit: float = 120) -> dict:
    """最大化費後收盤NAV。HiGHS用浮點求解，股數再以Decimal獨立驗收。

    q/b/s為目標/買進/賣出整張數，h/u/v為持有/買单/賣单binary。
    同一股票不能雙向交易。限制股數公式可達成的前收權重，以及
    前收預估與T日收盤兩種取價下的費後現金和單股上限。
    """
    import numpy as np
    import scipy
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_array

    if not isfinite(time_limit) or time_limit <= 0:
        raise EvaluationError("求解時間上限須為有限正數")
    validate_quotes(quotes, trade_date)
    account = AccountSnapshot.from_dict(account_raw)
    tickers = sorted(allowed)
    if len(set(tickers)) != len(tickers) or not tickers:
        raise EvaluationError("候選池重複或為空")
    held = {p.ticker: p.shares for p in account.positions}
    unavailable = {t for t in tickers if quotes.get(t, {}).get("trading_status") == "no_trade" and t not in held}
    missing = sorted(t for t in (set(tickers) | set(held)) - unavailable
                     if not quotes.get(t, {}).get("close_twd_per_share")
                     or not quotes.get(t, {}).get("vwap_twd_per_share") or not previous_closes.get(t))
    if missing or not set(held) <= set(tickers):
        return {"scope": "full_candidate_integer_portfolio", "status": "blocked_missing_data",
                "candidate_count": len(tickers), "missing_tickers": missing,
                "held_outside_candidates": sorted(set(held) - set(tickers)), "orders": [],
                "optimal_to_solver_tolerance": False, "solution": None,
                "reason": "缺資料不縮小候選池，不把未知價格補零；無法宣稱完整候選最佳。"}
    if any(q % 1000 for q in held.values()):
        raise EvaluationError("本次整數最佳化只處理整張期初帳，零股須另行明示")
    n, scale = len(tickers), Decimal("1000000")
    size = 6 * n + 4
    cash, nav, pre_cash, pre_nav = range(6 * n, size)
    objective = np.zeros(size)
    objective[nav] = -1
    integrality = np.zeros(size, dtype=np.uint8)
    integrality[:6 * n] = 1
    lower, upper = np.zeros(size), np.full(size, np.inf)
    lower[nav] = lower[pre_nav] = 1e-6
    entries, row_lower, row_upper = [], [], []

    def constrain(coefficients, lo=-np.inf, hi=np.inf):
        index = len(row_lower)
        entries.extend((index, col, float(value)) for col, value in coefficients.items() if value)
        row_lower.append(float(lo))
        row_upper.append(float(hi))

    actual_cash_row, pre_cash_row = {cash: 1}, {pre_cash: 1}
    actual_nav_row, pre_nav_row = {nav: 1, cash: -1}, {pre_nav: 1, pre_cash: -1}
    declared_weight_row = {}
    with localcontext() as context:
        context.prec = 50
        for i, ticker in enumerate(tickers):
            q, b, s, h, u, v = (group * n + i for group in range(6))
            if ticker in unavailable:
                # 當日零成交而且原未持有：禁止建倉；不虛構close/VWAP。
                upper[[q, b, s, h, u, v]] = 0
                continue
            previous = Decimal(previous_closes[ticker])
            closing = Decimal(quotes[ticker]["close_twd_per_share"])
            vwap = Decimal(quotes[ticker]["vwap_twd_per_share"])
            cap = Decimal("0.25") if ticker == "2330" else Decimal("0.10")
            maximum = int(cap * account.nav_twd / previous / 1000)
            initial = held.get(ticker, 0) // 1000
            upper[[q, b]] = maximum
            upper[s] = initial
            upper[[h, u, v]] = 1
            constrain({q: 1, b: -1, s: 1}, initial, initial)
            constrain({q: 1, h: -maximum}, hi=0)
            constrain({q: 1, h: -1}, lo=0)
            constrain({b: 1, u: -maximum}, hi=0)
            constrain({b: 1, u: -1}, lo=0)
            constrain({s: 1, v: -initial}, hi=0)
            constrain({s: 1, v: -1}, lo=0)
            constrain({u: 1, v: 1}, hi=1)
            constrain({q: closing * 1000 / scale, nav: -cap}, hi=0)
            constrain({q: previous * 1000 / scale, pre_nav: -cap}, hi=0)
            actual_cash_row[b] = vwap * 1000 * (1 + FEE) / scale
            actual_cash_row[s] = -vwap * 1000 * (1 - FEE - SELL_TAX) / scale
            pre_cash_row[b] = previous * 1000 * (1 + FEE) / scale
            pre_cash_row[s] = -previous * 1000 * (1 - FEE - SELL_TAX) / scale
            actual_nav_row[q] = -closing * 1000 / scale
            pre_nav_row[q] = -previous * 1000 / scale
            declared_weight_row[q] = previous * 1000 / scale
        start_cash, start_nav = account.cash_twd / scale, account.nav_twd / scale
        constrain(actual_cash_row, start_cash, start_cash)
        constrain(pre_cash_row, start_cash, start_cash)
        constrain(actual_nav_row, 0, 0)
        constrain(pre_nav_row, 0, 0)
        constrain(declared_weight_row, start_nav * Decimal("0.75"), start_nav)
    constrain({cash: 1, nav: -0.25}, hi=0)
    constrain({pre_cash: 1, pre_nav: -0.25}, hi=0)
    constrain({3 * n + i: 1 for i in range(n)}, 20, 30)
    constrain({group * n + i: 1 for group in (4, 5) for i in range(n)}, hi=30)
    matrix = coo_array(([value for _, _, value in entries],
                        ([row for row, _, _ in entries], [col for _, col, _ in entries])),
                       shape=(len(row_lower), size)).tocsc()
    result = milp(objective, integrality=integrality, bounds=Bounds(lower, upper),
                  constraints=LinearConstraint(matrix, row_lower, row_upper),
                  options={"time_limit": time_limit, "mip_rel_gap": 1e-8, "presolve": True})
    report = {"scope": "full_candidate_integer_portfolio", "candidate_count": n,
              "tradable_candidate_count": n - len(unavailable), "no_trade_tickers": sorted(unavailable),
              "solver": "scipy.optimize.milp/HiGHS", "scipy_version": scipy.__version__,
              "numpy_version": np.__version__, "time_limit_seconds": time_limit,
              "solver_status": int(result.status), "solver_message": str(result.message),
              "mip_relative_gap": float(result.mip_gap) if getattr(result, "mip_gap", None) is not None else None,
              "mip_node_count": int(result.mip_node_count) if getattr(result, "mip_node_count", None) is not None else None,
              "solver_upper_bound_nav_twd": str(-Decimal(str(result.mip_dual_bound)) * scale)
              if getattr(result, "mip_dual_bound", None) is not None and isfinite(result.mip_dual_bound) else None,
              "optimal_to_solver_tolerance": False, "orders": [], "solution": None,
              "constraints": {"lot_shares": 1000, "holdings_min": 20, "holdings_max": 30,
                              "orders_max": 30, "cash_ratio_min": "0", "cash_ratio_max": "0.25",
                              "single_name_cap": "0.10", "2330_cap": "0.25",
                              "no_short": True, "no_same_stock_day_trade": True,
                              "weight_price_checks": ["previous_close_fee_adjusted", "trade_day_close_fee_adjusted"]},
              "limitations": ["事後使用T日日均價與收盤，不是當時可知的投資策略。",
                              "最佳僅指明列候選池、費稅及財務限制下的單日NAV；沒有證據鏈或正式資格保證。",
                              "費用與NAV不做主辦方未確認的取整；公司行動與成交失敗另列限制。",
                              "HiGHS浮點求解，最終股數與財務限制以50位Decimal重算，不任意放寬上限。"]}
    if result.x is None:
        report["status"] = "infeasible" if result.status == 2 else "no_solution"
        return report
    if any(abs(result.x[i] - round(result.x[i])) > 1e-5 for i in range(6 * n)):
        raise EvaluationError("求解結果未滿足整數要求，不能四捨五入冒充有效配置")
    target = {ticker: int(round(result.x[i])) * 1000 for i, ticker in enumerate(tickers)}
    orders = []
    for ticker in tickers:
        delta = target[ticker] - held.get(ticker, 0)
        if delta:
            orders.append({"ticker": ticker, "side": "BUY" if delta > 0 else "SELL", "shares": abs(delta)})
    solution = simulate(account_raw, orders, quotes, trade_date=trade_date,
                        previous_closes=previous_closes, scenario="hindsight_best")
    previous_quotes = {ticker: {"ticker": ticker, "trade_date": trade_date,
                              "close_twd_per_share": price, "vwap_twd_per_share": price,
                              "volume_shares": 1000, "amount_twd": str(Decimal(price) * 1000)}
                       for ticker, price in previous_closes.items() if price is not None}
    projected = simulate(account_raw, orders, previous_quotes, trade_date=trade_date,
                         previous_closes=previous_closes, scenario="hindsight_previous_close_check")
    with localcontext() as context:
        context.prec = 50
        total_weight = sum((Decimal(previous_closes[t]) * q for t, q in target.items() if q), Decimal(0)) / account.nav_twd
        weights_ok = Decimal("0.75") <= total_weight <= 1 and all(
            Decimal(previous_closes[t]) * q <= account.nav_twd * (Decimal("0.25") if t == "2330" else Decimal("0.10"))
            for t, q in target.items() if q)
    report.update(orders=orders, target_shares=target, solution=solution, previous_close_checks=projected["checks"],
                  implied_cash_target_ratio=str(1 - total_weight))
    if not (solution["constraint_checks_ok"] and projected["constraint_checks_ok"] and weights_ok):
        report["status"] = "rejected_decimal_validation"
        report["reason"] = "求解器浮點候選未通過精確重算，不能視為最佳或有效配置"
        return report
    report["status"] = ("optimal" if result.status == 0 else "feasible_limit_reached" if result.status == 1
                        else "rejected_solver_status")
    report["optimal_to_solver_tolerance"] = result.status == 0
    return report
