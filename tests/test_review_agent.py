"""前日檢視缺資料與常見錯誤；只用合成報告，不讀行情。"""

import copy
import unittest

from etf_agent.sub_agents.test_agent import (
    ReviewReportError,
    review_previous_day,
    validate_review_report,
)


DAY = "2025-09-30"


class ReviewAgentTests(unittest.TestCase):
    def test_first_day_reports_missing_prior_run_without_fake_results(self):
        report = review_previous_day(as_of=DAY)
        self.assertEqual(report["status"], "prior_run_missing")
        self.assertEqual(report["as_of"], DAY)
        self.assertEqual(report["data_through"], DAY)
        self.assertEqual(report["recommendations"], [])
        self.assertIsNone(report["performance"])
        self.assertTrue(report["demo"])
        self.assertFalse(report["submission_ready"])
        self.assertIn("實際成交", report["reason"])
        self.assertIsNone(validate_review_report(report, as_of=DAY))

    def test_dates_must_match_cutoff_and_be_valid_iso_dates(self):
        report = review_previous_day(as_of=DAY)
        for field, value in (("as_of", "2025-10-01"),
                             ("data_through", "2025-10-01"),
                             ("data_through", "2025-09-29"),
                             ("as_of", "2025-09-31")):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ReviewReportError):
                    validate_review_report({**report, field: value}, as_of=DAY)
        with self.assertRaises(ReviewReportError):
            review_previous_day(as_of="20250930")

    def test_fabricated_performance_and_recommendations_are_rejected(self):
        report = review_previous_day(as_of=DAY)
        for changes in ({"performance": {"return_pct": 0.1}},
                        {"performance": 0},
                        {"recommendations": [{"ticker": "2330", "action": "BUY"}]},
                        {"recommendations": ()},
                        {"status": "review_completed"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ReviewReportError):
                    validate_review_report({**report, **changes}, as_of=DAY)

    def test_unknown_schema_and_formal_flags_are_rejected(self):
        report = review_previous_day(as_of=DAY)
        for changes in ({"report_version": "2.0"}, {"unknown": "field"},
                        {"role": "data_agent"}, {"scope": "performance"},
                        {"demo": False}, {"demo": 1},
                        {"submission_ready": True}, {"reason": ""}):
            with self.subTest(changes=changes):
                with self.assertRaises(ReviewReportError):
                    validate_review_report({**report, **changes}, as_of=DAY)
        missing = copy.deepcopy(report)
        del missing["performance"]
        with self.assertRaises(ReviewReportError):
            validate_review_report(missing, as_of=DAY)


if __name__ == "__main__":
    unittest.main()
