"""Account agent checks use synthetic prices and never read a market cache."""

import copy
import unittest
from decimal import Decimal

from etf_agent.sub_agents.account_agent.account import value_account
from etf_agent.contracts import AccountSnapshot
from etf_agent.sub_agents.account_agent import report_account


DAY = "2025-09-30"


class AccountAgentTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "contract_version": "1.0", "snapshot_id": "test-account-1b",
            "as_of_trade_date": DAY, "status": "demo", "cash_twd": "125000000.00",
            "nav_twd": "1000000000.00",
            "positions": [{"ticker": str(1100 + index), "shares": 350000} for index in range(25)],
            "origin": "artificial_test", "origin_ref": None, "demo": True, "reconciled": False,
        }
        self.context = {
            "as_of": DAY, "stocks": {}, "quotes": {}, "issues": [],
            "inputs": {"daily_prices": {"path": "synthetic-september.csv", "sha256": "a" * 64}},
        }
        for position in self.account["positions"]:
            ticker = position["ticker"]
            self.context["stocks"][ticker] = {"name": ticker, "market": "TWSE"}
            self.context["quotes"][ticker] = {
                "trade_date": DAY, "market": "TWSE", "price_valid": True,
                "close_twd_per_share": Decimal("100"), "known_at": None,
                "tradable": False, "adjustment_status": "unresolved", "source_key": "synthetic",
            }

    def valuation(self):
        return value_account(AccountSnapshot.from_dict(self.account), self.context)

    def test_complete_demo_reports_one_billion_and_keeps_inputs_unchanged(self):
        valuation = self.valuation()
        before = copy.deepcopy((self.account, valuation))
        report = report_account(self.account, valuation, as_of=DAY)
        self.assertTrue(report["account_valid"])
        self.assertEqual(report["nav_twd"], "1000000000.00")
        self.assertEqual(report["cash_twd"], "125000000.00")
        self.assertEqual(report["estimated_available_cash_twd"], report["cash_twd"])
        self.assertIsNone(report["available_cash_twd"])
        self.assertEqual(report["reservation_status"], "not_implemented")
        self.assertEqual(report["current_positions"][0]["market_value_twd"], "35000000")
        self.assertEqual(len(report["current_positions"]), 25)
        self.assertTrue(report["demo"])
        self.assertFalse(report["reconciled"])
        self.assertFalse(report["submission_ready"])
        report["inputs"]["valuation"]["daily_prices"]["path"] = "changed"
        self.assertEqual((self.account, valuation), before)

    def test_missing_close_preserves_held_shares(self):
        ticker = self.account["positions"][0]["ticker"]
        del self.context["quotes"][ticker]
        report = report_account(self.account, self.valuation(), as_of=DAY)
        self.assertFalse(report["account_valid"])
        self.assertEqual(len(report["current_positions"]), 25)
        self.assertEqual(report["current_positions"][0]["shares"], 350000)
        self.assertIsNone(report["current_positions"][0]["market_value_twd"])
        self.assertTrue(any(row["severity"] == "BLOCK" for row in report["issues"]))

    def test_date_identity_shares_and_nav_mismatches_are_blocked(self):
        valuation = self.valuation()
        for change, as_of, code in (
            (lambda item: None, "2025-10-01", "account_report_date_mismatch"),
            (lambda item: item["account_snapshot"].update(snapshot_id="other"), DAY,
             "account_report_identity_mismatch"),
            (lambda item: item["positions"][0].update(shares=1), DAY, "account_report_shares_mismatch"),
            (lambda item: item.update(nav_difference_twd="0.01"), DAY, "account_report_nav_mismatch"),
        ):
            with self.subTest(code=code):
                changed = copy.deepcopy(valuation)
                change(changed)
                report = report_account(self.account, changed, as_of=as_of)
                self.assertFalse(report["account_valid"])
                self.assertIn(code, {issue["code"] for issue in report["issues"]})
                self.assertEqual(report["current_positions"][0]["shares"], 350000)

    def test_no_formal_available_cash_without_reservation_and_settlement(self):
        self.account.update(status="official_confirmed", demo=False, reconciled=True,
                            origin_ref="artificial-confirmation")
        report = report_account(self.account, self.valuation(), as_of=DAY)
        self.assertTrue(report["account_valid"])
        self.assertIsNone(report["available_cash_twd"])
        self.assertIsNone(report["estimated_available_cash_twd"])
        self.assertEqual(report["origin_ref"], "artificial-confirmation")
        self.assertFalse(report["submission_ready"])


if __name__ == "__main__":
    unittest.main()
