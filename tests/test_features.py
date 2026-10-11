"""Three important raw-price analysis cases; prices and universe are artificial fixtures."""

import csv
import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from etf_agent.coverage import PRICE_CSV_COLUMNS
from etf_agent.features import (
    FeatureAnalysisError,
    analyze_history_features,
    calculate_price_features,
    write_feature_analysis,
)
from etf_agent.history_windows import check_history_windows, write_window_report
from etf_agent.universe import Stock, Universe


MONTH = "2025-09"
SESSIONS = [
    (date(2025, 9, 1) + timedelta(days=index)).isoformat()
    for index in range(30)
    if (date(2025, 9, 1) + timedelta(days=index)).weekday() < 5
    and (date(2025, 9, 1) + timedelta(days=index)).isoformat() != "2025-09-29"
]


class FeatureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def window_fixture(self):
        """Use the existing window checker to create a complete and a nine-bar stock."""
        stocks = (Stock("2330", "Fixture A", "TWSE"), Stock("5274", "Fixture B", "TPEX"))
        universe = Universe(stocks, "feature-fixture-universe-v1", self.directory / "source.pdf",
                            "a" * 64, "b" * 64)
        calendar = {
            "format_version": "1.0", "month": MONTH, "calendar_version": "feature-fixture-calendar-v1",
            "markets": {
                market: {"trade_dates": SESSIONS, "schedule_verified": True,
                         "actual_sessions_verified": False}
                for market in ("TWSE", "TPEX")
            },
            "sources": [],
        }
        daily_dir = self.directory / "daily" / MONTH
        daily_dir.mkdir(parents=True)
        daily_prices = []
        for index, day in enumerate(SESSIONS):
            path = daily_dir / f"{day}_prices.csv"
            close = "100" if index == 0 else "110"
            rows = []
            for stock in stocks:
                if stock.ticker == "5274" and index >= 9:
                    continue
                exact = stock.market == "TWSE"
                rows.append({
                    "trade_date": day, "ticker": stock.ticker, "market": stock.market,
                    "open_ktwd_per_lot": close, "high_ktwd_per_lot": close,
                    "low_ktwd_per_lot": close, "close_raw_ktwd_per_lot": close,
                    "return_close_ktwd_per_lot": "", "volume_lots": "10" if exact else "",
                    "amount_ktwd": str(Decimal(close) * 10) if exact else "",
                    "avg_price_ktwd_per_lot": close if exact else "",
                    "source_key": f"FEATURE-{stock.ticker}", "known_at": "",
                    "fetched_at": "2026-10-11T15:00:00+08:00", "data_version": "artificial-feature-test-v1",
                    "adjustment_status": "unresolved", "price_valid": "true", "tradable": "false",
                    "reported_volume_lots": "10", "reported_amount_ktwd": str(Decimal(close) * 10),
                    "reported_avg_price_ktwd_per_lot": close,
                    "exact_volume_amount": "true" if exact else "false",
                })
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=PRICE_CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            daily_prices.append({"trade_date": day, "row_count": len(rows),
                                 "prices_csv": path.relative_to(self.directory).as_posix()})
        manifest = self.directory / "manifest.json"
        manifest.write_text(json.dumps({
            "format_version": "1.0", "csv_format_version": "4.0", "requested_month": MONTH,
            "run_id": "artificial-feature-test", "data_origin": "artificial_fixture",
            "universe_version": universe.universe_version, "universe_csv_sha256": universe.csv_sha256,
            "universe_source_sha256": universe.source_sha256, "daily_prices": daily_prices,
            "sources": [], "submission_ready": False,
        }), encoding="utf-8")
        report = check_history_windows(manifest, as_of="2025-09-30", calendar=calendar, universe=universe)
        self.assertTrue(report["input_valid"])
        saved = write_window_report(report, self.directory / "windows")
        return Path(saved["report_json"]), manifest, daily_dir

    def test_hand_calculated_formulas_and_constant_prices(self):
        values = calculate_price_features([Decimal("100")] + [Decimal("110")] * 20)
        self.assertEqual(values["mom20"], Decimal("0.1"))
        self.assertEqual(values["trend20"], Decimal("0"))
        # Daily returns are 0.1, then nineteen zeros. Sample variance = 0.0005.
        self.assertAlmostEqual(float(values["vol20"]), 0.3549647869859769, places=14)
        flat = calculate_price_features([Decimal("100")] * 21)
        self.assertEqual(flat, {"mom20": Decimal("0"), "trend20": Decimal("0"), "vol20": Decimal("0")})

    def test_complete_stock_only_daily_inputs_percent_csv_and_repeatable_new_runs(self):
        window_path, manifest, daily_dir = self.window_fixture()
        future = daily_dir / "2025-10-01_prices.csv"
        monthly = self.directory / "monthly.csv"
        future.write_text("future data must not be read", encoding="utf-8")
        monthly.write_text("monthly duplicate must not be read", encoding="utf-8")
        forbidden = {future.resolve(), monthly.resolve()}
        original_read_bytes, original_open = Path.read_bytes, Path.open

        def permitted_read_bytes(path):
            self.assertNotIn(path.resolve(), forbidden)
            return original_read_bytes(path)

        def permitted_open(path, *args, **kwargs):
            self.assertNotIn(path.resolve(), forbidden)
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "read_bytes", new=permitted_read_bytes), patch.object(Path, "open", new=permitted_open):
            report = analyze_history_features(window_path)
            repeated = analyze_history_features(window_path)
        self.assertEqual(report["scope"], "historical_raw_price_feature_analysis")
        self.assertEqual(report["as_of"], "2025-09-30")
        self.assertEqual(report["summary"], {
            "stock_count": 2, "analyzed_stock_count": 1, "excluded_stock_count": 1,
        })
        self.assertEqual([row["ticker"] for row in report["rows"]], ["2330"])
        row = report["rows"][0]
        self.assertEqual((row["price_count"], row["return_count"]), (21, 20))
        self.assertEqual(Decimal(row["values"]["mom20"]), Decimal("0.1"))
        self.assertEqual(Decimal(row["values"]["trend20"]), Decimal("0"))
        self.assertEqual(report["excluded_stocks"][0]["ticker"], "5274")
        self.assertEqual(report["excluded_stocks"][0]["status"], "missing_prices")
        self.assertEqual(report["excluded_stocks"][0]["missing_dates"], SESSIONS[9:])
        self.assertEqual([item["trade_date"] for item in report["daily_inputs"]], SESSIONS)
        self.assertEqual(report["feature_version"], repeated["feature_version"])
        self.assertEqual(report["rows"], repeated["rows"])
        self.assertFalse(report["submission_ready"])
        self.assertTrue(report["limitations"])

        saved = write_feature_analysis(report, self.directory / "features")
        csv_path = Path(saved["features_csv"])
        before = csv_path.read_bytes()
        self.assertTrue(before.startswith(b"\xef\xbb\xbf"))
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mom20_pct"], "10.000000")
        self.assertEqual(rows[0]["trend20_pct"], "0.000000")
        self.assertEqual(rows[0]["vol20_annual_pct"], "35.496479")
        metadata = json.loads(Path(saved["metadata_json"]).read_text(encoding="utf-8"))
        self.assertFalse(metadata["submission_ready"])
        self.assertEqual(metadata["feature_version"], report["feature_version"])
        self.assertEqual(metadata["input_window_report"]["sha256"], hashlib.sha256(window_path.read_bytes()).hexdigest())
        self.assertEqual(metadata["input_manifest"]["sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
        self.assertEqual(len(metadata["daily_inputs"]), 21)
        self.assertTrue(metadata["formulas"])
        self.assertTrue(metadata["units"])
        self.assertTrue(Path(saved["analysis_md"]).is_file())
        newer = write_feature_analysis(repeated, self.directory / "features")
        self.assertNotEqual(saved["run_dir"], newer["run_dir"])
        self.assertEqual(csv_path.read_bytes(), before)
        self.assertEqual(Path(newer["features_csv"]).read_bytes(), before)

    def test_modified_daily_file_is_rejected_instead_of_using_stale_window_evidence(self):
        window_path, _, daily_dir = self.window_fixture()
        day_file = daily_dir / f"{SESSIONS[0]}_prices.csv"
        day_file.write_bytes(day_file.read_bytes().replace(b",100,100,100,100,", b",101,101,101,101,"))
        with self.assertRaises(FeatureAnalysisError):
            analyze_history_features(window_path)


if __name__ == "__main__":
    unittest.main()
