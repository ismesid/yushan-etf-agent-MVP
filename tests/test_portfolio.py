"""官方floor與完整组合的重要案例；全部價格、帳戶及代號為人工測試資料。"""

import copy
import unittest
from decimal import Decimal

from etf_agent.contracts import WeightedAgentDraft
from etf_agent.decision.portfolio import PortfolioError, build_portfolio, derive_target_shares


def fixtures():
    tickers = [str(1000 + i) for i in range(26)]
    held = tickers[:25]
    account = {"contract_version": "1.0", "snapshot_id": "artificial-account",
               "as_of_trade_date": "2025-09-30", "status": "demo",
               "cash_twd": "125000000", "nav_twd": "1000000000",
               "positions": [{"ticker": ticker, "shares": 35000} for ticker in held],
               "origin": "artificial_portfolio_test", "reconciled": False, "demo": True,
               "origin_ref": None}
    obs = {ticker: f"O{i + 2}" for i, ticker in enumerate(tickers)}
    prices = [{"ticker": ticker, "close_twd_per_share": "1000", "demo_candidate": True}
              for ticker in tickers]
    packet = {"as_of": "2025-09-30", "trade_date": "2025-10-01",
              "account_snapshot": account, "allowed_tickers": tickers,
              "data_report": {"as_of": "2025-09-30", "account_snapshot": copy.deepcopy(account),
                              "allowed_tickers": tickers, "rankings": prices,
                              "held_positions": copy.deepcopy(prices[:25])},
              "observations": [{"obs_id": ref} for ref in ["O1", *obs.values()]],
              "stock_observation_ids": obs, "demo_decision_ready": True}
    raw = {"contract_version": "2.0",
           "market_proposal": {"regime": "neutral", "stance": "neutral", "cash_target": 0.125,
                               "proposed_cash_range": [0.10, 0.20], "intended_flow": "hold",
                               "basis_obs_ids": ["O1"], "rationale": "人工測試", "counter_evidence": None},
           "selections": [{"ticker": ticker, "target_weight": "0.035",
                           "supporting_obs_ids": [obs[ticker]], "rationale": "人工測試", "counter_evidence": None}
                          for ticker in held],
           "held_reviews": [{"ticker": ticker, "intent": "keep", "supporting_obs_ids": [obs[ticker]],
                             "rationale": "人工測試", "counter_evidence": None} for ticker in held]}
    return packet, raw


def swap_fixture():
    packet, raw = fixtures()
    first = raw["selections"].pop(0)
    raw["selections"].append({**first, "ticker": "1025", "supporting_obs_ids": ["O27"]})
    raw["held_reviews"][0]["intent"] = "exit"
    raw["held_reviews"][1]["intent"] = "rebalance"
    raw["held_reviews"][2]["intent"] = "rebalance"
    raw["selections"][0]["target_weight"] = "0.030"
    raw["selections"][1]["target_weight"] = "0.040"
    return packet, raw


class PortfolioTests(unittest.TestCase):
    def test_floor_is_exact_at_and_just_below_whole_lot_boundary(self):
        self.assertEqual(derive_target_shares(Decimal("0.04"), Decimal("1000000000"), Decimal("1000")), 40000)
        self.assertEqual(derive_target_shares(Decimal("0.039999999999999999999999999999999999"),
                                              Decimal("1000000000"), Decimal("1000")), 39000)
        self.assertEqual(derive_target_shares(Decimal(0), Decimal("1000000000"), Decimal("1000")), 0)
        for weight, nav, close in ((Decimal("-0.1"), Decimal(1), Decimal(1)),
                                   (Decimal("0.1"), Decimal(0), Decimal(1)),
                                   (Decimal("0.1"), Decimal(1), Decimal(0))):
            with self.subTest(weight=weight, nav=nav, close=close), self.assertRaises(PortfolioError):
                derive_target_shares(weight, nav, close)

    def test_buy_add_trim_sell_all_and_no_trade_use_full_holdings_without_overselling(self):
        packet, raw = swap_fixture()
        original = copy.deepcopy(packet)
        report = build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
        self.assertTrue(report["portfolio_ok"], report["issues"])
        self.assertEqual([row["action"] for row in report["decisions"]], ["SELL_ALL", "TRIM", "ADD", "BUY"])
        self.assertEqual([row["decision_id"] for row in report["decisions"]], ["D1", "D2", "D3", "D4"])
        self.assertEqual([row["shares"] for row in report["orders"]], [35000, 5000, 5000, 35000])
        self.assertEqual(len(report["no_trade_tickers"]), 22)
        originals = {row["ticker"]: row["shares"] for row in packet["account_snapshot"]["positions"]}
        for order in report["orders"]:
            self.assertEqual(order["shares"] % 1000, 0)
            if order["side"] == "SELL":
                self.assertLessEqual(order["shares"], originals[order["ticker"]])
        self.assertEqual(Decimal(report["fees_twd"]), Decimal("114000"))
        self.assertEqual(Decimal(report["tax_twd"]), Decimal("120000"))
        self.assertEqual(Decimal(report["cash_after_twd"]), Decimal("124766000"))
        self.assertEqual(Decimal(report["projected_nav_twd"]), Decimal("999766000"))
        self.assertEqual(Decimal(report["net_flow_twd"]), Decimal(0))
        self.assertFalse(report["submission_ready"])
        self.assertEqual(packet, original)

    def test_keep_keeps_original_shares_and_requires_matching_requested_floor(self):
        packet, raw = fixtures()
        normal = build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
        self.assertTrue(normal["portfolio_ok"])
        self.assertEqual(normal["orders"], [])
        self.assertEqual(len(normal["no_trade_tickers"]), 25)
        raw["selections"][0]["target_weight"] = "0.036"
        raw["selections"][1]["target_weight"] = "0.034"
        report = build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
        self.assertFalse(report["portfolio_ok"])
        self.assertFalse(report["checks"]["keep_intent"])
        self.assertEqual(report["positions"][0]["current_shares"], 35000)
        self.assertEqual(report["positions"][0]["target_shares"], 35000)
        self.assertEqual(report["positions"][0]["requested_target_shares"], 36000)
        self.assertEqual(report["orders"], [])

    def test_fees_can_make_zero_cash_target_unfunded_and_report_blocks(self):
        packet, raw = fixtures()
        raw["market_proposal"].update(cash_target=0, proposed_cash_range=[0, 0.05], intended_flow="increase")
        for row in raw["selections"]:
            row["target_weight"] = "0.04"
        for review in raw["held_reviews"]:
            review["intent"] = "rebalance"
        report = build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
        self.assertFalse(report["portfolio_ok"])
        self.assertLess(Decimal(report["cash_after_twd"]), 0)
        self.assertFalse(report["checks"]["cash_nonnegative"])
        self.assertTrue(report["checks"]["posture"])
        self.assertTrue(report["checks"]["no_overselling"])

    def test_cash_interval_and_declared_posture_mismatches_block_without_changing_orders(self):
        for change, failed_check in (({"intended_flow": "increase"}, "posture"),
                                     ({"proposed_cash_range": [0.125, 0.125]}, "declared_cash_range")):
            with self.subTest(change=change):
                packet, raw = swap_fixture()
                raw["market_proposal"].update(change)
                report = build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
                self.assertFalse(report["portfolio_ok"])
                self.assertFalse(report["checks"][failed_check])
                self.assertEqual(len(report["orders"]), 4)

    def test_odd_lot_inventory_is_preserved_and_blocks_integer_lot_orders(self):
        packet, raw = fixtures()
        for account in (packet["account_snapshot"], packet["data_report"]["account_snapshot"]):
            account["positions"][0]["shares"] = 35001
            account["cash_twd"] = "124999000"
        raw["held_reviews"][0]["intent"] = "rebalance"
        report = build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
        self.assertFalse(report["portfolio_ok"])
        self.assertFalse(report["checks"]["whole_lots"])
        self.assertEqual(report["positions"][0]["current_shares"], 35001)
        self.assertEqual(report["orders"][0]["shares"], 1)
        self.assertTrue(report["checks"]["no_overselling"])

    def test_per_stock_reference_and_missing_price_are_hard_input_errors(self):
        packet, raw = fixtures()
        raw["selections"][0]["supporting_obs_ids"] = ["O1"]
        with self.assertRaises(PortfolioError):
            build_portfolio(packet, WeightedAgentDraft.from_dict(raw))
        packet, raw = fixtures()
        packet["data_report"]["rankings"][0]["close_twd_per_share"] = None
        packet["data_report"]["held_positions"][0]["close_twd_per_share"] = None
        with self.assertRaises(PortfolioError):
            build_portfolio(packet, WeightedAgentDraft.from_dict(raw))


if __name__ == "__main__":
    unittest.main()
