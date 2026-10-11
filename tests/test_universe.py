"""F05 白名單的離線驗收；異常案例只修改暫存測試資料。"""

import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from etf_agent.universe import Stock, UniverseError, load_universe
from etf_agent.cli import main


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "universe.csv"
MANIFEST_PATH = CSV_PATH.with_suffix(".manifest.json")


class UniverseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
            cls.official_rows = list(csv.reader(stream))
        cls.official_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def fixture(self, rows=None):
        """重算測試 CSV 的完整性資訊，讓異常案例確實走到內容驗證。

        測試來源 bytes 是合成內容，只用來驗證 hash 與缺檔行為；
        正式 F05 PDF 與專案 CSV 完全不修改。
        """
        rows = copy.deepcopy(self.official_rows) if rows is None else rows
        csv_path = self.directory / "universe.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerows(rows)
        csv_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        source_path = self.directory / "source.pdf"
        source_path.write_bytes(b"Synthetic source bytes for offline integrity tests.")
        manifest = copy.deepcopy(self.official_manifest)
        manifest["universe_version"] = "F05-v1-" + csv_sha256[:12]
        manifest["csv"].update(path="universe.csv", sha256=csv_sha256)
        manifest["official_source"].update(
            path="source.pdf", sha256=hashlib.sha256(source_path.read_bytes()).hexdigest()
        )
        manifest_path = csv_path.with_suffix(".manifest.json")
        self.write_manifest(manifest_path, manifest)
        return csv_path, manifest_path, source_path, manifest

    def write_manifest(self, path, manifest):
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def assert_rows_rejected(self, rows):
        csv_path, _, _, _ = self.fixture(rows)
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_official_file_has_150_unique_stocks_and_verified_source(self):
        universe = load_universe(CSV_PATH)
        self.assertEqual(len(universe.stocks), 150)
        self.assertEqual(len(universe.allowed_tickers), 150)
        self.assertEqual(len(universe.select_market("TWSE")), 100)
        self.assertEqual(len(universe.select_market("TPEX")), 50)
        self.assertIsInstance(universe.allowed_tickers, frozenset)
        self.assertEqual(universe.allowed_tickers, frozenset(stock.ticker for stock in universe.stocks))
        self.assertEqual(
            universe.source_path.resolve(),
            (ROOT / "specs" / "official" / "05_stock_universe_150_v1.pdf").resolve(),
        )
        self.assertEqual(universe.source_sha256, hashlib.sha256(universe.source_path.read_bytes()).hexdigest())
        self.assertEqual(universe.csv_sha256, hashlib.sha256(CSV_PATH.read_bytes()).hexdigest())
        self.assertEqual(universe.universe_version, "F05-v1-" + universe.csv_sha256[:12])

    def test_known_listed_and_otc_stocks_preserve_names_and_market(self):
        universe = load_universe(CSV_PATH)
        self.assertEqual(universe.lookup("2330", market="TWSE"), Stock("2330", "台積電", "TWSE"))
        self.assertEqual(universe.lookup("5274", market="TPEX"), Stock("5274", "信驊", "TPEX"))
        self.assertEqual(universe.lookup("2330"), universe.lookup("2330", market="TWSE"))

    def test_market_selection_returns_only_the_requested_market(self):
        universe = load_universe(CSV_PATH)
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                stocks = universe.select_market(market)
                self.assertIsInstance(stocks, tuple)
                self.assertTrue(all(stock.market == market for stock in stocks))
                self.assertTrue(all(universe.lookup(stock.ticker, market=market) == stock for stock in stocks))

    def test_unknown_market_selection_is_rejected(self):
        universe = load_universe(CSV_PATH)
        for market in ("OTC", "twse", "", "TPEX "):
            with self.subTest(market=market):
                with self.assertRaises(UniverseError):
                    universe.select_market(market)

    def test_lookup_rejects_a_stock_outside_the_whitelist(self):
        universe = load_universe(CSV_PATH)
        with self.assertRaises(UniverseError):
            universe.lookup("0000")

    def test_lookup_rejects_a_valid_ticker_in_the_wrong_market(self):
        universe = load_universe(CSV_PATH)
        for ticker, market in (("2330", "TPEX"), ("5274", "TWSE"), ("2330", "OTC")):
            with self.subTest(ticker=ticker, market=market):
                with self.assertRaises(UniverseError):
                    universe.lookup(ticker, market=market)

    def test_duplicate_tickers_are_rejected_even_across_markets(self):
        for same_market in (True, False):
            with self.subTest(same_market=same_market):
                rows = copy.deepcopy(self.official_rows)
                original = next(row for row in rows[1:] if row[2] == "TWSE")
                other = next(
                    row for row in rows[1:]
                    if row is not original and (row[2] == original[2]) == same_market
                )
                other[0] = original[0]
                self.assert_rows_rejected(rows)

    def test_missing_stock_is_rejected_without_synthesizing_a_replacement(self):
        rows = copy.deepcopy(self.official_rows)
        rows.pop()
        self.assert_rows_rejected(rows)

    def test_incorrect_market_counts_are_rejected_even_with_150_unique_rows(self):
        rows = copy.deepcopy(self.official_rows)
        next(row for row in rows[1:] if row[2] == "TPEX")[2] = "TWSE"
        self.assert_rows_rejected(rows)

    def test_tickers_require_four_ascii_digits_and_remain_strings(self):
        for ticker in ("233", "23300", "２３３０", "23A0", "2330 ", " 2330", ""):
            with self.subTest(ticker=ticker):
                rows = copy.deepcopy(self.official_rows)
                rows[1][0] = ticker
                self.assert_rows_rejected(rows)
        self.assertTrue(all(isinstance(stock.ticker, str) for stock in load_universe(CSV_PATH).stocks))

    def test_empty_stock_names_are_rejected(self):
        for name in ("", " ", "\t"):
            with self.subTest(name=name):
                rows = copy.deepcopy(self.official_rows)
                rows[1][1] = name
                self.assert_rows_rejected(rows)

    def test_rows_with_unknown_market_are_rejected(self):
        for market in ("OTC", "twse", "TPEX ", ""):
            with self.subTest(market=market):
                rows = copy.deepcopy(self.official_rows)
                rows[1][2] = market
                self.assert_rows_rejected(rows)

    def test_csv_requires_exactly_the_three_agreed_columns(self):
        for columns in (
            ["ticker", "name", "market", "industry"],
            ["ticker", "name"],
            ["ticker", "name", "unknown"],
            ["ticker", "ticker", "market"],
        ):
            with self.subTest(columns=columns):
                rows = copy.deepcopy(self.official_rows)
                rows[0] = columns
                self.assert_rows_rejected(rows)

    def test_rows_with_missing_or_extra_cells_are_rejected(self):
        for cells in (["2330", "台積電"], ["2330", "台積電", "TWSE", "unexpected"]):
            with self.subTest(cells=cells):
                rows = copy.deepcopy(self.official_rows)
                rows[1] = cells
                self.assert_rows_rejected(rows)

    def test_csv_changes_without_matching_manifest_are_rejected(self):
        csv_path, _, _, _ = self.fixture()
        csv_path.write_bytes(csv_path.read_bytes().replace("台積電".encode(), "測試名稱".encode()))
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_source_changes_without_matching_manifest_are_rejected(self):
        csv_path, _, source_path, _ = self.fixture()
        source_path.write_bytes(b"Changed synthetic source content.")
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_missing_source_blocks_loading(self):
        csv_path, _, source_path, _ = self.fixture()
        source_path.unlink()
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_manifest_cannot_override_the_official_market_counts(self):
        csv_path, manifest_path, _, manifest = self.fixture()
        manifest["expected_counts"] = {"TWSE": 101, "TPEX": 49}
        self.write_manifest(manifest_path, manifest)
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_version_must_identify_the_csv_content(self):
        csv_path, manifest_path, _, manifest = self.fixture()
        manifest["universe_version"] = "F05-v1-000000000000"
        self.write_manifest(manifest_path, manifest)
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_manifest_csv_path_must_identify_the_requested_file(self):
        csv_path, manifest_path, _, manifest = self.fixture()
        other_path = self.directory / "other.csv"
        other_path.write_bytes(csv_path.read_bytes())
        manifest["csv"]["path"] = "other.csv"
        self.write_manifest(manifest_path, manifest)
        with self.assertRaises(UniverseError):
            load_universe(csv_path)

    def test_explicit_manifest_path_supports_an_independent_filename(self):
        csv_path, manifest_path, _, _ = self.fixture()
        renamed_manifest = self.directory / "metadata.json"
        manifest_path.rename(renamed_manifest)
        universe = load_universe(csv_path, manifest_path=renamed_manifest)
        self.assertEqual(len(universe.stocks), 150)

    def test_missing_or_invalid_manifest_is_reported_as_a_universe_error(self):
        for content in (None, "{", "[]"):
            with self.subTest(content=content):
                csv_path, manifest_path, _, _ = self.fixture()
                if content is None:
                    manifest_path.unlink()
                else:
                    manifest_path.write_text(content, encoding="utf-8")
                with self.assertRaises(UniverseError):
                    load_universe(csv_path)

    def test_cli_json_reports_verified_official_counts_and_examples(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["universe-check", "--universe", str(CSV_PATH), "--json"])
        summary = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["row_count"], 150)
        self.assertEqual(summary["counts"], {"TWSE": 100, "TPEX": 50})
        self.assertEqual(summary["examples"], [
            {"ticker": "2330", "name": "台積電", "market": "TWSE"},
            {"ticker": "5274", "name": "信驊", "market": "TPEX"},
        ])
        self.assertFalse(summary["historical_universe_verified"])

    def test_cli_missing_input_returns_error_code_and_readable_message(self):
        error = io.StringIO()
        with redirect_stderr(error):
            exit_code = main(["universe-check", "--universe", str(self.directory / "missing.csv")])
        self.assertEqual(exit_code, 2)
        self.assertIn("白名單", error.getvalue())

    def test_cli_invalid_market_is_blocked_even_with_matching_csv_hash(self):
        rows = copy.deepcopy(self.official_rows)
        rows[1][2] = "OTC"
        csv_path, _, _, _ = self.fixture(rows)
        error = io.StringIO()
        with redirect_stderr(error):
            exit_code = main(["universe-check", "--universe", str(csv_path)])
        self.assertEqual(exit_code, 2)
        self.assertIn("市場", error.getvalue())


if __name__ == "__main__":
    unittest.main()
