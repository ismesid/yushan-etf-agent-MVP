"""Important ranking cases; input values and stock names are artificial fixtures."""

import csv
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from etf_agent.ranking import (
    RANKING_CSV_COLUMNS,
    RankingError,
    analyze_history_rankings,
    calculate_factor_rankings,
    load_ranking_profile,
    write_ranking_analysis,
)


WEIGHTS = {"mom20": "0.40", "trend20": "0.25", "lowvol20": "0.35"}


def stock(ticker, mom, trend, vol):
    return {"ticker": ticker, "name": f"Fixture {ticker}", "market": "TWSE",
            "values": {"mom20": mom, "trend20": trend, "vol20": vol},
            "source_metadata": {"source_keys": [f"FIXTURE-{ticker}"], "known_at_missing_dates": ["2025-09-30"]}}


class RankingTests(unittest.TestCase):
    def test_average_ties_hand_score_and_single_volatility_reversal(self):
        rows = [stock("0003", "0.1", "0.2", "0.3"), stock("0001", "0.1", "0.4", "0.1"),
                stock("0002", "0.2", "0.3", "0.2")]
        ranked = calculate_factor_rankings(rows, WEIGHTS)
        self.assertEqual([row["ticker"] for row in ranked], ["0001", "0002", "0003"])
        first, second, third = ranked
        self.assertEqual(first["rank_scores"], {"mom20": Decimal("0.25"), "trend20": Decimal(1), "lowvol20": Decimal(1)})
        self.assertEqual(first["contributions"], {"mom20": Decimal("0.10"), "trend20": Decimal("0.25"), "lowvol20": Decimal("0.35")})
        self.assertEqual([row["score"] for row in ranked], [Decimal("0.70"), Decimal("0.70"), Decimal("0.10")])
        self.assertEqual([row["rank"] for row in ranked], [1, 2, 3])
        self.assertEqual(second["rank_scores"]["lowvol20"], Decimal("0.5"))
        self.assertEqual(third["rank_scores"]["lowvol20"], Decimal(0))
        self.assertEqual(rows[0]["values"]["vol20"], "0.3")  # Pure function does not modify its input.
        equal = calculate_factor_rankings([stock("0002", "0", "0", "0"), stock("0001", "0", "0", "0")], WEIGHTS)
        self.assertEqual([row["ticker"] for row in equal], ["0001", "0002"])
        self.assertTrue(all(row["score"] == Decimal("0.5") for row in equal))
        self.assertEqual(equal[0]["analysis_warnings"], ["zero_volatility_requires_review"])
        single = calculate_factor_rankings([rows[0]], WEIGHTS)
        self.assertEqual(single[0]["score"], Decimal("0.5"))
        self.assertEqual(single[0]["rank_scores"], dict.fromkeys(WEIGHTS, Decimal("0.5")))
        # The first two scores are mathematically tied despite thirds in their factor ranks.
        thirds = calculate_factor_rankings([
            stock("0002", "4", "1", "3"), stock("0001", "2", "3", "1"),
            stock("0003", "1", "2", "4"), stock("0004", "3", "4", "2"),
        ], {"mom20": "0.5", "trend20": "0.25", "lowvol20": "0.25"})
        tied = [row for row in thirds if row["ticker"] in ("0001", "0002")]
        self.assertEqual(tied[0]["score"], tied[1]["score"])
        self.assertEqual([row["ticker"] for row in tied], ["0001", "0002"])

    def test_invalid_values_duplicate_tickers_and_common_profile_errors_stop(self):
        normal = stock("0001", "0.1", "0.2", "0.3")
        for rows in ([], [normal, normal], [stock("0001", "NaN", "0", "0")],
                     [stock("0001", "0", "Infinity", "0")], [stock("0001", "0", "0", "-0.1")],
                     [{"ticker": "0001", "values": {"mom20": "0", "trend20": "0"}}]):
            with self.subTest(rows=rows), self.assertRaises(RankingError):
                calculate_factor_rankings(rows, WEIGHTS)
        for weights in ({"mom20": "0.4", "trend20": "0.25"},
                        {**WEIGHTS, "lowvol20": "0.30"}, {**WEIGHTS, "mom20": "-0.4"},
                        {**WEIGHTS, "mom20": "Infinity"}):
            with self.subTest(weights=weights), self.assertRaises(RankingError):
                calculate_factor_rankings([normal], weights)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps({"format_version": "1.0", "factor_profile": "price_only_v1",
                                       "enabled_factors": ["mom20", "trend20", "mom20"], "weights": WEIGHTS}), encoding="utf-8")
            with self.assertRaises(RankingError):
                load_ranking_profile(path)

    def test_metadata_only_export_preserves_exclusions_versions_and_new_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            metadata_path, profile_path = directory / "features.json", directory / "profile.json"
            excluded = [{"ticker": "0004", "status": "missing_prices", "missing_dates": ["2025-09-30"],
                         "source_metadata": {"source_keys": ["EXCLUDED-FIXTURE"]}}]
            source = {"analysis_format_version": "1.0", "scope": "historical_raw_price_feature_analysis",
                      "as_of": "2025-09-30", "feature_version": "fixture-features-v1",
                      "universe_version": "fixture-universe-v1", "calendar_version": "fixture-calendar-v1",
                      "price_basis": "unadjusted_raw_close", "submission_ready": False,
                      "limitations": ["historical fixture prices only"],
                      "rows": [stock("0001", "0.1", "0.2", "0.3"), stock("0002", "0.2", "0.1", "0.1")],
                      "excluded_stocks": excluded,
                      "summary": {"stock_count": 3, "analyzed_stock_count": 2, "excluded_stock_count": 1},
                      "daily_inputs": [{"path": "do-not-read-prices.csv", "sha256": "x" * 64}],
                      "input_manifest": {"path": "do-not-read-manifest.json", "sha256": "y" * 64}}
            metadata_path.write_text(json.dumps(source), encoding="utf-8")
            profile_path.write_text(json.dumps({"format_version": "1.0", "factor_profile": "price_only_v1",
                                               "enabled_factors": list(WEIGHTS), "weights": WEIGHTS}), encoding="utf-8")
            original_read_bytes = Path.read_bytes

            def permitted(path):
                self.assertIn(path.resolve(), {metadata_path.resolve(), profile_path.resolve()})
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", new=permitted):
                report = analyze_history_rankings(metadata_path, profile_path)
                repeated = analyze_history_rankings(metadata_path, profile_path)
            self.assertEqual(report, repeated)
            self.assertEqual(report["excluded_stocks"], excluded)
            self.assertEqual(report["summary"], {"stock_count": 3, "ranked_stock_count": 2, "excluded_stock_count": 1})
            self.assertEqual(report["profile"]["weights"], WEIGHTS)
            self.assertEqual(report["feature_version"], "fixture-features-v1")
            self.assertEqual(report["input_feature_metadata"]["sha256"], hashlib.sha256(metadata_path.read_bytes()).hexdigest())
            self.assertEqual(report["input_profile"]["sha256"], hashlib.sha256(profile_path.read_bytes()).hexdigest())
            self.assertEqual(report["rows"][0]["source_metadata"], source["rows"][1]["source_metadata"])
            self.assertTrue(all(row["analysis_included"] and not row["formal_eligible"] for row in report["rows"]))
            self.assertFalse(report["submission_ready"])
            saved = write_ranking_analysis(report, directory / "rankings")
            csv_path = Path(saved["rankings_csv"])
            before = csv_path.read_bytes()
            self.assertTrue(before.startswith(b"\xef\xbb\xbf"))
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames), RANKING_CSV_COLUMNS)
                rows = list(reader)
            self.assertEqual(rows[0]["ticker"], "0002")
            self.assertEqual(rows[0]["mom20_pct"], "20.000000")
            self.assertEqual(rows[0]["rank_lowvol20_pct"], "100.000000")
            self.assertEqual(rows[0]["contribution_lowvol20_pct"], "35.000000")
            self.assertEqual(rows[0]["score_pct"], "75.000000")
            self.assertEqual(rows[0]["formal_eligible"], "false")
            self.assertEqual({path.name for path in Path(saved["run_dir"]).iterdir()}, {"rankings.csv", "metadata.json"})
            stored = json.loads(Path(saved["metadata_json"]).read_text(encoding="utf-8"))
            self.assertEqual(stored["ranking_version"], report["ranking_version"])
            self.assertEqual(stored["artifacts"], {"rankings_csv": "rankings.csv"})
            newer = write_ranking_analysis(repeated, directory / "rankings")
            self.assertNotEqual(saved["run_dir"], newer["run_dir"])
            self.assertEqual(csv_path.read_bytes(), before)
            self.assertEqual(Path(newer["rankings_csv"]).read_bytes(), before)
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["weights"] = {"mom20": "0.35", "trend20": "0.25", "lowvol20": "0.40"}
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            changed = analyze_history_rankings(metadata_path, profile_path)
            self.assertNotEqual(changed["ranking_version"], report["ranking_version"])


if __name__ == "__main__":
    unittest.main()
