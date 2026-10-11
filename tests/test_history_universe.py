"""150 檔下載器的離線行為測試；所有行情與 HTTP 回應都是人工 fixture。

每檔只放兩個示範日期，以核對分組、證據、失敗及快取行為；
這些測試不發出 HTTP，也不把 fixture 視為真正的 2025-09 完整行情。
"""

import copy
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from etf_agent.coverage import PRICE_CSV_COLUMNS
from etf_agent.history import _write_json, download_history_sample, download_history_universe
from etf_agent.providers.http import DownloadError, HttpResponse
from etf_agent.providers.monthly import HistoryDataError
from etf_agent.universe import load_universe


ROOT = Path(__file__).resolve().parents[1]
MONTH = "2025-09"
FETCHED_AT = datetime.fromisoformat("2026-10-11T15:00:00+08:00")


def fixture_payload(market, ticker, *, days=("01", "02")):
    """符合 adapter 身分檢查的人工月報，並保留各市場來源單位。"""
    rows = [
        [f"114/09/{day}", "1,234,001" if market == "TWSE" else "1,234",
         "123,400,123" if market == "TWSE" else "123,400",
         "100.00", "102.50", "99.50", "101.00", "+1.00", "1,234"]
        for day in days
    ]
    notes = ["人工離線 fixture，非官方歷史行情"]
    if market == "TWSE":
        return {
            "stat": "OK", "date": "20250901",
            "title": f"114年9月 {ticker} 測試股票 各日成交資訊",
            "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價",
                       "收盤價", "漲跌價差", "成交筆數"],
            "data": rows, "notes": notes,
        }
    return {
        "stat": "ok", "date": "20250901", "code": ticker,
        "tables": [{
            "date": "20250901",
            "fields": ["日期", "成交張數", "成交仟元", "開盤", "最高", "最低",
                       "收盤", "漲跌", "筆數"],
            "data": rows, "notes": notes,
        }],
    }


class UniverseHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.universe = load_universe(ROOT / "data" / "universe.csv")

    def fetcher(self, calls, *, responses=None, days=None):
        responses = responses or {}
        days = days or {}

        def fetch(url, *, transport, timeout):
            self.assertEqual(timeout, 10)
            query = parse_qs(urlsplit(url).query)
            market = "TWSE" if "twse.com.tw" in urlsplit(url).hostname else "TPEX"
            ticker = query["stockNo" if market == "TWSE" else "code"][0]
            calls.append((market, ticker))
            response = responses.get(ticker)
            if isinstance(response, Exception):
                raise response
            if response is None:
                payload = fixture_payload(market, ticker, days=days.get(ticker, ("01", "02")))
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                status, content_type = 200, "application/json; charset=utf-8"
            else:
                body, status, content_type = response
            return HttpResponse(body, url, status, content_type, FETCHED_AT, "offline-fixture")

        return fetch

    def download(self, output, *, calls=None, **kwargs):
        calls = [] if calls is None else calls
        kwargs.setdefault("fetcher", self.fetcher(calls))
        kwargs.setdefault("sleeper", lambda duration: None)
        return download_history_universe(MONTH, Path(output), universe=self.universe, **kwargs)

    def read_csv(self, path):
        path = Path(path)
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(tuple(reader.fieldnames), PRICE_CSV_COLUMNS)
            return list(reader)

    def daily_rows(self, result):
        return [row for daily in result["daily_prices"] for row in self.read_csv(daily["prices_csv"])]

    def coverage(self, result):
        return json.loads(Path(result["coverage_report"]).read_text(encoding="utf-8"))

    def make_sample_cache(self, output):
        return download_history_sample(MONTH, Path(output), fetcher=self.fetcher([]))

    def test_full_fixture_has_150_unique_sources_and_consistent_daily_monthly_and_source_views(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, calls=calls)
            run = Path(result["run_dir"])
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            self.assertTrue(result["success"])
            self.assertEqual((result["row_count"], result["network_requests"], result["cache_hits"]), (300, 150, 0))
            self.assertEqual(len(calls), len(set(calls)))
            self.assertEqual(set(calls), {(stock.market, stock.ticker) for stock in self.universe.stocks})
            self.assertEqual(manifest["source_count"], 150)
            self.assertEqual((manifest["network_requests"], manifest["cache_hits"]), (150, 0))
            self.assertEqual(manifest["csv_format_version"], "4.0")
            self.assertEqual(manifest["universe_version"], self.universe.universe_version)
            self.assertEqual(manifest["universe_csv_sha256"], self.universe.csv_sha256)
            self.assertEqual(manifest["universe_source_sha256"], self.universe.source_sha256)
            self.assertEqual(manifest["expected_counts"], {"TWSE": 100, "TPEX": 50})
            self.assertFalse(manifest["submission_ready"])
            sources = manifest["sources"]
            self.assertEqual([source["source_key"] for source in sources], [f"H{index}" for index in range(1, 151)])
            self.assertTrue(all(source["status"] == "success" for source in sources))
            by_source = {source["source_key"]: source for source in sources}
            self.assertEqual([(entry["trade_date"], entry["row_count"]) for entry in result["daily_prices"]],
                             [("2025-09-01", 150), ("2025-09-02", 150)])
            daily_rows, monthly_rows = self.daily_rows(result), []
            self.assertEqual(len({(row["trade_date"], row["ticker"]) for row in daily_rows}), 300)
            for row in daily_rows:
                source = by_source[row["source_key"]]
                self.assertEqual((row["market"], row["ticker"]), (source["market"], source["ticker"]))
                self.assertEqual(row["known_at"], "")
                self.assertEqual(row["tradable"], "false")
            for source in sources:
                monthly_rows.extend(self.read_csv(run / source["prices_csv"]))
                raw = (run / source["raw_path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), source["raw_sha256"])
                payload = json.loads(raw.decode("utf-8"))
                table = payload if source["market"] == "TWSE" else payload["tables"][0]
                with (run / source["source_csv"]).open(encoding="utf-8-sig", newline="") as handle:
                    self.assertEqual(list(csv.reader(handle)), [table["fields"], *table["data"]])
            key = lambda row: (row["trade_date"], row["ticker"])
            self.assertEqual(sorted(daily_rows, key=key), sorted(monthly_rows, key=key))
            twse = next(row for row in daily_rows if row["market"] == "TWSE")
            tpex = next(row for row in daily_rows if row["market"] == "TPEX")
            self.assertEqual(Decimal(twse["volume_lots"]), Decimal("1234.001"))
            self.assertEqual(Decimal(twse["amount_ktwd"]), Decimal("123400.123"))
            self.assertEqual((tpex["volume_lots"], tpex["amount_ktwd"], tpex["exact_volume_amount"]), ("", "", "false"))
            self.assertEqual(Decimal(tpex["reported_volume_lots"]), Decimal("1234"))
            report = self.coverage(result)
            self.assertEqual((report["successful_stock_count"], report["expected_stock_count"]), (150, 150))
            self.assertFalse(report["calendar_completeness_verified"])
            self.assertFalse(report["submission_ready"])
            self.assertEqual([(day["present_count"], day["missing_count"]) for day in report["daily_reports"]],
                             [(150, 0), (150, 0)])

    def test_verified_two_stock_cache_avoids_requests_and_preserves_original_raw_fetch_time(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            original = self.make_sample_cache(base / "cache")
            old_run = Path(original["run_dir"])
            old_manifest = json.loads(Path(original["manifest"]).read_text(encoding="utf-8"))
            # 閱讀用 CSV 可以是舊版；重用來源須以 raw JSON 核對及重建。
            for source in old_manifest["sources"]:
                (old_run / source["prices_csv"]).write_text("old csv\n", encoding="utf-8")
                (old_run / source["source_csv"]).write_text("old source view\n", encoding="utf-8")
            original_files = {path.relative_to(old_run): path.read_bytes() for path in old_run.rglob("*") if path.is_file()}
            calls = []
            with patch("etf_agent.history.get_https", side_effect=AssertionError("不得默默繞過注入的 fetcher")):
                result = self.download(base / "output", calls=calls, cache_manifest=Path(original["manifest"]))
            self.assertTrue(result["success"])
            self.assertEqual((result["network_requests"], result["cache_hits"]), (148, 2))
            self.assertEqual(len(calls), 148)
            self.assertNotIn(("TWSE", "2330"), calls)
            self.assertNotIn(("TPEX", "5274"), calls)
            run = Path(result["run_dir"])
            sources = {(source["market"], source["ticker"]): source for source in result["sources"]}
            for old_source in old_manifest["sources"]:
                source = sources[(old_source["market"], old_source["ticker"])]
                self.assertEqual(source["transport"], "cached_replay")
                for field in ("fetched_at", "raw_sha256", "data_version", "requested_url", "effective_url"):
                    self.assertEqual(source[field], old_source[field])
                self.assertEqual((run / source["raw_path"]).read_bytes(), (old_run / old_source["raw_path"]).read_bytes())
            for relative, body in original_files.items():
                self.assertEqual((old_run / relative).read_bytes(), body)

    def test_corrupt_cache_is_blocked_before_fetching_or_creating_new_output(self):
        scenarios = ("hash", "requested_month", "ticker", "requested_url", "effective_url", "content_type", "raw_path")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            original = self.make_sample_cache(base / "cache")
            cache = Path(original["manifest"])
            metadata = json.loads(cache.read_text(encoding="utf-8"))
            for scenario in scenarios:
                with self.subTest(scenario=scenario):
                    changed = copy.deepcopy(metadata)
                    source = changed["sources"][0]
                    if scenario == "hash":
                        source["raw_sha256"] = "0" * 64
                    elif scenario == "requested_month":
                        source["requested_month"] = "2025-08"
                    elif scenario == "ticker":
                        source["ticker"] = "2317"
                    elif scenario == "requested_url":
                        source["requested_url"] = source["requested_url"].replace("2330", "2317")
                    elif scenario == "effective_url":
                        source["effective_url"] = "https://example.invalid/history"
                    elif scenario == "content_type":
                        source["content_type"] = "text/html"
                    else:
                        source["raw_path"] = str((cache.parent / source["raw_path"]).resolve())
                    cache.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
                    output = base / f"blocked-{scenario}"
                    calls = []
                    with self.assertRaises(HistoryDataError):
                        self.download(output, calls=calls, cache_manifest=cache)
                    self.assertEqual(calls, [])
                    self.assertFalse(output.exists())

    def test_partial_failures_keep_raw_evidence_and_missing_stocks_without_fake_rows(self):
        forbidden, html = b"<html>Forbidden fixture</html>", b"<html>Unexpected fixture page</html>"
        first, second = self.universe.stocks[:2]
        responses = {first.ticker: (forbidden, 403, "text/html"), second.ticker: (html, 200, "text/html")}
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            with patch("etf_agent.history.get_https", side_effect=AssertionError("HTTP 拒絕不得觸發其他下載")):
                result = self.download(directory, calls=calls, fetcher=self.fetcher(calls, responses=responses))
            self.assertFalse(result["success"])
            self.assertEqual((result["network_requests"], len(calls)), (150, 150))
            self.assertEqual(result["row_count"], 296)
            run = Path(result["run_dir"])
            self.assertEqual(len(result["sources"]), 150)
            self.assertEqual(len({source["source_key"] for source in result["sources"]}), 150)
            failed = [source for source in result["sources"] if source["status"] == "failed"]
            self.assertEqual({source["ticker"] for source in failed}, {first.ticker, second.ticker})
            for source in failed:
                self.assertIn("error", source)
                self.assertEqual((run / source["raw_path"]).read_bytes(), responses[source["ticker"]][0])
                self.assertNotIn("prices_csv", source)
                self.assertNotIn("source_csv", source)
                self.assertFalse((Path(result["monthly_dir"]) / f'{source["market"]}_{source["ticker"]}_{MONTH}.csv').exists())
            self.assertTrue(all(row["ticker"] not in responses for row in self.daily_rows(result)))
            for report in self.coverage(result)["daily_reports"]:
                self.assertEqual(report["missing_count"], 2)
                self.assertEqual(set(report["missing_tickers"]), set(responses))
                self.assertFalse(report["coverage_complete"])

    def test_all_transport_failures_still_record_150_statuses_without_fake_daily_files(self):
        calls = []
        responses = {stock.ticker: DownloadError("offline connection failure fixture") for stock in self.universe.stocks}
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, calls=calls, fetcher=self.fetcher(calls, responses=responses))
            self.assertFalse(result["success"])
            self.assertEqual((len(calls), result["network_requests"], result["row_count"]), (150, 150, 0))
            self.assertEqual(result["daily_prices"], [])
            self.assertEqual(len(result["sources"]), 150)
            self.assertTrue(all(source["status"] == "failed" and "error" in source for source in result["sources"]))
            self.assertTrue(all("raw_path" not in source and "prices_csv" not in source for source in result["sources"]))
            self.assertEqual(list(Path(result["monthly_dir"]).glob("*.csv")), [])
            report = self.coverage(result)
            self.assertEqual(report["successful_stock_count"], 0)
            self.assertEqual(len(report["failed_stocks"]), 150)
            self.assertEqual(report["daily_reports"], [])

    def test_single_stock_missing_date_remains_missing_in_daily_coverage(self):
        stock = self.universe.stocks[0]
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, calls=calls, fetcher=self.fetcher(calls, days={stock.ticker: ("02",)}))
            self.assertEqual(result["row_count"], 299)
            self.assertEqual([(day["trade_date"], day["row_count"]) for day in result["daily_prices"]],
                             [("2025-09-01", 149), ("2025-09-02", 150)])
            reports = {day["trade_date"]: day for day in self.coverage(result)["daily_reports"]}
            self.assertEqual(reports["2025-09-01"]["missing_tickers"], [stock.ticker])
            self.assertFalse(reports["2025-09-01"]["coverage_complete"])
            self.assertTrue(reports["2025-09-02"]["coverage_complete"])
            source = next(source for source in result["sources"] if source["ticker"] == stock.ticker)
            rows = self.read_csv(Path(result["run_dir"]) / source["prices_csv"])
            self.assertEqual([row["trade_date"] for row in rows], ["2025-09-02"])

    def test_rate_limit_and_progress_follow_each_completed_stock_including_failure(self):
        calls, sleeps, updates = [], [], []
        failed_ticker = self.universe.stocks[3].ticker

        def progress(completed, total, entry):
            updates.append((completed, total, dict(entry), len(calls)))

        with tempfile.TemporaryDirectory() as directory:
            self.download(directory, calls=calls,
                          fetcher=self.fetcher(calls, responses={failed_ticker: DownloadError("fixture")}),
                          request_interval_seconds=1.25, sleeper=sleeps.append, progress=progress)
        self.assertEqual(sleeps, [1.25] * 149)
        self.assertEqual([update[0] for update in updates], list(range(1, 151)))
        self.assertTrue(all(update[1] == 150 and update[3] == update[0] for update in updates))
        self.assertEqual([update[2]["ticker"] for update in updates], [stock.ticker for stock in self.universe.stocks])
        failure = next(update[2] for update in updates if update[2]["ticker"] == failed_ticker)
        self.assertEqual(failure["status"], "failed")

    def test_invalid_current_and_future_months_are_rejected_before_http_and_output(self):
        current_month = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m")
        with tempfile.TemporaryDirectory() as directory:
            for index, month in enumerate(("2025-13", "2025-9", "bad", current_month, "2099-01")):
                with self.subTest(month=month):
                    calls = []
                    output = Path(directory) / str(index)
                    with self.assertRaises(HistoryDataError):
                        download_history_universe(month, output, universe=self.universe,
                                                  fetcher=self.fetcher(calls), sleeper=lambda duration: None)
                    self.assertEqual(calls, [])
                    self.assertFalse(output.exists())

    def test_invalid_or_faster_than_authorized_intervals_are_rejected_before_http_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, interval in enumerate((float("nan"), float("inf"), True, False, 0, -1, 0.25, "1")):
                with self.subTest(interval=interval):
                    calls, sleeps = [], []
                    output = Path(directory) / str(index)
                    with self.assertRaises(HistoryDataError):
                        download_history_universe(MONTH, output, universe=self.universe,
                                                  fetcher=self.fetcher(calls), sleeper=sleeps.append,
                                                  request_interval_seconds=interval)
                    self.assertEqual(calls, [])
                    self.assertEqual(sleeps, [])
                    self.assertFalse(output.exists())

    def test_replaying_complete_cache_makes_new_run_preserves_old_files_and_never_fetches_or_sleeps(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            original = self.download(output)
            original_run = Path(original["run_dir"])
            before = {path.relative_to(original_run): path.read_bytes() for path in original_run.rglob("*") if path.is_file()}
            sleeps, updates = [], []

            def forbidden_fetch(*args, **kwargs):
                raise AssertionError("完整已核對快取不得連網")

            result = self.download(output, cache_manifest=Path(original["manifest"]), fetcher=forbidden_fetch,
                                   sleeper=sleeps.append, progress=lambda completed, total, entry: updates.append(completed))
            self.assertTrue(result["success"])
            self.assertEqual((result["network_requests"], result["cache_hits"]), (0, 150))
            self.assertNotEqual(result["run_dir"], original["run_dir"])
            self.assertEqual(sleeps, [])
            self.assertEqual(updates, list(range(1, 151)))
            self.assertEqual(self.daily_rows(result), self.daily_rows(original))
            for relative, content in before.items():
                self.assertEqual((original_run / relative).read_bytes(), content)

    def test_wrong_ticker_response_is_saved_as_failure_and_cannot_contaminate_other_stock(self):
        stock = self.universe.stocks[0]
        payload = fixture_payload(stock.market, "9999")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(directory, calls=calls,
                                   fetcher=self.fetcher(calls, responses={stock.ticker: (body, 200, "application/json")}))
            self.assertFalse(result["success"])
            self.assertEqual(result["row_count"], 298)
            source = next(source for source in result["sources"] if source["ticker"] == stock.ticker)
            self.assertEqual(source["status"], "failed")
            self.assertEqual((Path(result["run_dir"]) / source["raw_path"]).read_bytes(), body)
            rows = self.daily_rows(result)
            self.assertTrue(all(row["ticker"] not in (stock.ticker, "9999") for row in rows))
            self.assertTrue(all(day["missing_tickers"] == [stock.ticker] for day in self.coverage(result)["daily_reports"]))

    def test_source_csv_write_failure_retains_raw_but_removes_orphan_monthly_csv_and_daily_rows(self):
        stock = self.universe.stocks[0]
        source_filename = f"{stock.market}_{stock.ticker}_{MONTH}_source.csv"
        original_open = Path.open

        def reject_source_csv(path, mode="r", *args, **kwargs):
            if "source_csv" in path.parts and path.name == source_filename and mode == "w":
                raise OSError("fixture source CSV write failure")
            return original_open(path, mode, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path, "open", new=reject_source_csv):
                result = self.download(directory)
            self.assertFalse(result["success"])
            self.assertEqual((result["network_requests"], result["row_count"]), (150, 298))
            run = Path(result["run_dir"])
            failed = [source for source in result["sources"] if source["status"] == "failed"]
            self.assertEqual([source["ticker"] for source in failed], [stock.ticker])
            source = failed[0]
            self.assertIn("fixture source CSV write failure", source["error"])
            raw = (run / source["raw_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["raw_sha256"])
            self.assertEqual(json.loads(raw.decode("utf-8")), fixture_payload(stock.market, stock.ticker))
            self.assertFalse((Path(result["monthly_dir"]) / f"{stock.market}_{stock.ticker}_{MONTH}.csv").exists())
            self.assertFalse((run / "source_csv" / MONTH / source_filename).exists())
            self.assertNotIn("prices_csv", source)
            self.assertNotIn("source_csv", source)
            self.assertTrue(all(row["ticker"] != stock.ticker for row in self.daily_rows(result)))
            self.assertEqual(sum(source["status"] == "success" for source in result["sources"]), 149)
            self.assertTrue(all(day["missing_tickers"] == [stock.ticker] for day in self.coverage(result)["daily_reports"]))

    def test_atomic_json_failure_preserves_existing_manifest_and_removes_partial_temporary_file(self):
        original_write_text = Path.write_text
        attempts = []

        def fail_partial_temporary_write(path, text, *args, **kwargs):
            if path.name.endswith(".tmp"):
                attempts.append(path)
                original_write_text(path, text[:7], *args, **kwargs)
                raise OSError("fixture interrupted JSON write")
            return original_write_text(path, text, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            before = b'{"run_id":"preserved","sources":[]}\n'
            manifest.write_bytes(before)
            with patch.object(Path, "write_text", new=fail_partial_temporary_write):
                with self.assertRaisesRegex(OSError, "fixture interrupted JSON write"):
                    _write_json(manifest, {"run_id": "replacement", "sources": ["new"]})
            self.assertEqual(manifest.read_bytes(), before)
            self.assertEqual(len(attempts), 1)
            self.assertFalse(attempts[0].exists())
            self.assertEqual([path.name for path in Path(directory).iterdir()], ["manifest.json"])


if __name__ == "__main__":
    unittest.main()
