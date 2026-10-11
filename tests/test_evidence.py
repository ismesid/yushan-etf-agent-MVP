"""決策輸入的關鍵行為；僅人工歷史日表，不讀本機行情快取。"""

import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from etf_agent.cli import main
from etf_agent.coverage import PRICE_CSV_COLUMNS
from etf_agent.evidence import EvidenceError, prepare_decision, write_decision_packet
from etf_agent.reports import write_csv_view
from etf_agent.sub_agents.data_agent import DataAgentError, prepare_data
from etf_agent.universe import load_universe


ROOT = Path(__file__).resolve().parents[1]
DAY = "2025-09-30"


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.universe = load_universe(ROOT / "data/universe.csv")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.account = self.directory / "account.json"
        self.ranking = self.directory / "ranking.json"
        self.manifest = self.directory / "history.json"
        self.daily = self.directory / "artificial-2025-09-30.csv"
        self.future = self.directory / "DO_NOT_OPEN_2025-10-01.csv"
        self.rows, sources, ranked = [], [], []
        for index, stock in enumerate(self.universe.stocks, 1):
            version = "artificial-v1-" + stock.ticker
            host = "www.twse.com.tw" if stock.market == "TWSE" else "www.tpex.org.tw"
            sources.append({"source_key": f"H{index}", "ticker": stock.ticker, "market": stock.market,
                            "status": "success", "data_version": version,
                            "fetched_at": "2026-10-11T12:00:00+08:00", "raw_sha256": "a" * 64,
                            "requested_url": f"https://{host}/artificial-test-series?stock={stock.ticker}"})
            self.rows.append({"trade_date": DAY, "ticker": stock.ticker, "market": stock.market,
                              "open_ktwd_per_lot": "100", "high_ktwd_per_lot": "100",
                              "low_ktwd_per_lot": "100", "close_raw_ktwd_per_lot": "100",
                              "return_close_ktwd_per_lot": "", "volume_lots": "1", "amount_ktwd": "100",
                              "avg_price_ktwd_per_lot": "100", "reported_volume_lots": "1",
                              "reported_amount_ktwd": "100", "reported_avg_price_ktwd_per_lot": "100",
                              "exact_volume_amount": "true", "source_key": f"H{index}",
                              "known_at": "", "fetched_at": "2026-10-11T12:00:00+08:00",
                              "data_version": version, "adjustment_status": "unresolved",
                              "price_valid": "true", "tradable": "false"})
            ranked.append({"ticker": stock.ticker, "market": stock.market, "rank": index,
                           "values": {"mom20": "0.2", "trend20": "0.1", "vol20": "0.3"},
                           "score": "0.5", "analysis_included": True, "formal_eligible": False,
                           "source_metadata": {"source_keys": [f"H{index}"], "data_versions": [version]}})
        self.manifest_value = {"format_version": "1.0", "csv_format_version": "4.0",
                               "requested_month": "2025-09", "universe_version": self.universe.universe_version,
                               "sources": sources, "daily_prices": [
                                   {"trade_date": DAY, "prices_csv": self.daily.name, "row_count": len(self.rows)},
                                   {"trade_date": "2025-10-01", "prices_csv": self.future.name, "row_count": 999}]}
        self.ranking_value = {"analysis_format_version": "1.0", "scope": "historical_raw_price_factor_ranking",
                              "price_basis": "unadjusted_raw_close", "as_of": DAY, "submission_ready": False,
                              "universe_version": self.universe.universe_version,
                              "ranking_version": "artificial-rank-v1", "feature_version": "artificial-feature-v1",
                              "calendar_version": "artificial-calendar-v1", "rows": ranked, "excluded_stocks": [],
                              "profile": {"weights": {"mom20": "0.40", "trend20": "0.25", "lowvol20": "0.35"}},
                              "summary": {"stock_count": 150, "ranked_stock_count": 150, "excluded_stock_count": 0}}
        self.account_value = {"contract_version": "1.0", "snapshot_id": "synthetic-evidence-account",
                              "as_of_trade_date": DAY, "status": "demo", "cash_twd": "125000000.00",
                              "nav_twd": "1000000000.00", "positions": [
                                  {"ticker": stock.ticker, "shares": 350000} for stock in self.universe.stocks[:25]],
                              "origin": "artificial_test", "origin_ref": None, "demo": True, "reconciled": False}
        self.write_json(self.account, self.account_value)
        self.save_lineage()

    def write_json(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def save_lineage(self):
        with self.daily.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=PRICE_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        self.manifest_value["daily_prices"][0]["row_count"] = len(self.rows)
        self.write_json(self.manifest, self.manifest_value)
        self.ranking_value["input_manifest"] = {"path": str(self.manifest),
                                                "sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest()}
        self.ranking_value["daily_inputs"] = [{"trade_date": DAY, "path": str(self.daily),
                                                "sha256": hashlib.sha256(self.daily.read_bytes()).hexdigest()},
                                               {"trade_date": "2025-10-01", "path": str(self.future), "sha256": "f" * 64}]
        self.write_json(self.ranking, self.ranking_value)

    def prepare(self):
        return prepare_decision(self.account, self.ranking, as_of=DAY, trade_date="2025-10-01", universe=self.universe)

    def test_normal_inputs_are_bounded_and_frozen_with_hashes(self):
        permitted = {self.account, self.ranking, self.manifest, self.daily}
        original = Path.read_bytes
        def guarded(path):
            self.assertIn(path, permitted)
            return original(path)
        with patch.object(Path, "read_bytes", guarded):
            packet = self.prepare()
        self.assertTrue(packet["demo_decision_ready"])
        self.assertEqual(len(packet["held_tickers"]), 25)
        self.assertEqual(len(packet["allowed_tickers"]), 150)
        self.assertEqual(len(packet["sources"]), 2)
        self.assertEqual(len(packet["observations"]), 151)
        self.assertEqual(set(packet["stock_observation_ids"]), set(packet["allowed_tickers"]))
        self.assertEqual(packet["review_report"]["recommendations"], [])
        self.assertFalse(packet["submission_ready"])
        self.assertEqual(packet["data_report"]["account_valuation"]["nav_difference_twd"], "0.00")
        before = self.account.read_bytes()
        first = write_decision_packet(packet, self.directory / "output", project_root=ROOT)
        second = write_decision_packet(packet, self.directory / "output", project_root=ROOT)
        self.assertNotEqual(first["run_dir"], second["run_dir"])
        self.assertEqual(before, self.account.read_bytes())
        saved = json.loads(Path(first["manifest_json"]).read_text(encoding="utf-8"))
        self.assertEqual(len(saved["artifact_sha256"]), 13)
        self.assertTrue(packet["account_report"]["account_valid"])
        for filename, expected in saved["artifact_sha256"].items():
            self.assertEqual(hashlib.sha256((Path(first["run_dir"]) / filename).read_bytes()).hexdigest(), expected)
        self.assertEqual(self.prepare()["packet_version_id"], packet["packet_version_id"])

    def read_csv(self, path):
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return reader.fieldnames, list(reader)

    def test_csv_candidates_preserve_146_rows_factor_units_exclusions_and_workspace_hashes(self):
        excluded_tickers = {"3718", "7750", "7769", "7828"}
        self.ranking_value["rows"] = [row for row in self.ranking_value["rows"] if row["ticker"] not in excluded_tickers]
        for index, row in enumerate(self.ranking_value["rows"], 1):
            row["rank"] = index
        exact_mom = "0.2000000000000000000000000000000000001"
        self.ranking_value["rows"][0]["values"]["mom20"] = exact_mom
        self.ranking_value["excluded_stocks"] = [
            {"ticker": ticker, "name": self.universe.lookup(ticker).name,
             "market": self.universe.lookup(ticker).market, "status": "artificial_window_shortfall",
             "valid_price_count": 20, "missing_dates": ["2025-09-01"], "invalid_price_dates": [],
             "calendar_window_shortfall": 0, "source_metadata": {"source_keys": [], "data_versions": []}}
            for ticker in sorted(excluded_tickers)]
        self.ranking_value["summary"] = {"stock_count": 150, "ranked_stock_count": 146, "excluded_stock_count": 4}
        self.save_lineage()
        packet = self.prepare()
        original = copy.deepcopy(packet)
        output = write_decision_packet(packet, self.directory / "csv_output", project_root=ROOT)
        columns, candidates = self.read_csv(output["data_candidates_csv"])
        self.assertEqual(len(candidates), 146)
        self.assertIn("vol20_annualized_ratio", columns)
        self.assertEqual(candidates[0]["mom20_ratio"], exact_mom)
        self.assertEqual(candidates[0]["score_ratio"], packet["data_report"]["rankings"][0]["score"])
        self.assertEqual(candidates[0]["source_key"], packet["data_report"]["rankings"][0]["source_key"])
        _, excluded = self.read_csv(output["data_issues_csv"])
        self.assertEqual({row["ticker"] for row in excluded}, excluded_tickers)
        self.assertTrue(all(json.loads(row["missing_dates"]) == ["2025-09-01"] for row in excluded))
        self.assertEqual(packet, original)
        run_dir = Path(output["run_dir"])
        self.assertEqual(len(list(run_dir.iterdir())), 14)
        manifest = json.loads(Path(output["manifest_json"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["artifact_sha256"]), 13)
        workspace = json.loads(Path(output["workspace_json"]).read_text(encoding="utf-8"))
        for name, expected in manifest["artifact_sha256"].items():
            self.assertEqual(hashlib.sha256((run_dir / name).read_bytes()).hexdigest(), expected)
        for key, path in output.items():
            if key.endswith("_csv"):
                self.assertTrue(Path(path).read_bytes().startswith(b"\xef\xbb\xbf"))
                self.assertEqual(workspace["files"][key], Path(path).name)

    def test_review_csv_has_no_invented_performance_or_recommendations_and_money_stays_exact(self):
        packet = self.prepare()
        output = write_decision_packet(packet, self.directory / "csv_output", project_root=ROOT)
        columns, recommendations = self.read_csv(output["review_recommendations_csv"])
        self.assertIn("recommendation_id", columns)
        self.assertEqual(recommendations, [])
        _, status = self.read_csv(output["review_status_csv"])
        self.assertEqual(status[0]["status"], "prior_run_missing")
        self.assertEqual(status[0]["performance"], "")
        self.assertEqual(status[0]["recommendation_count"], "0")
        self.assertEqual(status[0]["reason"], packet["review_report"]["reason"])
        _, summary = self.read_csv(output["account_summary_csv"])
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["cash_twd"], packet["account_report"]["cash_twd"])
        self.assertEqual(summary[0]["formal_available_cash_twd"], "")
        self.assertEqual(summary[0]["demo"], "true")
        self.assertEqual(summary[0]["account_as_of_trade_date"], packet["account_snapshot"]["as_of_trade_date"])
        exact = self.directory / "exact_decimal.csv"
        expected_hash = write_csv_view(exact, ("amount_twd", "unknown", "details"),
                                       [{"amount_twd": Decimal("100000.0100"), "unknown": None,
                                         "details": {"b": [2, None], "a": Decimal("0.10")}}])
        _, values = self.read_csv(exact)
        self.assertEqual(values[0]["amount_twd"], "100000.0100")
        self.assertEqual(values[0]["unknown"], "")
        self.assertEqual(values[0]["details"], '{"a":"0.10","b":[2,null]}')
        self.assertEqual(expected_hash, hashlib.sha256(exact.read_bytes()).hexdigest())

    def test_missing_price_csv_preserves_complete_positions_and_unknown_totals(self):
        ticker = self.account_value["positions"][0]["ticker"]
        self.rows = [row for row in self.rows if row["ticker"] != ticker]
        self.save_lineage()
        packet = self.prepare()
        output = write_decision_packet(packet, self.directory / "csv_output", project_root=ROOT)
        _, positions = self.read_csv(output["account_positions_csv"])
        self.assertEqual(len(positions), 25)
        missing = next(row for row in positions if row["ticker"] == ticker)
        self.assertEqual(missing["shares"], str(self.account_value["positions"][0]["shares"]))
        for field in ("close_twd_per_share", "market_value_twd", "weight_of_input_nav_ratio"):
            self.assertEqual(missing[field], "")
        self.assertIn("position_close_missing", json.loads(missing["issue_codes"]))
        self.assertEqual(missing["valuation_status"], "unknown")
        _, summary = self.read_csv(output["account_summary_csv"])
        self.assertEqual(summary[0]["calculated_nav_twd"], "")
        self.assertEqual(summary[0]["stock_value_twd"], "")
        self.assertEqual(summary[0]["account_valid"], "false")
        self.assertEqual(summary[0]["input_nav_twd"], packet["account_snapshot"]["nav_twd"])

    def test_date_errors_stop_before_market_loading(self):
        with patch("etf_agent.prices._reference") as loader:
            with self.assertRaises(EvidenceError):
                prepare_decision(self.account, self.ranking, as_of=DAY, trade_date=DAY, universe=self.universe)
            self.ranking_value["as_of"] = "2025-10-01"
            self.write_json(self.ranking, self.ranking_value)
            with self.assertRaises(DataAgentError):
                self.prepare()
            loader.assert_not_called()

    def test_data_agent_report_does_not_read_or_value_account(self):
        permitted = {self.ranking, self.manifest, self.daily}
        original_read = Path.read_bytes

        def guarded(path):
            self.assertIn(path, permitted)
            return original_read(path)

        with patch.object(Path, "read_bytes", guarded):
            report = prepare_data(self.ranking, as_of=DAY, universe=self.universe)
        self.assertTrue(report["demo_decision_ready"])
        for field in ("account_snapshot", "account_valuation", "held_positions"):
            self.assertNotIn(field, report)
        self.assertNotIn("account", report["inputs"])
        self.assertNotIn("current_shares", report["rankings"][0])

    def test_missing_held_close_is_preserved_and_not_ready(self):
        ticker = self.account_value["positions"][0]["ticker"]
        self.rows = [row for row in self.rows if row["ticker"] != ticker]
        self.save_lineage()
        packet = self.prepare()
        self.assertFalse(packet["demo_decision_ready"])
        self.assertIn(ticker, packet["held_tickers"])
        self.assertNotIn(ticker, packet["allowed_tickers"])
        held = next(row for row in packet["data_report"]["held_positions"] if row["ticker"] == ticker)
        self.assertEqual(held["shares"], 350000)
        self.assertIsNone(held["market_value_twd"])
        self.assertIsNone(packet["data_report"]["account_valuation"]["calculated_nav_twd"])
        self.assertEqual(packet["observations"][-1]["kind"], "held_data_missing")

    def test_source_and_factor_errors_are_rejected(self):
        original = copy.deepcopy(self.ranking_value)
        for edit in (lambda r: r["rows"][0]["source_metadata"].update(source_keys=["H999"]),
                     lambda r: r["rows"][0]["values"].update(mom20="NaN"),
                     lambda r: r["rows"][1].update(ticker=r["rows"][0]["ticker"])):
            with self.subTest(edit=edit):
                self.ranking_value = copy.deepcopy(original)
                edit(self.ranking_value)
                self.write_json(self.ranking, self.ranking_value)
                with self.assertRaises(DataAgentError):
                    self.prepare()
        self.ranking_value = copy.deepcopy(original)
        self.manifest_value["sources"][1]["requested_url"] = "https://www.twse.com.tw/different-series"
        self.save_lineage()
        with self.assertRaisesRegex(DataAgentError, "同一 endpoint"):
            self.prepare()

    def test_cli_outputs_prepared_input_and_date_failure(self):
        output = self.directory / "cli-output"
        argv = ["prepare-decision", "--account", str(self.account), "--ranking-metadata", str(self.ranking),
                "--as-of", DAY, "--trade-date", "2025-10-01", "--universe", str(ROOT / "data/universe.csv"),
                "--output", str(output), "--json"]
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main(argv), 0)
        result = json.loads(stream.getvalue())
        self.assertFalse(result["packet"]["real_agent_decision"])
        self.assertTrue(Path(result["outputs"]["packet_json"]).is_file())
        argv[argv.index("--trade-date") + 1] = DAY
        stream = io.StringIO()
        with redirect_stderr(stream):
            self.assertEqual(main(argv), 2)
        self.assertIn("決策日須晚於", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
