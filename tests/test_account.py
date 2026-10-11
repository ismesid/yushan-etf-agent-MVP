"""帳戶核對的重要行為；價格與帳戶均為人工 fixture，不讀歷史快取。"""

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

from etf_agent.sub_agents.account_agent.account import (
    AccountError,
    analyze_account,
    build_weak_demo_account,
    load_account_json,
    load_history_closes,
    value_account,
    write_account_report,
    write_weak_demo_account,
)
from etf_agent.cli import main
from etf_agent.contracts import AccountSnapshot
from etf_agent.coverage import PRICE_CSV_COLUMNS
from etf_agent.universe import load_universe


ROOT = Path(__file__).resolve().parents[1]
DAY = "2025-09-30"
FETCHED_AT = "2026-10-11T12:00:00+08:00"
NAV = Decimal("1000000000.00")


class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.universe = load_universe(ROOT / "data" / "universe.csv")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def account(self, *, full=False):
        if full:
            positions = [{"ticker": stock.ticker, "shares": 350000}
                         for stock in self.universe.stocks[:25]]
            cash = "125000000.00"
        else:
            positions = [{"ticker": "2330", "shares": 1000},
                         {"ticker": "5274", "shares": 2000}]
            cash = "994998750.00"
        return AccountSnapshot.from_dict({
            "contract_version": "1.0", "snapshot_id": "artificial-account-2025-09-30",
            "as_of_trade_date": DAY, "status": "demo", "cash_twd": cash,
            "nav_twd": str(NAV), "positions": positions,
            "origin": "artificial_test_account", "reconciled": False,
            "demo": True, "origin_ref": None,
        })

    def price_context(self, account):
        stocks = {stock.ticker: {"name": stock.name, "market": stock.market}
                  for stock in self.universe.stocks}
        quotes = {}
        for number, position in enumerate(account.positions, start=1):
            close = Decimal("100") if len(account.positions) == 25 else {
                "2330": Decimal("1000.25"), "5274": Decimal("2000.50"),
            }[position.ticker]
            raw_hash = hashlib.sha256(position.ticker.encode("ascii")).hexdigest()
            quotes[position.ticker] = {
                "trade_date": DAY, "market": stocks[position.ticker]["market"],
                "close_twd_per_share": close, "price_valid": True,
                "source_key": f"H{number}", "data_version": "history-sample-v1-" + raw_hash[:12],
                "fetched_at": FETCHED_AT, "known_at": None, "raw_sha256": raw_hash,
                "adjustment_status": "unresolved", "tradable": False,
            }
        return {"as_of": DAY, "stocks": stocks, "quotes": quotes, "issues": [], "inputs": {}}

    def write_json(self, filename, value):
        path = self.directory / filename
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def historical_fixture(self, account):
        """只建人工 9/30 CSV；10/1 是不能讀取、沒有實際檔案的 sentinel。"""
        context = self.price_context(account)
        rows, sources = [], []
        for position in account.positions:
            quote, stock = context["quotes"][position.ticker], context["stocks"][position.ticker]
            close = str(quote["close_twd_per_share"])
            rows.append({
                "trade_date": DAY, "ticker": position.ticker, "market": stock["market"],
                "open_ktwd_per_lot": close, "high_ktwd_per_lot": close,
                "low_ktwd_per_lot": close, "close_raw_ktwd_per_lot": close,
                "return_close_ktwd_per_lot": "", "volume_lots": "1", "amount_ktwd": close,
                "avg_price_ktwd_per_lot": close, "source_key": quote["source_key"],
                "known_at": "", "fetched_at": FETCHED_AT, "data_version": quote["data_version"],
                "adjustment_status": "unresolved", "price_valid": "true", "tradable": "false",
                "reported_volume_lots": "1", "reported_amount_ktwd": close,
                "reported_avg_price_ktwd_per_lot": close, "exact_volume_amount": "true",
            })
            sources.append({
                "source_key": quote["source_key"], "ticker": position.ticker,
                "market": stock["market"], "status": "success", "requested_month": "2025-09",
                "raw_sha256": quote["raw_sha256"], "data_version": quote["data_version"],
                "fetched_at": FETCHED_AT,
            })
        daily_path = self.directory / "artificial-2025-09-30.csv"
        with daily_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=PRICE_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        future_path = self.directory / "future-sentinel-do-not-read.csv"
        manifest_path = self.write_json("history-manifest.json", {
            "format_version": "1.0", "csv_format_version": "4.0", "requested_month": "2025-09",
            "universe_version": self.universe.universe_version, "sources": sources,
            "daily_prices": [{"trade_date": DAY, "prices_csv": daily_path.name, "row_count": len(rows)},
                             {"trade_date": "2025-10-01", "prices_csv": future_path.name, "row_count": 999}],
        })
        metadata = {
            "analysis_format_version": "1.0", "scope": "historical_raw_price_factor_ranking",
            "as_of": DAY, "submission_ready": False, "universe_version": self.universe.universe_version,
            "input_manifest": {"path": str(manifest_path),
                               "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()},
            "daily_inputs": [
                {"trade_date": DAY, "path": str(daily_path),
                 "sha256": hashlib.sha256(daily_path.read_bytes()).hexdigest()},
                {"trade_date": "2025-10-01", "path": str(future_path), "sha256": "f" * 64},
            ],
        }
        metadata_path = self.write_json("ranking-metadata.json", metadata)
        return metadata_path, metadata, manifest_path, daily_path

    def run_cli(self, account_path, metadata_path, output):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                "account-check", "--account", str(account_path), "--ranking-metadata", str(metadata_path),
                "--as-of", DAY, "--universe", str(ROOT / "data" / "universe.csv"),
                "--output", str(output), "--json",
            ])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_normal_valuation_uses_shares_and_twd_without_promoting_demo(self):
        account = self.account()
        account_path = self.write_json("account.json", account.to_dict())
        imported = load_account_json(account_path)
        self.assertEqual(imported, account)
        context = self.price_context(imported)
        original = copy.deepcopy(context)
        report = value_account(imported, context)
        positions = {row["ticker"]: row for row in report["positions"]}
        self.assertEqual(Decimal(positions["2330"]["close_twd_per_share"]), Decimal("1000.25"))
        self.assertEqual(Decimal(positions["2330"]["market_value_twd"]), Decimal("1000250"))
        self.assertEqual(Decimal(positions["5274"]["market_value_twd"]), Decimal("4001000"))
        self.assertEqual(Decimal(positions["2330"]["weight_of_input_nav"]), Decimal("0.00100025"))
        self.assertEqual(Decimal(report["stock_value_twd"]), Decimal("5001250"))
        self.assertEqual(Decimal(report["calculated_nav_twd"]), NAV)
        self.assertEqual(Decimal(report["nav_difference_twd"]), Decimal(0))
        self.assertTrue(report["date_matches"] and report["valuation_complete"] and report["nav_matches"])
        self.assertTrue(report["valuation_ok"])
        self.assertFalse(report["initial_constraints"]["holdings_count_passed"])
        self.assertFalse(report["initial_constraints"]["passed"])
        self.assertFalse(report["submission_ready"])
        self.assertEqual(report["account_snapshot"], account.to_dict())
        self.assertTrue(report["account_snapshot"]["demo"])
        self.assertFalse(report["account_snapshot"]["reconciled"])
        self.assertEqual(context, original)

    def test_date_and_nav_mismatches_are_diagnostic_without_rewriting_account(self):
        normal = self.account()
        for changes in ({"as_of_trade_date": "2026-10-14"}, {"nav_twd": "1000000000.01"}):
            with self.subTest(changes=changes):
                raw = {**normal.to_dict(), **changes}
                account = AccountSnapshot.from_dict(raw)
                report = value_account(account, self.price_context(account))
                self.assertFalse(report["valuation_ok"])
                self.assertTrue(report["issues"])
                self.assertEqual(report["account_snapshot"], raw)
                if "as_of_trade_date" in changes:
                    self.assertFalse(report["date_matches"])
                else:
                    self.assertFalse(report["nav_matches"])
                    self.assertEqual(Decimal(report["nav_difference_twd"]), Decimal("-0.01"))

    def test_missing_or_invalid_price_preserves_position_and_withholds_full_totals(self):
        account = self.account()
        for missing_kind in ("absent", "null_close", "invalid_price"):
            with self.subTest(missing_kind=missing_kind):
                context = self.price_context(account)
                if missing_kind == "absent":
                    del context["quotes"]["5274"]
                elif missing_kind == "null_close":
                    context["quotes"]["5274"].update(close_twd_per_share=None, price_valid=False)
                else:
                    context["quotes"]["5274"]["price_valid"] = False
                report = value_account(account, context)
                positions = {row["ticker"]: row for row in report["positions"]}
                self.assertEqual(set(positions), {"2330", "5274"})
                self.assertEqual(positions["5274"]["shares"], 2000)
                self.assertIsNone(positions["5274"]["market_value_twd"])
                self.assertIsNone(positions["5274"]["weight_of_input_nav"])
                self.assertEqual(Decimal(report["known_stock_value_twd"]), Decimal("1000250"))
                for field in ("stock_value_twd", "calculated_nav_twd", "nav_difference_twd", "nav_matches"):
                    self.assertIsNone(report[field])
                self.assertFalse(report["valuation_complete"] or report["valuation_ok"])
                self.assertTrue(report["issues"])
                self.assertEqual(report["account_snapshot"], account.to_dict())

    def test_history_reads_only_as_of_date_and_checks_metadata_hash_and_source_identity(self):
        account = self.account()
        metadata_path, metadata, manifest_path, daily_path = self.historical_fixture(account)
        original_read_bytes = Path.read_bytes
        allowed_paths = {metadata_path.resolve(), manifest_path.resolve(), daily_path.resolve()}

        def permitted(path):
            self.assertIn(path.resolve(), allowed_paths, "只能讀取 ranking、manifest 與指定 9/30 CSV")
            return original_read_bytes(path)

        with patch.object(Path, "read_bytes", new=permitted):
            context = load_history_closes(metadata_path, as_of=DAY, universe=self.universe)
        self.assertEqual(set(context["quotes"]), {"2330", "5274"})
        self.assertEqual(context["quotes"]["2330"]["close_twd_per_share"], Decimal("1000.25"))
        self.assertTrue(value_account(account, context)["valuation_ok"])
        for field, wrong_value in (("scope", "wrong_scope"), ("as_of", "2025-09-29"),
                                   ("universe_version", "wrong_universe")):
            with self.subTest(metadata_field=field):
                self.write_json(metadata_path.name, {**metadata, field: wrong_value})
                with self.assertRaises(AccountError):
                    load_history_closes(metadata_path, as_of=DAY, universe=self.universe)
        bad = copy.deepcopy(metadata)
        bad["input_manifest"]["sha256"] = "0" * 64
        self.write_json(metadata_path.name, bad)
        with self.assertRaises(AccountError):
            load_history_closes(metadata_path, as_of=DAY, universe=self.universe)
        self.write_json(metadata_path.name, metadata)
        original_daily = daily_path.read_bytes()
        daily_path.write_bytes(original_daily + b"\n")
        with self.assertRaises(AccountError):
            load_history_closes(metadata_path, as_of=DAY, universe=self.universe)
        daily_path.write_bytes(original_daily)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sources"][0]["ticker"] = "9999"
        self.write_json(manifest_path.name, manifest)
        metadata["input_manifest"]["sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        self.write_json(metadata_path.name, metadata)
        with self.assertRaises(AccountError):
            load_history_closes(metadata_path, as_of=DAY, universe=self.universe)

    def test_wrong_date_row_never_overwrites_close_and_zero_calculated_nav_stays_diagnostic(self):
        account = self.account()
        metadata_path, metadata, manifest_path, daily_path = self.historical_fixture(account)
        with daily_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows.append({**rows[0], "trade_date": "2025-09-26",
                     "open_ktwd_per_lot": "99.99", "high_ktwd_per_lot": "99.99",
                     "low_ktwd_per_lot": "99.99", "close_raw_ktwd_per_lot": "99.99"})
        with daily_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=PRICE_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["daily_prices"][0]["row_count"] = len(rows)
        self.write_json(manifest_path.name, manifest)
        metadata["input_manifest"]["sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        metadata["daily_inputs"][0]["sha256"] = hashlib.sha256(daily_path.read_bytes()).hexdigest()
        self.write_json(metadata_path.name, metadata)
        context = load_history_closes(metadata_path, as_of=DAY, universe=self.universe)
        self.assertEqual(context["quotes"]["2330"]["close_twd_per_share"], Decimal("1000.25"))
        self.assertTrue(any(issue["code"] == "trade_date" and issue["severity"] == "BLOCK"
                            for issue in context["issues"]))
        self.assertFalse(value_account(account, context)["valuation_ok"])

        empty = AccountSnapshot.from_dict({**account.to_dict(), "positions": [], "cash_twd": "0"})
        report = value_account(empty, self.price_context(account))
        self.assertEqual(Decimal(report["calculated_nav_twd"]), Decimal(0))
        self.assertEqual(Decimal(report["nav_difference_twd"]), -NAV)
        self.assertIsNone(report["cash_ratio"])
        self.assertFalse(report["valuation_ok"])

    def test_valid_25_stock_reports_remain_demo_and_never_overwrite_inputs_or_prior_runs(self):
        account = self.account(full=True)
        account_path = self.write_json("account.json", account.to_dict())
        metadata_path, _, _, _ = self.historical_fixture(account)
        input_bytes = account_path.read_bytes()
        report = analyze_account(account_path, metadata_path, as_of=DAY, universe=self.universe)
        original_report = copy.deepcopy(report)
        self.assertTrue(report["valuation_ok"])
        self.assertTrue(report["initial_constraints"]["passed"])
        first = write_account_report(report, self.directory / "reports")
        prior = {key: Path(first[key]).read_bytes() for key in ("account_json", "positions_csv", "report_json")}
        second = write_account_report(report, self.directory / "reports")
        self.assertNotEqual(first["run_dir"], second["run_dir"])
        self.assertEqual({path.name for path in Path(first["run_dir"]).iterdir()},
                         {"account_snapshot.json", "positions.csv", "valuation.json"})
        self.assertEqual(account_path.read_bytes(), input_bytes)
        self.assertEqual(report, original_report)
        for key, content in prior.items():
            self.assertEqual(Path(first[key]).read_bytes(), content)
        stored = json.loads(Path(first["report_json"]).read_text(encoding="utf-8-sig"))
        self.assertEqual(Decimal(stored["input_nav_twd"]), NAV)
        self.assertFalse(stored["submission_ready"])
        self.assertFalse(stored["account_snapshot"]["reconciled"])
        with Path(first["positions_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 25)
        self.assertEqual({row["ticker"] for row in rows}, {position.ticker for position in account.positions})

    def test_cli_success_and_common_failures_return_truthful_diagnostics(self):
        account = self.account(full=True)
        account_path = self.write_json("account.json", account.to_dict())
        metadata_path, _, _, _ = self.historical_fixture(account)
        code, stdout, stderr = self.run_cli(account_path, metadata_path, self.directory / "cli_success")
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["report"]["valuation_ok"])
        self.assertTrue(payload["report"]["initial_constraints"]["passed"])
        self.assertFalse(payload["report"]["submission_ready"])
        bad = {**account.to_dict(), "nav_twd": "1000000000.01"}
        self.write_json(account_path.name, bad)
        output = self.directory / "cli_nav_mismatch"
        code, stdout, _ = self.run_cli(account_path, metadata_path, output)
        self.assertEqual(code, 2)
        payload = json.loads(stdout)
        self.assertFalse(payload["report"]["nav_matches"])
        self.assertTrue(Path(payload["outputs"]["report_json"]).is_file())
        missing_output = self.directory / "cli_missing_account"
        code, _, stderr = self.run_cli(self.directory / "missing.json", metadata_path, missing_output)
        self.assertEqual(code, 2)
        self.assertTrue(stderr)
        self.assertEqual(list(missing_output.rglob("valuation.json")), [])

    def weak_ranking_fixture(self):
        account = self.account(full=True)
        metadata_path, _, _, _ = self.historical_fixture(account)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        stocks = [*self.universe.stocks[25:30], *self.universe.stocks[:25]]
        metadata.update(ranking_version="artificial-ranking-v1", profile={
            "weights": {"mom20": "0.40", "trend20": "0.25", "vol20": "0.35"}}, rows=[
            {"ticker": stock.ticker, "market": stock.market, "rank": index,
             "score": str(Decimal(31 - index) / 100), "analysis_included": True,
             "formal_eligible": False, "values": {"mom20": "-0.1", "trend20": "-0.02", "vol20": "0.3"}}
            for index, stock in enumerate(stocks, 1)])
        self.write_json(metadata_path.name, metadata)
        return metadata_path

    def test_weak_demo_selects_bottom_25_and_saves_checkable_csv_without_overwrite(self):
        metadata_path = self.weak_ranking_fixture()
        input_body = metadata_path.read_bytes()
        report = build_weak_demo_account(metadata_path, universe=self.universe)
        account = report["account_snapshot"]
        self.assertEqual(account["nav_twd"], "1000000000.00")
        self.assertEqual(Decimal(account["cash_twd"]), Decimal("100000000"))
        self.assertIn("WEAK", account["snapshot_id"])
        self.assertEqual({row["ticker"] for row in account["positions"]},
                         {stock.ticker for stock in self.universe.stocks[:25]})
        self.assertEqual([row["rank"] for row in report["selection_rows"]], list(range(6, 31)))
        self.assertTrue(all(row["shares"] == 360000 for row in account["positions"]))
        self.assertTrue(account["demo"])
        self.assertFalse(account["reconciled"])
        self.assertTrue(report["valuation"]["valuation_ok"])
        self.assertTrue(report["valuation"]["initial_constraints"]["passed"])
        self.assertEqual(metadata_path.read_bytes(), input_body)
        first = write_weak_demo_account(report, self.directory / "weak_accounts")
        second = write_weak_demo_account(report, self.directory / "weak_accounts")
        self.assertNotEqual(first["run_dir"], second["run_dir"])
        with Path(first["positions_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 25)
        self.assertEqual([int(row["rank"]) for row in rows], list(range(6, 31)))
        self.assertEqual(rows[0]["mom20"], "-0.1")
        stored = json.loads(Path(first["construction_json"]).read_text(encoding="utf-8"))
        self.assertEqual(stored["per_stock_budget_twd"], "36000000.00")
        self.assertEqual(stored["ranking_profile"]["weights"],
                         {"mom20": "0.40", "trend20": "0.25", "vol20": "0.35"})
        for name, digest in stored["artifact_sha256"].items():
            self.assertEqual(hashlib.sha256((Path(first["run_dir"]) / name).read_bytes()).hexdigest(), digest)

    def test_weak_demo_rejects_missing_selected_close_or_future_date(self):
        metadata_path = self.weak_ranking_fixture()
        context = load_history_closes(metadata_path, as_of=DAY, universe=self.universe)
        del context["quotes"][self.universe.stocks[0].ticker]
        with patch("etf_agent.sub_agents.account_agent.account.load_history_closes", return_value=context), self.assertRaises(AccountError):
            build_weak_demo_account(metadata_path, universe=self.universe)
        with patch("etf_agent.sub_agents.account_agent.account.load_history_closes") as prices, self.assertRaises(AccountError):
            build_weak_demo_account(metadata_path, as_of="2025-10-01", universe=self.universe)
        prices.assert_not_called()


if __name__ == "__main__":
    unittest.main()
