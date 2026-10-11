"""F04 結構與本地 D-Plan 語意驗證；估計財務不代表正式成交或提交資格。"""

import json
import math
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


from etf_agent.paths import project_root


OFFICIAL_SCHEMA = project_root() / "specs/official/04_D-Plan.schema_v4.2.json"


def _check(code, passed, message):
    return {"code": code, "severity": "PASS" if passed else "BLOCK", "message": message}


def _day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("日期須為有效 YYYY-MM-DD")
    return date.fromisoformat(value)


def _time(value):
    if type(value) is not str or not value.endswith("+08:00"):
        raise ValueError("時間須使用 +08:00")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(hours=8):
        raise ValueError("時間須使用 +08:00")
    return parsed


def _decimal(value):
    if type(value) not in (int, float, str, Decimal):
        raise ValueError("金額或比例型別錯誤")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("金額或比例須為有限數值")
    return result


def _frozen_values(values):
    """重現編譯器的數字轉換；scope 說明不是官方 values 的數值事實。"""
    result = {}
    for key, value in values.items():
        if type(value) is int:
            result[key] = value
            continue
        try:
            number = float(_decimal(value))
            if not math.isfinite(number):
                raise ValueError("觀察值非有限數字")
            result[key] = number
        except (ValueError, InvalidOperation):
            if key != "scope":
                raise ValueError(f"凍結觀察值 {key} 無法轉為官方數字")
    return result


def validate_structure(plan, schema_path=OFFICIAL_SCHEMA) -> list[dict]:
    """執行原版 JSON schema，另補其 pattern 未檢查的真實日期與時間順序。"""
    checks = []
    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8-sig"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(plan), key=lambda e: str(list(e.path))):
            checks.append(_check("schema", False, f"{list(error.path)}: {error.message}"))
    except (OSError, ValueError) as exc:
        return [_check("schema_unavailable", False, str(exc))]

    def walk(value, path="plan"):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif type(value) is float and not math.isfinite(value):
            checks.append(_check("nonfinite_number", False, f"{path} 不可為 NaN 或 Infinity"))
        elif isinstance(value, Decimal):
            checks.append(_check("json_number_type", False, f"{path} 應為 JSON 數值，不能直接放 Decimal"))
    walk(plan)
    if isinstance(plan, dict):
        try:
            _day(plan.get("trade_date"))
        except (TypeError, ValueError):
            checks.append(_check("calendar_date", False, "trade_date 不是有效日期"))
        times = []
        for index, source in enumerate(plan.get("sources", []) if isinstance(plan.get("sources"), list) else []):
            if isinstance(source, dict):
                times.extend((f"sources[{index}].{key}", source[key]) for key in
                             ("content_as_of", "published_at", "fetched_at") if key in source)
        metadata = plan.get("agent_metadata")
        if isinstance(metadata, dict):
            times.extend((f"agent_metadata.{key}", metadata[key]) for key in
                         ("run_started_at", "run_completed_at") if key in metadata)
        for label, value in times:
            try:
                _time(value)
            except (TypeError, ValueError):
                checks.append(_check("calendar_timestamp", False, f"{label} 日期／時間／時區錯誤"))
        if isinstance(metadata, dict):
            try:
                if _time(metadata["run_completed_at"]) < _time(metadata["run_started_at"]):
                    checks.append(_check("run_time_order", False, "執行結束不可早於開始"))
            except (KeyError, TypeError, ValueError):
                pass  # 必填或格式問題已由 schema／timestamp 檢查列出。
    if not checks:
        checks.append(_check("schema_valid", True, "F04 v4.2 結構與日期／時間檢查通過"))
    return checks


def validate_dplan(plan, packet, *, portfolio=None) -> dict:
    """對當前plan重推股數與財務；另保留草稿意圖／配置失敗，舊PASS不能取代重算。"""
    checks = validate_structure(plan)
    schema_ok = not any(item["severity"] == "BLOCK" for item in checks)
    semantics = []
    frozen_facts_present = isinstance(packet, dict) and "sources" in packet and "observations" in packet

    def add(code, passed, message):
        semantics.append(_check(code, passed, message))

    if portfolio is not None:
        add("portfolio_gate", isinstance(portfolio, dict) and portfolio.get("portfolio_ok") is True
            and not any(item.get("severity") == "BLOCK" for item in portfolio.get("issues", [])),
            "草稿意圖與完整配置檢查須通過；配置BLOCK不能被no_trade結構掩蓋")

    def refs(values, known, label):
        missing = [value for value in values if value not in known]
        add("reference_chain", not missing, f"{label} 引用不存在的 ID：{missing}" if missing else f"{label} 引用完整")

    if schema_ok:
        try:
            cutoff = _day(packet["as_of"])
            add("trade_date", plan["trade_date"] == packet["trade_date"] and _day(plan["trade_date"]) > cutoff,
                "計畫決策日須與 packet 相同且晚於資料截止")
            groups = {}
            for field, key, prefix in (("sources", "source_id", "S"), ("observations", "obs_id", "O"),
                                       ("inferences", "inf_id", "I"), ("decisions", "decision_id", "D")):
                ids = [row[key] for row in plan[field]]
                add("continuous_ids", ids == [f"{prefix}{i}" for i in range(1, len(ids) + 1)],
                    f"{field} ID 須從 {prefix}1 連續遞增且唯一")
                groups[prefix] = set(ids)
            for row in plan["observations"]:
                refs(row["source_ref"], groups["S"], row["obs_id"])
            refs(plan["market_view"]["basis_refs"], groups["O"], "market_view")
            for row in plan["inferences"]:
                refs(row["premise_refs"], groups["O"], row["inf_id"])
            for row in plan["decisions"]:
                refs(row["inference_refs"], groups["I"], row["decision_id"])
            for row in plan["no_trade_decisions"]:
                refs(row["reason_refs"], groups["I"], row["ticker"])
            for row in plan["orders"]:
                refs([row["decision_ref"]], groups["D"], row["ticker"] + " order")
            for row in plan["sources"]:
                add("source_cutoff", _time(row["content_as_of"]).date() <= cutoff,
                    f"{row['source_id']} 內容描述日期不得晚於 {cutoff}")

            if frozen_facts_present:
                frozen_sources = {row["source_id"]: (row["authority"], row["url"])
                                  for row in packet["sources"]}
                official_sources = {row["source_id"]: (row["authority"], row["url"])
                                    for row in plan["sources"]}
                for source_id, identity in official_sources.items():
                    add("frozen_source", identity in frozen_sources.values(),
                        f"{source_id} url／authority 必須來自凍結來源，來源ID可重新編號")
                original_facts = []
                for row in packet["observations"]:
                    original_facts.append((row["statement"].split(" 人工期初持股 ")[0],
                                           _frozen_values(row["values"]),
                                           Counter(frozen_sources[ref] for ref in row["source_ref"])))
                for row in plan["observations"]:
                    identity = (row["statement"], row["values"],
                                Counter(official_sources.get(ref) for ref in row["source_ref"]))
                    add("frozen_observation", identity in original_facts,
                        f"{row['obs_id']} statement／數字values／來源身份組合須對應凍結事實")

            account = packet["account_snapshot"]
            add("account_date", _day(account["as_of_trade_date"]) == cutoff, "期初帳戶日期須等於資料截止")
            held_rows = account["positions"]
            held = {row["ticker"]: row["shares"] for row in held_rows}
            add("initial_positions", len(held) == len(held_rows) and all(type(q) is int and q > 0 for q in held.values()),
                "期初持股須唯一且為正整數股數")
            data = packet["data_report"]
            allowed = set(packet.get("allowed_tickers", [])) | set(held)
            prices = {}
            for row in (*data.get("rankings", []), *data.get("held_positions", [])):
                allowed.add(row["ticker"])
                value = row.get("close_twd_per_share")
                if value is not None:
                    prices[row["ticker"]] = _decimal(value)
            allowed.update(row["ticker"] for row in data.get("excluded_stocks", []))
            for source in data.get("sources", []):
                allowed.update(row["ticker"] for row in source.get("members", []))
            all_tickers = [row["ticker"] for field in ("decisions", "no_trade_decisions", "orders") for row in plan[field]]
            add("whitelist", all(ticker in allowed for ticker in all_tickers), "決策／續抱／委託必須在 packet 股票白名單內")
            decision_tickers = [row["ticker"] for row in plan["decisions"]]
            keep_tickers = [row["ticker"] for row in plan["no_trade_decisions"]]
            counts = Counter(decision_tickers + keep_tickers)
            add("held_coverage", all(counts[ticker] == 1 for ticker in held), "全部原持股須恰好出現於異動或續抱之一")
            add("unique_decisions", len(set(decision_tickers)) == len(decision_tickers)
                and len(set(keep_tickers)) == len(keep_tickers) and not set(decision_tickers) & set(keep_tickers),
                "異動與續抱不得重複或重疊")
            add("keep_existing", set(keep_tickers) <= set(held), "續抱只能引用原持股")
            nav, cash = _decimal(account["nav_twd"]), _decimal(account["cash_twd"])
            if nav <= 0 or cash < 0 or any(price <= 0 for price in prices.values()):
                raise ValueError("NAV／現金／價格無效")
            required_prices = set(held) | set(decision_tickers) | {row["ticker"] for row in plan["orders"]}
            if not required_prices <= prices.keys():
                raise ValueError(f"估計財務缺行情：{sorted(required_prices - prices.keys())}")
            from etf_agent.decision.portfolio import derive_target_shares
            expected_orders = []
            decisions = {row["decision_id"]: row for row in plan["decisions"]}
            for row in plan["decisions"]:
                ticker = row["ticker"]
                weight = _decimal(row["target_weight"])
                target = derive_target_shares(weight, nav, prices[ticker])
                current = held.get(ticker, 0)
                delta = target - current
                expected_action = "BUY" if current == 0 and delta > 0 else "SELL_ALL" if current > 0 and target == 0 \
                    else "ADD" if current > 0 and delta > 0 else "TRIM" if current > 0 and 0 < target < current else None
                add("action_direction", row["action"] == expected_action, f"{ticker} action須符合實際期初／目標股數")
                add("stock_target_cap", weight <= (Decimal("0.25") if ticker == "2330" else Decimal("0.10")),
                    f"{ticker} 目標權重須符合個股上限")
                if delta:
                    expected_orders.append((ticker, "BUY" if delta > 0 else "SELL", abs(delta), row["decision_id"]))
            actual_orders = [(row["ticker"], row["side"], row["shares"], row["decision_ref"]) for row in plan["orders"]]
            add("official_order_formula", Counter(actual_orders) == Counter(expected_orders),
                "orders須精確對應官方floor、方向、股數、ticker及decision_ref；零差額應續抱")
            add("unique_orders", len({row["ticker"] for row in plan["orders"]}) == len(plan["orders"]),
                "每股委託不得重複")
            add("keep_unchanged", not set(keep_tickers) & {row["ticker"] for row in plan["orders"]}, "續抱股不得產生委託")
            final = dict(held)
            buy = sell = Decimal(0)
            oversold = False
            with localcontext() as context:
                context.prec = 80
                for row in plan["orders"]:
                    ticker, quantity = row["ticker"], row["shares"]
                    value = prices[ticker] * quantity
                    if row["side"] == "BUY":
                        buy += value
                        final[ticker] = final.get(ticker, 0) + quantity
                    else:
                        sell += value
                        oversold |= quantity > held.get(ticker, 0)
                        final[ticker] = final.get(ticker, 0) - quantity
                add("no_oversell", not oversold and all(q >= 0 for q in final.values()), "賣出股數不可超過實際原持股")
                origin_value = sum((q * prices[ticker] for ticker, q in held.items()), Decimal(0))
                add("initial_nav", cash + origin_value == nav, "期初NAV須等於現金加完整持股收盤市值")
                fee, tax = (buy + sell) * Decimal("0.001425"), sell * Decimal("0.003")
                cash_after = cash - buy + sell - fee - tax
                stock_after = sum((q * prices[ticker] for ticker, q in final.items()), Decimal(0))
                nav_after = cash_after + stock_after
                if nav_after <= 0:
                    raise ValueError("委託後預估NAV非正")
                ratio = cash_after / nav_after
                add("cash_nonnegative", cash_after >= 0, "委託後預估現金不可負")
                add("holdings_count", 20 <= sum(q > 0 for q in final.values()) <= 30, "完整委託後持股須20～30檔")
                add("portfolio_caps", all(q * prices[ticker] / nav_after <=
                    (Decimal("0.25") if ticker == "2330" else Decimal("0.10")) for ticker, q in final.items() if q > 0),
                    "全部委託後持股權重須符合上限")
                add("cash_limit", Decimal(0) <= ratio <= Decimal("0.25"), "委託後現金比須0～25%")
                posture = plan["market_view"]["posture"]
                low, high = map(_decimal, posture["target_cash_pct_range"])
                add("declared_cash_range", low <= high and low <= ratio <= high, "預估現金比須落在宣告區間")
                flow = buy - sell
                intent = posture["net_exposure_intent"]
                flow_ok = flow > 0 if intent == "increase" else flow < 0 if intent == "reduce" else abs(flow) <= nav * Decimal("0.02")
                add("posture_flow", flow_ok, "委託淨流向須符合posture；hold預設2% NAV容差")
                marked = {row["decision_id"] for row in plan["decisions"] if row.get("funding_for")}
                for row in plan["decisions"]:
                    if row.get("funding_for"):
                        targets = row["funding_for"]
                        add("funding_refs", row["action"] in ("TRIM", "SELL_ALL") and all(
                            key in decisions and decisions[key]["action"] in ("BUY", "ADD") for key in targets),
                            "funding_for須由賣出引用同日BUY/ADD決策")
                if marked:
                    marked_value = sum((prices[row["ticker"]] * row["shares"] for row in plan["orders"]
                                        if row["side"] == "SELL" and row["decision_ref"] in marked), Decimal(0))
                    remaining_sell = sell - marked_value
                    remaining_cost = (buy + remaining_sell) * Decimal("0.001425") + remaining_sell * Decimal("0.003")
                    without_cash = cash - buy + remaining_sell - remaining_cost
                    without_nav = nav - remaining_cost
                    add("funding_shortfall", marked_value > 0 and without_nav > 0 and without_cash / without_nav < low,
                        "移除全部標記調度賣出後現金比須低於宣告下限，缺口須實際存在")
            trusted = packet.get("agent_metadata")
            if trusted is not None:
                add("metadata_matches_run", plan["agent_metadata"] == trusted, "模型執行metadata須與保存的真實紀錄相符")
        except (KeyError, TypeError, ValueError, InvalidOperation, ArithmeticError) as exc:
            add("semantic_context", False, f"語意輸入或計算無法完成：{exc}")
    else:
        add("semantic_skipped", False, "結構未通過，不能宣稱語意驗證完成")
    checks.extend(semantics)
    semantic_ok = bool(semantics) and not any(row["severity"] == "BLOCK" for row in semantics)
    return {"scope": "dplan_local", "mode": "demo", "schema_ok": schema_ok,
            "semantic_ok": semantic_ok, "local_validation_ok": schema_ok and semantic_ok,
            "checks": checks, "issues": [row for row in checks if row["severity"] == "BLOCK"],
            "formal_eligible": False, "submission_ready": False,
            "limitations": ["預估價格為前收，費用Decimal不取整，尚非正式結算。",
                            "歷史demo使用實際執行日期，不偽造2025年的模型執行時刻。",
                            "本地metadata欄位驗證不替代真實模型回覆與官方資格核對。",
                            *([] if frozen_facts_present else ["packet未含凍結sources／observations；本次未核對事實內容來源。"])]}
