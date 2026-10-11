"""21 日窗口的三個重要離線案例；兩股、行情與日曆均為人工 fixture。

測試只核對日期窗口及資料缺口，不計算因子，不代表官方已核實行情。
"""

import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from etf_agent.coverage import PRICE_CSV_COLUMNS
from etf_agent.history_windows import check_history_windows, write_window_report
from etf_agent.universe import Stock, Universe


MONTH = "2025-09"
SESSIONS = [
    (date(2025, 9, 1) + timedelta(days=index)).isoformat()
    for index in range(30)
    if (date(2025, 9, 1) + timedelta(days=index)).weekday() < 5
    and (date(2025, 9, 1) + timedelta(days=index)).isoformat() != "2025-09-29"
]


def price_row(day, stock, source_key):
    exact = stock.market == "TWSE"
    return {
        "trade_date": day, "ticker": stock.ticker, "market": stock.market,
        "open_ktwd_per_lot": "100", "high_ktwd_per_lot": "102",
        "low_ktwd_per_lot": "99", "close_raw_ktwd_per_lot": "101",
        "return_close_ktwd_per_lot": "", "volume_lots": "10" if exact else "",
        "amount_ktwd": "1000" if exact else "", "avg_price_ktwd_per_lot": "100" if exact else "",
        "source_key": source_key, "known_at": "", "fetched_at": "2026-10-11T15:00:00+08:00",
        "data_version": "artificial-window-test-v1", "adjustment_status": "unresolved",
        "price_valid": "true", "tradable": "false", "reported_volume_lots": "10",
        "reported_amount_ktwd": "1000", "reported_avg_price_ktwd_per_lot": "100",
        "exact_volume_amount": "true" if exact else "false",
    }


class HistoryWindowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.stocks = (Stock("2330", "測試甲", "TWSE"), Stock("5274", "測試乙", "TPEX"))
        self.universe = Universe(self.stocks, "fixture-universe-v1", self.directory / "fixture-source.pdf",
                                 "a" * 64, "b" * 64)
        self.calendar = {
            "format_version": "1.0", "month": MONTH, "calendar_version": "fixture-calendar-v1",
            "markets": {
                market: {"trade_dates": list(SESSIONS), "schedule_verified": True,
                         "actual_sessions_verified": False}
                for market in ("TWSE", "TPEX")
            },
            "sources": [],
        }

    def manifest_fixture(self, *, short_stock_dates=None):
        daily_dir = self.directory / "daily" / MONTH
        daily_dir.mkdir(parents=True)
        daily_prices = []
        for day in SESSIONS:
            path = daily_dir / f"{day}_prices.csv"
            rows = [
                price_row(day, stock, f"H{index}")
                for index, stock in enumerate(self.stocks, start=1)
                if stock.ticker != "5274" or short_stock_dates is None or day in short_stock_dates
            ]
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=PRICE_CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            daily_prices.append({"trade_date": day, "row_count": len(rows),
                                 "prices_csv": path.relative_to(self.directory).as_posix()})
        manifest = self.directory / "manifest.json"
        manifest.write_text(json.dumps({
            "format_version": "1.0", "csv_format_version": "4.0", "requested_month": MONTH,
            "run_id": "artificial-window-test", "data_origin": "artificial_fixture",
            "universe_version": self.universe.universe_version,
            "universe_csv_sha256": self.universe.csv_sha256,
            "universe_source_sha256": self.universe.source_sha256,
            "daily_prices": daily_prices, "sources": [], "submission_ready": False,
        }), encoding="utf-8")
        return manifest

    def check(self, manifest, *, as_of="2025-09-30"):
        return check_history_windows(manifest, as_of=as_of, calendar=self.calendar, universe=self.universe)

    def test_complete_21_price_window_reports_each_stock_and_writes_readable_bom_csv(self):
        report = self.check(self.manifest_fixture())
        self.assertEqual(report["required_bars"], 21)
        self.assertEqual(report["expected_dates_by_market"], {"TWSE": SESSIONS, "TPEX": SESSIONS})
        self.assertEqual(report["summary"]["stock_count"], 2)
        self.assertEqual(report["summary"]["complete_stock_count"], 2)
        self.assertEqual(report["summary"]["incomplete_stock_count"], 0)
        self.assertTrue(report["input_valid"])
        self.assertEqual(report["missing_day_files"], [])
        self.assertFalse(report["submission_ready"])
        self.assertTrue(report["limitations"])
        for stock in report["stocks"]:
            self.assertEqual(stock["valid_price_count"], 21)
            self.assertEqual(stock["expected_dates"], SESSIONS)
            self.assertEqual(stock["missing_dates"], [])
            self.assertEqual(stock["invalid_price_dates"], [])
            self.assertEqual(stock["calendar_window_shortfall"], 0)
            self.assertTrue(stock["window_complete"])
            self.assertEqual(stock["status"], "complete")
        saved = write_window_report(report, self.directory / "reports")
        csv_path = Path(saved["report_csv"])
        self.assertTrue(csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        self.assertEqual({row["ticker"] for row in rows}, {"2330", "5274"})
        self.assertTrue(all(row["valid_price_count"] == "21" and row["status"] == "complete" for row in rows))
        self.assertTrue(all(row["window_complete"] == "true" and row["submission_ready"] == "false" for row in rows))
        self.assertNotIn("expected_dates", reader.fieldnames)
        self.assertTrue(all(row["missing_dates"] == "" and row["invalid_price_dates"] == "" for row in rows))
        self.assertEqual(json.loads(Path(saved["report_json"]).read_text(encoding="utf-8"))["stocks"], report["stocks"])
        self.assertTrue(Path(saved["report_md"]).is_file())

    def test_weekend_and_holiday_as_of_stop_at_prior_session_without_reading_future_prices(self):
        manifest = self.manifest_fixture()
        future_prices = self.directory / "daily" / MONTH / "2025-09-30_prices.csv"
        original_read_bytes = Path.read_bytes

        def reject_future_read(path):
            if path.resolve() == future_prices.resolve():
                raise AssertionError("窗口不可讀取 as_of 以後的行情")
            return original_read_bytes(path)

        # 9/28 是週日；fixture 日曆把 9/29 列為休市，兩者最後交易日皆是 9/26。
        with patch.object(Path, "read_bytes", new=reject_future_read):
            for as_of in ("2025-09-28", "2025-09-29"):
                with self.subTest(as_of=as_of):
                    report = self.check(manifest, as_of=as_of)
                    expected = [day for day in SESSIONS if day <= "2025-09-26"]
                    self.assertEqual(len(expected), 20)
                    self.assertEqual(report["expected_dates_by_market"], {"TWSE": expected, "TPEX": expected})
                    self.assertEqual(report["summary"]["complete_stock_count"], 0)
                    for stock in report["stocks"]:
                        self.assertEqual(stock["valid_price_count"], 20)
                        self.assertEqual(stock["calendar_window_shortfall"], 1)
                        self.assertEqual(stock["missing_dates"], [])
                        self.assertFalse(stock["window_complete"])
                        self.assertEqual(stock["status"], "calendar_window_shortfall")

    def test_missing_middle_day_and_nine_bar_stock_keep_original_expected_window(self):
        nine_dates = SESSIONS[:9]
        manifest = self.manifest_fixture(short_stock_dates=nine_dates)
        missing_day = SESSIONS[10]
        (self.directory / "daily" / MONTH / f"{missing_day}_prices.csv").unlink()
        report = self.check(manifest)
        self.assertEqual(report["expected_dates_by_market"], {"TWSE": SESSIONS, "TPEX": SESSIONS})
        self.assertEqual({entry["trade_date"] for entry in report["missing_day_files"]}, {missing_day})
        stocks = {stock["ticker"]: stock for stock in report["stocks"]}
        self.assertEqual(stocks["2330"]["valid_price_count"], 20)
        self.assertEqual(stocks["2330"]["missing_dates"], [missing_day])
        self.assertEqual(stocks["5274"]["valid_price_count"], 9)
        self.assertEqual(stocks["5274"]["missing_dates"], [day for day in SESSIONS if day not in nine_dates])
        for stock in stocks.values():
            self.assertEqual(stock["expected_dates"], SESSIONS)
            self.assertEqual(stock["calendar_window_shortfall"], 0)
            self.assertEqual(stock["status"], "missing_prices")
            self.assertFalse(stock["window_complete"])
        self.assertEqual(report["summary"]["complete_stock_count"], 0)
        self.assertEqual(report["summary"]["incomplete_stock_count"], 2)
        self.assertFalse(report["submission_ready"])


if __name__ == "__main__":
    unittest.main()
