"""純Markdown檢查視圖；人工草稿／計畫，沒有行情、模型或策略執行。"""

import copy
import re
import unittest
from decimal import Decimal

from etf_agent.contracts import WeightedAgentDraft
from etf_agent.decision.markdown import render_plan_markdown


def fixture():
    tickers = [str(1000 + index) for index in range(25)]
    rationale = "人工依據 | 觀察\n保留 [理由](https://example.invalid) <script>字串</script>。"
    raw = {"contract_version": "2.0", "market_proposal": {
        "regime": "neutral", "stance": "neutral", "cash_target": 0.125,
        "proposed_cash_range": [0.10, 0.20], "intended_flow": "hold", "basis_obs_ids": ["O1"],
        "rationale": "人工市場現金理由，僅測試保留原始文字。", "counter_evidence": "人工市場反證。"},
        "selections": [{"ticker": ticker, "target_weight": "0.035", "supporting_obs_ids": [f"O{index+2}"],
                        "rationale": rationale + ticker, "counter_evidence": "人工選股反證 | " + ticker}
                       for index, ticker in enumerate(tickers)],
        "held_reviews": [{"ticker": ticker, "intent": "keep", "supporting_obs_ids": [f"O{index+2}"],
                          "rationale": "人工續抱理由 " + ticker, "counter_evidence": None} for index, ticker in enumerate(tickers)]}
    # 退出1000、新買1025，其他24檔KEEP；資料皆為人工數值，不在renderer算股數。
    raw["selections"][0].update(ticker="1025", supporting_obs_ids=["O27"])
    raw["held_reviews"][0].update(intent="exit", rationale="人工退出理由：依據原觀察決定退出。",
                                  counter_evidence="人工退出反證。")
    draft = WeightedAgentDraft.from_dict(raw)
    positions = [{"ticker": ticker, "current_shares": 35000 if ticker != "1025" else 0,
                  "target_shares": 0 if ticker == "1000" else 35000,
                  "target_weight": "0" if ticker == "1000" else "0.035",
                  "projected_weight": "0" if ticker == "1000" else "0.0351",
                  "close_twd_per_share": "1000"} for ticker in [*tickers, "1025"]]
    no_trade = tickers[1:]
    orders = [{"ticker": "1000", "side": "SELL", "shares": 35000, "decision_ref": "D1"},
              {"ticker": "1025", "side": "BUY", "shares": 35000, "decision_ref": "D2"}]
    plan = {"agent_metadata": {"model_version": "ARTIFICIAL_MODEL"}, "orders": orders,
            "market_view": {"basis_refs": ["O1"]},
            "decisions": [{"ticker": "1000", "action": "SELL_ALL", "decision_id": "D1", "inference_refs": ["I1"]},
                          {"ticker": "1025", "action": "BUY", "decision_id": "D2", "inference_refs": ["I26"]}],
            "no_trade_decisions": [{"ticker": ticker, "reason_refs": [f"I{index+2}"]} for index,ticker in enumerate(no_trade)],
            "sources": [{"source_id": "S1", "name": "人工來源", "url": "https://example.invalid/source", "content_as_of": "2025-09-30T23:59:59+08:00"}],
            "observations": [{"obs_id": "O1", "source_ref": ["S1"], "statement": "人工市場觀察"},
                             {"obs_id": "O2", "source_ref": ["S1"], "statement": "人工股票觀察"}],
            "inferences": [{"inf_id": "I1", "premise_refs": ["O2"]}, {"inf_id": "I26", "premise_refs": ["O3"]}]}
    packet = {"as_of": "2025-09-30", "trade_date": "2025-10-01", "account_snapshot": {"nav_twd": "1000000000"},
              "data_report": {"mode": "historical_demo", "rankings": [{"ticker": row["ticker"], "name": "人工股票"} for row in positions],
                              "issues": [], "excluded_stocks": []},
              "review_report": {"status": "prior_run_missing", "reason": "人工：沒有昨日封存計畫。"},
              "account_report": {"issues": []}, "limitations": ["人工示例，不是真實行情。"]}
    result = {"as_of": packet["as_of"], "trade_date": packet["trade_date"], "decision_source": "fixture",
              "real_agent_decision": False, "submission_ready": False, "plan": plan,
              "portfolio": {"positions": positions, "decisions": copy.deepcopy(plan["decisions"]),
                            "orders": orders, "no_trade_tickers": no_trade, "portfolio_ok": True, "issues": [],
                            "cash_before_twd": "125000000", "buy_notional_twd": "35000000", "sell_notional_twd": "35000000",
                            "fees_twd": "99750", "tax_twd": "105000", "cash_after_twd": "124795250",
                            "projected_nav_twd": "999795250", "net_flow_twd": "0", "cash_ratio": "0.124820806",
                            "limitations": ["人工前收估算。"]},
              "validation": {"schema_ok": True, "semantic_ok": True, "local_validation_ok": True,
                             "formal_eligible": False, "submission_ready": False, "issues": [],
                             "checks": [{"code": "artificial_check", "severity": "PASS", "message": "人工檢查通過。"}]}}
    return result, packet, draft


class PlanMarkdownTests(unittest.TestCase):
    def test_original_reasons_references_and_money_are_preserved_without_mutating_inputs(self):
        result, packet, draft = fixture()
        before = copy.deepcopy((result, packet, draft.to_dict()))
        markdown = render_plan_markdown(result, packet, draft)
        self.assertIn(draft.market_proposal.rationale, markdown)
        self.assertIn(draft.market_proposal.counter_evidence, markdown)
        self.assertIn("人工續抱理由 1001", markdown)
        self.assertIn("人工退出理由：依據原觀察決定退出。", markdown)
        self.assertIn("人工退出反證。", markdown)
        self.assertIn("保留 \\[理由\\]\\(https://example.invalid\\) &lt;script&gt;字串&lt;/script&gt;。1000", markdown)
        self.assertIn("| 期初帳戶 NAV | 1000000000 |", markdown)
        self.assertIn("| 買賣手續費 | 99750 |", markdown)
        self.assertIn("| 推論 I | 官方前提 O |", markdown)
        self.assertIn('| I1 | \\["O2"\\] |', markdown)
        self.assertEqual((result, packet, draft.to_dict()), before)

    def test_keep_exit_buy_show_supplied_shares_and_official_order_references(self):
        result, packet, draft = fixture()
        markdown = render_plan_markdown(result, packet, draft)
        self.assertIn("| 1000 | 人工股票 | 退出（SELL\\_ALL） | 35000 | 0 |", markdown)
        self.assertIn("| 1001 | 人工股票 | 續抱（KEEP） | 35000 | 35000 |", markdown)
        self.assertIn("| 1025 | 人工股票 | 新買（BUY） | 0 | 35000 |", markdown)
        self.assertIn("| 1000 | SELL | 35000 | D1 |", markdown)
        self.assertIn("| 1025 | BUY | 35000 | D2 |", markdown)
        # 故意使用公式算不出的數值，證明渲染器沒有重新推導或更正股數。
        result["portfolio"]["positions"][1]["target_shares"] = 12345
        self.assertIn("| 1001 | 人工股票 | 續抱（KEEP） | 35000 | 12345 |", render_plan_markdown(result, packet, draft))

    def test_fixture_candidate_block_unknown_and_real_local_pass_are_distinct(self):
        result, packet, draft = fixture()
        self.assertIn("# ETF 決策檢查：候選計畫", render_plan_markdown(result, packet, draft))
        result["validation"].update(schema_ok=False, semantic_ok=False, local_validation_ok=False)
        result["validation"]["issues"] = [{"code": "missing_model", "severity": "BLOCK", "ticker": None, "message": "模型身分未知"}]
        result["plan"]["agent_metadata"] = {}
        result["portfolio"].update(cash_after_twd=None, projected_nav_twd=None, cash_ratio=None)
        markdown = render_plan_markdown(result, packet, draft)
        self.assertIn("候選計畫／BLOCK", markdown)
        self.assertIn("| 模型 ID | 未知 |", markdown)
        self.assertIn("| 費後投影 NAV | 未知 |", markdown)
        self.assertIn("missing\\_model", markdown)
        self.assertIn("模型身分未知", markdown)
        self.assertIn("| 正式資格 | 否 |", markdown)
        result.update(decision_source="real", real_agent_decision=True)
        result["validation"].update(schema_ok=True, semantic_ok=True, local_validation_ok=True)
        self.assertIn("歷史 demo 計畫（本地 PASS）", render_plan_markdown(result, packet, draft))

    def test_special_text_cannot_add_table_columns_markdown_links_or_raw_html(self):
        result, packet, draft = fixture()
        result["plan"]["observations"][0]["statement"] = "a|b\r\n![圖](https://example.invalid/img) <img src=x onerror=bad> `code`"
        packet["data_report"]["rankings"][0]["name"] = "人工 | 名稱\n<script>bad</script>"
        markdown = render_plan_markdown(result, packet, draft)
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("<img src=", markdown)
        self.assertNotIn("![圖](", markdown)
        self.assertIn("a\\|b<br>\\!\\[圖\\]\\(https://example.invalid/img\\)", markdown)
        table_width = None
        for line in markdown.splitlines():
            if not line.startswith("|"):
                table_width = None
                continue
            width = len(re.split(r'(?<!\\)\|', line))
            if table_width is None:
                table_width = width
            self.assertEqual(width, table_width, line)

    def test_zero_orders_keep_complete_holdings_and_unknown_values_do_not_become_zero(self):
        result, packet, draft = fixture()
        raw = draft.to_dict()
        raw["selections"][0].update(ticker="1000", supporting_obs_ids=["O2"])
        raw["held_reviews"][0]["intent"] = "keep"
        draft = WeightedAgentDraft.from_dict(raw)
        result["plan"].update(orders=[], decisions=[])
        positions = result["portfolio"]["positions"][:-1]
        positions[0].update(target_shares=35000, target_weight="0.035")
        tickers = [row["ticker"] for row in positions]
        result["plan"]["no_trade_decisions"] = [{"ticker": ticker, "reason_refs": [f"I{index+1}"]}
                                                for index,ticker in enumerate(tickers)]
        result["portfolio"].update(positions=positions, orders=[], decisions=[], no_trade_tickers=tickers,
                                   buy_notional_twd="0", sell_notional_twd="0", fees_twd="0", tax_twd="0",
                                   cash_after_twd=Decimal("125000000.0000"), projected_nav_twd="1000000000",
                                   cash_ratio=None)
        markdown = render_plan_markdown(result, packet, draft)
        self.assertIn("本計畫沒有買賣委託", markdown)
        self.assertIn("| 費後預估現金 | 125000000.0000 |", markdown)
        self.assertIn("| 費後現金比率（0～1） | 未知 |", markdown)
        self.assertIn("| 1001 | 人工股票 | 續抱（KEEP） | 35000 | 35000 |", markdown)
        self.assertEqual(sum("續抱（KEEP）" in line for line in markdown.splitlines()), 25)
        self.assertIn("原持股反方證據：未知", markdown)


if __name__ == "__main__":
    unittest.main()
