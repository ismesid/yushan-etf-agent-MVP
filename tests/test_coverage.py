"""每日 CSV 覆蓋報告：固定測試列，不依賴本機歷史下載快取。

兩筆測試列採用先前歷史樣本的收盤／量值；其餘欄位為離線測試設定。
完整 150 檔的列只是結構 fixture，不能當作真實行情或正式策略輸入。
"""

import copy
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path

from etf_agent.coverage import (
    PRICE_CSV_COLUMNS,
    PriceCoverageError,
    check_daily_prices,
    write_coverage_report,
)
from etf_agent.cli import main
from etf_agent.universe import load_universe


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COLUMNS = (
    "trade_date", "ticker", "market", "open_ktwd_per_lot", "high_ktwd_per_lot",
    "low_ktwd_per_lot", "close_raw_ktwd_per_lot", "return_close_ktwd_per_lot",
    "volume_lots", "amount_ktwd", "avg_price_ktwd_per_lot", "source_key",
    "known_at", "fetched_at", "data_version", "adjustment_status", "price_valid",
    "tradable", "reported_volume_lots", "reported_amount_ktwd",
    "reported_avg_price_ktwd_per_lot", "exact_volume_amount",
)
DAY = "2025-09-01"


def sample_rows():
    common = {
        "trade_date": DAY,
        "return_close_ktwd_per_lot": "",
        "known_at": "",
        "fetched_at": "2026-10-11T12:25:49+08:00",
        "data_version": "coverage-offline-test-v1",
        "adjustment_status": "unresolved",
        "price_valid": "true",
        "tradable": "false",
    }
    return [
        {
            **common,
            "ticker": "2330", "market": "TWSE",
            "open_ktwd_per_lot": "1150", "high_ktwd_per_lot": "1170",
            "low_ktwd_per_lot": "1140", "close_raw_ktwd_per_lot": "1165",
            "volume_lots": "23022.319", "amount_ktwd": "26647241.918",
            "avg_price_ktwd_per_lot": "1157.45255367", "source_key": "H01",
            "reported_volume_lots": "23022.319", "reported_amount_ktwd": "26647241.918",
            "reported_avg_price_ktwd_per_lot": "1157.45255367",
            "exact_volume_amount": "true",
        },
        {
            **common,
            "ticker": "5274", "market": "TPEX",
            "open_ktwd_per_lot": "5000", "high_ktwd_per_lot": "5050",
            "low_ktwd_per_lot": "4950", "close_raw_ktwd_per_lot": "5015",
            "volume_lots": "", "amount_ktwd": "", "avg_price_ktwd_per_lot": "",
            "source_key": "H02", "reported_volume_lots": "356",
            "reported_amount_ktwd": "1785269",
            "reported_avg_price_ktwd_per_lot": "5014.80056180",
            "exact_volume_amount": "false",
        },
    ]


class PriceCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.universe = load_universe(ROOT / "data" / "universe.csv")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def csv_fixture(self, rows=None, *, columns=EXPECTED_COLUMNS, filename="daily.csv"):
        path = self.directory / filename
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(sample_rows() if rows is None else rows)
        return path

    def report(self, rows=None, *, requested_date=DAY):
        return check_daily_prices(
            self.csv_fixture(rows), trade_date=requested_date, universe=self.universe,
        )

    def assert_row_errors(self, report, *, ticker):
        self.assertFalse(report["input_valid"])
        matching = [item for item in report["errors"] if item["ticker"] == ticker]
        self.assertTrue(matching)
        for item in matching:
            self.assertIsInstance(item["row"], int)
            self.assertGreaterEqual(item["row"], 2)
            self.assertTrue(item["code"])
            self.assertTrue(item["message"])

    def test_csv_columns_match_existing_version_4_contract(self):
        self.assertEqual(PRICE_CSV_COLUMNS, EXPECTED_COLUMNS)

    def test_two_symbol_sample_reports_148_missing_without_promoting_to_formal(self):
        report = self.report()
        self.assertTrue(report["input_valid"])
        self.assertEqual(report["trade_date"], DAY)
        self.assertEqual(report["row_count"], 2)
        self.assertEqual(report["present_count"], 2)
        self.assertEqual(report["valid_price_count"], 2)
        self.assertEqual(report["tradable_flag_count"], 0)
        self.assertEqual(report["present_tickers"], ["2330", "5274"])
        self.assertEqual(report["missing_count"], 148)
        self.assertEqual(len(report["missing_stocks"]), 148)
        self.assertEqual(len(set(report["missing_tickers"])), 148)
        self.assertEqual(
            set(report["missing_tickers"]), self.universe.allowed_tickers - {"2330", "5274"},
        )
        self.assertEqual(
            {item["ticker"] for item in report["missing_stocks"]},
            set(report["missing_tickers"]),
        )
        self.assertFalse(report["coverage_complete"])
        self.assertFalse(report["submission_ready"])
        self.assertAlmostEqual(Decimal(report["coverage_percent"]), Decimal("1.33"), places=2)
        self.assertEqual(report["by_market"], {
            "TWSE": {"expected_count": 100, "present_count": 1,
                     "valid_price_count": 1, "missing_count": 99},
            "TPEX": {"expected_count": 50, "present_count": 1,
                     "valid_price_count": 1, "missing_count": 49},
        })

    def test_reported_only_tpex_quantities_are_valid_and_never_rejected_for_precision(self):
        report = self.report([sample_rows()[1]])
        self.assertTrue(report["input_valid"])
        self.assertEqual(report["present_tickers"], ["5274"])
        self.assertEqual(report["valid_price_count"], 1)
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["warnings"])

    def test_missing_known_at_and_unresolved_adjustments_are_warnings(self):
        report = self.report()
        self.assertTrue(report["input_valid"])
        self.assertEqual(report["errors"], [])
        for warning in report["warnings"]:
            self.assertTrue(warning["code"])
            self.assertTrue(warning["message"])
            self.assertIsInstance(warning["tickers"], list)

    def test_same_day_duplicate_excludes_every_copy_instead_of_keeping_first(self):
        rows = sample_rows()
        rows.append(copy.deepcopy(rows[0]))
        report = self.report(rows)
        self.assertEqual(report["row_count"], 3)
        self.assertEqual(report["duplicate_tickers"], ["2330"])
        self.assertEqual(report["present_tickers"], ["5274"])
        self.assertEqual(report["present_count"], 1)
        self.assertEqual(report["missing_count"], 149)
        self.assertIn("2330", report["missing_tickers"])
        self.assert_row_errors(report, ticker="2330")

    def test_wrong_market_does_not_count_as_a_present_symbol(self):
        rows = sample_rows()
        rows[0]["market"] = "TPEX"
        report = self.report(rows)
        self.assertEqual(report["present_tickers"], ["5274"])
        self.assertEqual(report["by_market"]["TWSE"]["present_count"], 0)
        self.assertEqual(report["by_market"]["TPEX"]["present_count"], 1)
        self.assert_row_errors(report, ticker="2330")

    def test_wrong_date_does_not_count_toward_requested_daily_coverage(self):
        rows = sample_rows()
        rows[0]["trade_date"] = "2025-09-02"
        report = self.report(rows)
        self.assertEqual(report["present_tickers"], ["5274"])
        self.assert_row_errors(report, ticker="2330")

    def test_unlisted_symbol_is_reported_and_does_not_inflate_coverage(self):
        rows = sample_rows()
        extra = {**rows[0], "ticker": "0000"}
        report = self.report([*rows, extra])
        self.assertEqual(report["present_count"], 2)
        self.assertEqual(report["missing_count"], 148)
        self.assertEqual(report["unexpected_tickers"], ["0000"])
        self.assert_row_errors(report, ticker="0000")

    def test_missing_close_keeps_identity_coverage_but_has_no_valid_price(self):
        row = sample_rows()[0]
        row["close_raw_ktwd_per_lot"] = ""
        row["price_valid"] = "false"
        report = self.report([row])
        self.assertEqual(report["present_tickers"], ["2330"])
        self.assertEqual(report["present_count"], 1)
        self.assertEqual(report["valid_price_count"], 0)

    def test_price_valid_false_is_not_a_valid_price_even_with_close(self):
        row = sample_rows()[0]
        row["price_valid"] = "false"
        report = self.report([row])
        self.assertEqual(report["present_count"], 1)
        self.assertEqual(report["valid_price_count"], 0)

    def test_nonfinite_prices_and_amounts_are_row_errors(self):
        for column, value in (
            ("close_raw_ktwd_per_lot", "NaN"),
            ("amount_ktwd", "Infinity"),
            ("reported_volume_lots", "-Infinity"),
        ):
            with self.subTest(column=column, value=value):
                row = sample_rows()[0]
                row[column] = value
                report = self.report([row])
                self.assert_row_errors(report, ticker="2330")
                if column == "close_raw_ktwd_per_lot":
                    self.assertEqual(report["valid_price_count"], 0)

    def test_negative_exact_and_reported_quantities_are_row_errors(self):
        for column in ("volume_lots", "amount_ktwd", "reported_volume_lots", "reported_amount_ktwd"):
            with self.subTest(column=column):
                row = sample_rows()[0]
                row[column] = "-1"
                self.assert_row_errors(self.report([row]), ticker="2330")

    def test_volume_amount_pairs_cannot_be_half_missing_but_both_unknown_are_allowed(self):
        for prefix in ("", "reported_"):
            for volume, amount in (("1", ""), ("", "1"), ("", "")):
                with self.subTest(prefix=prefix, volume=volume, amount=amount):
                    row = sample_rows()[0]
                    row[prefix + "volume_lots"] = volume
                    row[prefix + "amount_ktwd"] = amount
                    row[prefix + "avg_price_ktwd_per_lot"] = ""
                    report = self.report([row])
                    if volume == amount == "":
                        self.assertTrue(report["input_valid"])
                        self.assertEqual(report["present_count"], 1)
                    else:
                        self.assert_row_errors(report, ticker="2330")

    def test_duplicate_with_extra_column_still_excludes_the_whole_symbol_group(self):
        rows = sample_rows()
        path = self.directory / "bad_duplicate.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(EXPECTED_COLUMNS)
            for row in rows:
                writer.writerow([row[column] for column in EXPECTED_COLUMNS])
            writer.writerow([rows[0][column] for column in EXPECTED_COLUMNS] + ["extra"])
        report = check_daily_prices(path, trade_date=DAY, universe=self.universe)
        self.assertEqual(report["row_count"], 3)
        self.assertEqual(report["duplicate_tickers"], ["2330"])
        self.assertEqual(report["present_tickers"], ["5274"])
        self.assertEqual(report["missing_count"], 149)
        self.assert_row_errors(report, ticker="2330")

    def test_zero_quantities_are_allowed_but_zero_price_is_invalid(self):
        row = sample_rows()[0]
        for column in ("volume_lots", "amount_ktwd", "reported_volume_lots", "reported_amount_ktwd"):
            row[column] = "0"
        row["avg_price_ktwd_per_lot"] = ""
        row["reported_avg_price_ktwd_per_lot"] = ""
        self.assertTrue(self.report([row])["input_valid"])
        row["close_raw_ktwd_per_lot"] = "0"
        self.assert_row_errors(self.report([row]), ticker="2330")

    def test_ohlc_out_of_range_is_rejected(self):
        row = sample_rows()[0]
        row["high_ktwd_per_lot"] = "1150"
        report = self.report([row])
        self.assert_row_errors(report, ticker="2330")
        self.assertEqual(report["valid_price_count"], 0)

    def test_boolean_fields_accept_only_literal_true_or_false(self):
        for column in ("price_valid", "tradable", "exact_volume_amount"):
            with self.subTest(column=column):
                row = sample_rows()[0]
                row[column] = "1"
                self.assert_row_errors(self.report([row]), ticker="2330")

    def test_requested_date_accepts_date_object_and_rejects_invalid_calendar_date(self):
        self.assertEqual(self.report(requested_date=date(2025, 9, 1))["trade_date"], DAY)
        with self.assertRaises(PriceCoverageError):
            self.report(requested_date="2025-02-29")

    def test_invalid_row_date_is_reported_without_crashing(self):
        row = sample_rows()[0]
        row["trade_date"] = "2025-02-29"
        report = self.report([row])
        self.assertEqual(report["present_count"], 0)
        self.assert_row_errors(report, ticker="2330")

    def test_missing_file_is_a_readable_domain_error(self):
        with self.assertRaises(PriceCoverageError):
            check_daily_prices(
                self.directory / "missing.csv", trade_date=DAY, universe=self.universe,
            )

    def test_wrong_header_cannot_be_silently_treated_as_current_price_csv(self):
        path = self.csv_fixture(columns=EXPECTED_COLUMNS[:-1])
        with self.assertRaises(PriceCoverageError):
            check_daily_prices(path, trade_date=DAY, universe=self.universe)

    def test_bad_encoding_is_a_domain_error(self):
        path = self.directory / "invalid_utf8.csv"
        path.write_bytes(b"\xff\xfe\xfd")
        with self.assertRaises(PriceCoverageError):
            check_daily_prices(path, trade_date=DAY, universe=self.universe)

    def test_empty_daily_file_has_all_150_missing_and_never_fabricates_rows(self):
        report = self.report([])
        self.assertTrue(report["input_valid"])
        self.assertEqual(report["row_count"], 0)
        self.assertEqual(report["present_count"], 0)
        self.assertEqual(report["missing_count"], 150)
        self.assertFalse(report["coverage_complete"])
        self.assertEqual(Decimal(report["coverage_percent"]), Decimal(0))

    def test_full_fixture_coverage_still_does_not_mean_formal_submission_ready(self):
        rows = []
        template = sample_rows()[0]
        for stock in self.universe.stocks:
            rows.append({**template, "ticker": stock.ticker, "market": stock.market})
        report = self.report(rows)
        self.assertTrue(report["input_valid"])
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(report["present_count"], 150)
        self.assertEqual(report["valid_price_count"], 150)
        self.assertEqual(report["missing_count"], 0)
        self.assertEqual(report["missing_stocks"], [])
        self.assertFalse(report["submission_ready"])

    def test_report_outputs_are_readable_and_each_run_is_separate(self):
        report = self.report()
        original = copy.deepcopy(report)
        output = self.directory / "reports"
        first = write_coverage_report(report, output)
        first_bytes = Path(first["report_json"]).read_bytes()
        second = write_coverage_report(report, output)
        self.assertNotEqual(Path(first["run_dir"]), Path(second["run_dir"]))
        self.assertEqual(Path(first["report_json"]).read_bytes(), first_bytes)
        self.assertEqual(report, original)
        stored = json.loads(first_bytes.decode("utf-8-sig"))
        self.assertEqual(stored["present_count"], 2)
        self.assertEqual(stored["missing_count"], 148)
        self.assertFalse(stored["submission_ready"])
        self.assertEqual({path.name for path in Path(first["run_dir"]).iterdir()}, {"coverage.json", "missing_stocks.csv"})
        with Path(first["missing_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, ["ticker", "name", "market"])
            missing = list(reader)
        self.assertEqual(missing, report["missing_stocks"])
        self.assertEqual(len(missing), 148)

    def run_cli(self, path, output):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([
                "prices-check", "--prices", str(path), "--date", DAY,
                "--universe", str(ROOT / "data" / "universe.csv"),
                "--output", str(output), "--json",
            ])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_cli_partial_coverage_returns_zero_and_saves_truthful_report(self):
        output = self.directory / "cli_reports"
        exit_code, stdout, _ = self.run_cli(self.csv_fixture(), output)
        self.assertEqual(exit_code, 0)
        self.assertIsInstance(json.loads(stdout), dict)
        saved = list(output.rglob("coverage.json"))
        self.assertEqual(len(saved), 1)
        report = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assertTrue(report["input_valid"])
        self.assertEqual(report["present_count"], 2)
        self.assertEqual(report["missing_count"], 148)
        self.assertFalse(report["coverage_complete"])
        self.assertFalse(report["submission_ready"])

    def test_cli_invalid_row_returns_two_and_preserves_diagnostics(self):
        rows = sample_rows()
        rows[0]["market"] = "TPEX"
        output = self.directory / "cli_reports"
        exit_code, stdout, _ = self.run_cli(self.csv_fixture(rows), output)
        self.assertEqual(exit_code, 2)
        self.assertIsInstance(json.loads(stdout), dict)
        saved = list(output.rglob("coverage.json"))
        self.assertEqual(len(saved), 1)
        report = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assert_row_errors(report, ticker="2330")
        self.assertEqual(report["present_tickers"], ["5274"])
        self.assertFalse(saved[0].with_name("coverage.md").exists())
        self.assertTrue(saved[0].with_name("missing_stocks.csv").is_file())

    def test_cli_invalid_header_returns_two_without_writing_a_report_version(self):
        output = self.directory / "cli_reports"
        path = self.csv_fixture(columns=EXPECTED_COLUMNS[:-1])
        exit_code, _, stderr = self.run_cli(path, output)
        self.assertEqual(exit_code, 2)
        self.assertTrue(stderr)
        self.assertEqual(list(output.rglob("coverage.json")), [])


if __name__ == "__main__":
    unittest.main()
