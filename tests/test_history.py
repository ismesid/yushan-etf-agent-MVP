"""歷史月報的離線行為測試；以下報表全部為合成值，沒有抓取真實行情。"""

import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from etf_agent.history import _write_prices, download_history_sample, export_history_sample
from etf_agent.providers import tpex, twse
from etf_agent.providers.http import HttpResponse, get_https
from etf_agent.providers.monthly import HistoryDataError


FETCHED_AT = datetime.fromisoformat("2026-10-11T15:00:00+08:00")


def sample_payload(market):
    """最小合成月報，刻意涵蓋民國日期、逗號與不同市場的單位。"""
    if market == "TWSE":
        return {
            "stat": "OK",
            "date": "20250501",
            "title": "114年05月 2330 台積電 各日成交資訊",
            "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"],
            "data": [["114/05/02", "1,234,001", "123,400,123", "100.00", "102.50", "99.50", "101.00", "+1.00", "1,234"]],
            "notes": ["合成測試資料，非官方行情。"],
        }
    return {
        "stat": "ok",
        "date": "20250501",
        "code": "5274",
        "tables": [{
            "date": "20250501",
            "fields": ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"],
            "data": [["114/05/02", "1,234", "123,400", "100.00", "102.50", "99.50", "101.00", "+1.00", "1,234"]],
            "notes": ["合成測試資料，報表量值精度為張／仟元。"],
        }],
    }


class HistoryParserTests(unittest.TestCase):
    def parse(self, market, payload=None, *, body=None, ticker=None, month="2025-05"):
        if body is None:
            payload = sample_payload(market) if payload is None else payload
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        module = twse if market == "TWSE" else tpex
        return module.parse_month(
            body,
            ticker=ticker or ("2330" if market == "TWSE" else "5274"),
            month=month,
            fetched_at=FETCHED_AT,
            raw_sha256=hashlib.sha256(body).hexdigest(),
        )

    def table(self, market, payload):
        return payload if market == "TWSE" else payload["tables"][0]

    def test_twse_preserves_exact_shares_amount_and_raw_prices(self):
        parsed = self.parse("TWSE")
        bar = parsed.bars[0]
        self.assertEqual(bar.trade_date, date(2025, 5, 2))
        self.assertEqual((bar.ticker, bar.market), ("2330", "TWSE"))
        self.assertEqual(bar.volume_shares, 1234001)
        self.assertEqual(bar.amount_twd, Decimal("123400123"))
        self.assertEqual(bar.close_raw, Decimal("101.00"))
        self.assertEqual(parsed.reported_quantities, ((Decimal("1234001"), Decimal("123400123")),))
        self.assertEqual((parsed.volume_unit, parsed.amount_unit), ("股", "元"))
        self.assertTrue(parsed.exact_volume_amount)

    def test_tpex_scales_reported_values_without_claiming_exact_quantities(self):
        parsed = self.parse("TPEX")
        bar = parsed.bars[0]
        self.assertEqual((bar.trade_date, bar.ticker, bar.market), (date(2025, 5, 2), "5274", "TPEX"))
        self.assertEqual(parsed.reported_quantities, ((Decimal("1234000"), Decimal("123400000")),))
        self.assertEqual((parsed.volume_unit, parsed.amount_unit), ("張", "仟元"))
        self.assertFalse(parsed.exact_volume_amount)
        self.assertIsNone(bar.volume_shares)
        self.assertIsNone(bar.amount_twd)
        self.assertEqual(parsed.source_rows[0][1:3], ("1,234", "123,400"))

    def test_history_keeps_true_fetch_time_unknown_knowledge_time_and_unresolved_adjustments(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                bar = self.parse(market, body=body).bars[0]
                self.assertEqual(bar.fetched_at, FETCHED_AT)
                self.assertIsNone(bar.known_at)
                self.assertIsNone(bar.return_close)
                self.assertEqual(bar.adjustment_status, "unresolved")
                self.assertTrue(bar.price_valid)
                self.assertFalse(bar.tradable)
                self.assertEqual(bar.raw_sha256, hashlib.sha256(body).hexdigest())

    def test_all_missing_prices_and_quantities_remain_null_not_zero(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                row = self.table(market, payload)["data"][0]
                row[1:7] = ["--", "", "---", "----", " ", "--"]
                parsed = self.parse(market, payload)
                bar = parsed.bars[0]
                self.assertEqual((bar.open, bar.high, bar.low, bar.close_raw, bar.volume_shares, bar.amount_twd), (None,) * 6)
                self.assertEqual(parsed.reported_quantities, ((None, None),))
                self.assertFalse(bar.price_valid)
                self.assertFalse(bar.tradable)

    def test_zero_turnover_is_preserved_and_never_enables_trading(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                self.table(market, payload)["data"][0][1:3] = ["0", "0"]
                parsed = self.parse(market, payload)
                self.assertEqual(parsed.reported_quantities, ((Decimal(0), Decimal(0)),))
                self.assertFalse(parsed.bars[0].tradable)

    def test_unrequested_top_level_month_is_rejected(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                payload["date"] = "20251001"
                with self.assertRaises(HistoryDataError):
                    self.parse(market, payload)

    def test_latest_rows_cannot_be_mislabeled_as_requested_history(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                self.table(market, payload)["data"][0][0] = "115/10/02"
                with self.assertRaisesRegex(HistoryDataError, "年月"):
                    self.parse(market, payload)

    def test_different_stock_is_rejected(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                if market == "TWSE":
                    payload["title"] = "114年05月 2317 鴻海 各日成交資訊"
                else:
                    payload["code"] = "6223"
                with self.assertRaisesRegex(HistoryDataError, "股票"):
                    self.parse(market, payload)

    def test_html_errors_and_non_object_json_are_rejected(self):
        for market in ("TWSE", "TPEX"):
            for body in (b"<html>403 Forbidden</html>", b"[]", b"null"):
                with self.subTest(market=market, body=body):
                    with self.assertRaises(HistoryDataError):
                        self.parse(market, body=body)

    def test_empty_month_and_failure_status_do_not_create_fake_rows(self):
        for market in ("TWSE", "TPEX"):
            for scenario in ("empty", "error"):
                with self.subTest(market=market, scenario=scenario):
                    payload = sample_payload(market)
                    if scenario == "empty":
                        self.table(market, payload)["data"] = []
                    else:
                        payload["stat"] = "查無資料"
                    with self.assertRaises(HistoryDataError):
                        self.parse(market, payload)

    def test_unrecognized_volume_or_amount_unit_blocks_parsing(self):
        for market in ("TWSE", "TPEX"):
            for field_index in (1, 2):
                with self.subTest(market=market, field_index=field_index):
                    payload = sample_payload(market)
                    self.table(market, payload)["fields"][field_index] = "成交百股" if field_index == 1 else "成交萬元"
                    with self.assertRaisesRegex(HistoryDataError, "欄位／單位"):
                        self.parse(market, payload)

    def test_field_reordering_uses_names_instead_of_assumed_positions(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                table = self.table(market, payload)
                table["fields"] = list(reversed(table["fields"]))
                table["data"] = [list(reversed(row)) for row in table["data"]]
                parsed = self.parse(market, payload)
                self.assertEqual(parsed.bars[0].close_raw, Decimal("101.00"))
                self.assertEqual(parsed.bars[0].trade_date, date(2025, 5, 2))

    def test_duplicate_fields_are_rejected_even_if_only_whitespace_differs(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                fields = self.table(market, payload)["fields"]
                fields[-1] = "日 期"
                with self.assertRaisesRegex(HistoryDataError, "欄位名稱重複"):
                    self.parse(market, payload)

    def test_identical_duplicate_day_is_deduplicated_but_conflict_is_rejected(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                rows = self.table(market, payload)["data"]
                rows.append(copy.deepcopy(rows[0]))
                parsed = self.parse(market, payload)
                self.assertEqual((len(parsed.bars), len(parsed.source_rows), len(parsed.reported_quantities)), (1, 1, 1))
                rows[-1][6] = "101.50"
                with self.assertRaisesRegex(HistoryDataError, "衝突"):
                    self.parse(market, payload)

    def test_sorting_keeps_original_rows_and_reported_quantities_aligned(self):
        for market in ("TWSE", "TPEX"):
            with self.subTest(market=market):
                payload = sample_payload(market)
                rows = self.table(market, payload)["data"]
                later = copy.deepcopy(rows[0])
                later[0:3] = ["114/05/05", "2,000", "200,000"]
                rows.insert(0, later)
                parsed = self.parse(market, payload)
                self.assertEqual([bar.trade_date for bar in parsed.bars], [date(2025, 5, 2), date(2025, 5, 5)])
                self.assertEqual(parsed.source_rows[1][0:3], tuple(later[0:3]))
                factor = Decimal(1) if market == "TWSE" else Decimal(1000)
                self.assertEqual(parsed.reported_quantities[1], (Decimal(2000) * factor, Decimal(200000) * factor))

    def test_invalid_ohlc_is_rejected(self):
        for market in ("TWSE", "TPEX"):
            for prices in (["100", "102", "99", "103"], ["100", "98", "99", "100"], ["0", "102", "99", "100"]):
                with self.subTest(market=market, prices=prices):
                    payload = sample_payload(market)
                    self.table(market, payload)["data"][0][3:7] = prices
                    with self.assertRaisesRegex(HistoryDataError, "行情不合理"):
                        self.parse(market, payload)

    def test_negative_fractional_volume_or_nonfinite_numbers_are_rejected(self):
        for market in ("TWSE", "TPEX"):
            for value in ("-1", "1.5", "NaN", "Infinity"):
                with self.subTest(market=market, value=value):
                    payload = sample_payload(market)
                    self.table(market, payload)["data"][0][1] = value
                    with self.assertRaises(HistoryDataError):
                        self.parse(market, payload)

    def test_incomplete_turnover_and_zero_volume_with_positive_amount_are_rejected(self):
        for market in ("TWSE", "TPEX"):
            for quantities in (["--", "123"], ["123", "--"], ["0", "123"]):
                with self.subTest(market=market, quantities=quantities):
                    payload = sample_payload(market)
                    self.table(market, payload)["data"][0][1:3] = quantities
                    with self.assertRaises(HistoryDataError):
                        self.parse(market, payload)

    def test_invalid_calendar_dates_and_row_shape_are_rejected(self):
        for market in ("TWSE", "TPEX"):
            for scenario in ("day", "length", "type"):
                with self.subTest(market=market, scenario=scenario):
                    payload = sample_payload(market)
                    row = self.table(market, payload)["data"][0]
                    if scenario == "day":
                        row[0] = "114/05/32"
                    elif scenario == "length":
                        row.pop()
                    else:
                        row[1] = 1234
                    with self.assertRaises(HistoryDataError):
                        self.parse(market, payload)

    def test_tpex_table_date_and_structure_must_match_request(self):
        for scenario in ("date", "extra_table", "missing_table"):
            with self.subTest(scenario=scenario):
                payload = sample_payload("TPEX")
                if scenario == "date":
                    payload["tables"][0]["date"] = "20251001"
                elif scenario == "extra_table":
                    payload["tables"].append(copy.deepcopy(payload["tables"][0]))
                else:
                    payload["tables"] = []
                with self.assertRaises(HistoryDataError):
                    self.parse("TPEX", payload)

    def test_history_urls_require_real_month_and_four_digit_stock(self):
        for module in (twse, tpex):
            for ticker, month in (("2330", "2025-13"), ("2330", "2025-5"), ("233", "2025-05"), ("23A0", "2025-05")):
                with self.subTest(provider=module.__name__, ticker=ticker, month=month):
                    with self.assertRaises(HistoryDataError):
                        module.history_url(ticker, month)


class HistoryOutputTests(unittest.TestCase):
    def test_urllib_http_error_preserves_status_and_original_body(self):
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=20250501&stockNo=2330&response=json"
        body = b"<html>Forbidden</html>"
        error = HTTPError(url, 403, "Forbidden", {"Content-Type": "text/html"}, io.BytesIO(body))
        with patch("etf_agent.providers.http.urlopen", side_effect=error):
            response = get_https(url, transport="urllib")
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status, 403)
        self.assertEqual(response.body, body)
        self.assertEqual(response.url, url)
        self.assertEqual(response.content_type, "text/html")
        self.assertEqual(response.transport, "urllib")

    def fetcher(self, responses):
        """注入本機回應，禁止測試發出 HTTP 請求。"""
        def fetch(url, *, transport, timeout):
            self.assertEqual(timeout, 10)
            market = "TWSE" if "twse.com.tw" in url else "TPEX"
            body, status, content_type = responses[market]
            return HttpResponse(body, url, status, content_type, FETCHED_AT, "offline-test")
        return fetch

    def good_response(self, market, payload=None):
        payload = sample_payload(market) if payload is None else payload
        return json.dumps(payload, ensure_ascii=False).encode("utf-8"), 200, "application/json; charset=utf-8"

    def read_csv(self, path):
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            self.assertIn("trade_date", reader.fieldnames)
            self.assertIn("volume_lots", reader.fieldnames)
            self.assertIn("reported_volume_lots", reader.fieldnames)
            for name in ("open_ktwd_per_lot", "high_ktwd_per_lot", "low_ktwd_per_lot",
                         "close_raw_ktwd_per_lot", "return_close_ktwd_per_lot",
                         "amount_ktwd", "reported_amount_ktwd", "avg_price_ktwd_per_lot",
                         "reported_avg_price_ktwd_per_lot"):
                self.assertIn(name, reader.fieldnames)
            self.assertNotIn("volume_shares", reader.fieldnames)
            self.assertNotIn("reported_volume_shares", reader.fieldnames)
            self.assertNotIn("source_url", reader.fieldnames)
            self.assertNotIn("source_volume_unit", reader.fieldnames)
            self.assertNotIn("source_amount_unit", reader.fieldnames)
            self.assertEqual(len(reader.fieldnames), 22)
            for name in ("open", "high", "low", "close_raw", "return_close",
                         "amount_twd", "reported_amount_twd", "raw_sha256"):
                self.assertNotIn(name, reader.fieldnames)
            return rows

    def read_daily_rows(self, result):
        rows = []
        for daily in sorted(result["daily_prices"], key=lambda item: item["trade_date"]):
            rows.extend(self.read_csv(daily["prices_csv"]))
        return rows

    def test_daily_tables_group_stocks_by_date_and_equal_monthly_history_without_duplicate_rows(self):
        responses = {}
        for market, days in (("TWSE", ["114/05/06", "114/05/02", "114/05/05", "114/05/02"]),
                             ("TPEX", ["114/05/05", "114/05/02"])):
            payload = sample_payload(market)
            table = payload if market == "TWSE" else payload["tables"][0]
            template = list(table["data"][0])
            table["data"] = []
            for day in days:
                row = list(template)
                row[0] = day
                table["data"].append(row)
            responses[market] = self.good_response(market, payload)
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            run = Path(result["run_dir"])
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            self.assertTrue(result["success"])
            self.assertEqual(result["row_count"], 5)
            self.assertNotIn("prices_csv", result)
            self.assertNotIn("prices_csv", manifest)
            self.assertEqual(Path(result["daily_dir"]), run / "daily" / "2025-05")
            self.assertEqual(Path(result["monthly_dir"]), run / "monthly" / "2025-05")
            self.assertEqual([(item["trade_date"], item["row_count"]) for item in result["daily_prices"]],
                             [("2025-05-02", 2), ("2025-05-05", 2), ("2025-05-06", 1)])
            for saved, listed in zip(manifest["daily_prices"], result["daily_prices"], strict=True):
                expected_relative = f'daily/2025-05/{saved["trade_date"]}_prices.csv'
                self.assertEqual(saved["prices_csv"], expected_relative)
                self.assertEqual(Path(listed["prices_csv"]), run / expected_relative)
                daily_rows = self.read_csv(listed["prices_csv"])
                self.assertEqual(len(daily_rows), saved["row_count"])
                self.assertEqual({row["trade_date"] for row in daily_rows}, {saved["trade_date"]})
                self.assertEqual(len({(row["market"], row["ticker"]) for row in daily_rows}), len(daily_rows))
                self.assertEqual([row["ticker"] for row in daily_rows], sorted(row["ticker"] for row in daily_rows))
            monthly_rows = []
            for source in manifest["sources"]:
                monthly_path = run / source["prices_csv"]
                rows = self.read_csv(monthly_path)
                self.assertEqual({(row["market"], row["ticker"]) for row in rows},
                                 {(source["market"], source["ticker"])})
                self.assertEqual([row["trade_date"] for row in rows], sorted(row["trade_date"] for row in rows))
                monthly_rows.extend(rows)
                self.assertFalse((run / monthly_path.name).exists())
            daily_rows = self.read_daily_rows(result)
            self.assertEqual(len({(row["trade_date"], row["market"], row["ticker"]) for row in daily_rows}), 5)
            row_key = lambda row: (row["trade_date"], row["ticker"], row["market"])
            self.assertEqual(sorted(daily_rows, key=row_key), sorted(monthly_rows, key=row_key))
            self.assertFalse((run / "prices.csv").exists())

    def test_daily_tables_do_not_invent_missing_dates_or_missing_stock_rows(self):
        twse_payload = sample_payload("TWSE")
        tpex_payload = sample_payload("TPEX")
        tpex_payload["tables"][0]["data"][0][0] = "114/05/06"
        responses = {"TWSE": self.good_response("TWSE", twse_payload),
                     "TPEX": self.good_response("TPEX", tpex_payload)}
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            self.assertTrue(result["success"])
            self.assertEqual([(item["trade_date"], item["row_count"]) for item in result["daily_prices"]],
                             [("2025-05-02", 1), ("2025-05-06", 1)])
            rows = self.read_daily_rows(result)
            self.assertEqual([(row["trade_date"], row["ticker"]) for row in rows],
                             [("2025-05-02", "2330"), ("2025-05-06", "5274")])
            self.assertFalse((Path(result["daily_dir"]) / "2025-05-05_prices.csv").exists())
            quality = json.loads((Path(result["run_dir"]) / "data_quality.json").read_text(encoding="utf-8"))
            self.assertFalse(quality["checks"]["calendar_completeness_verified"])
            self.assertFalse(quality["checks"]["all_150_symbols_covered"])
            self.assertFalse(quality["submission_ready"])

    def test_readable_units_make_price_times_lots_equal_thousands_and_keep_average_precision_scope(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            self.assertTrue(result["success"])
            rows = self.read_daily_rows(result)
            twse_row = next(row for row in rows if row["market"] == "TWSE")
            tpex_row = next(row for row in rows if row["market"] == "TPEX")
            prices = {name: Decimal(twse_row[name + "_ktwd_per_lot"])
                      for name in ("open", "high", "low", "close_raw")}
            self.assertEqual(prices, {"open": Decimal("100"), "high": Decimal("102.5"),
                                      "low": Decimal("99.5"), "close_raw": Decimal("101")})
            # 買兩張的收盤估值：101 千元／張 × 2 張 = 202 千元。
            self.assertEqual(prices["close_raw"] * Decimal(2), Decimal("202"))
            self.assertEqual(prices["close_raw"] * Decimal(2), Decimal("101") * Decimal(2000) / 1000)
            self.assertEqual(Decimal(twse_row["amount_ktwd"]), Decimal("123400.123"))
            self.assertEqual(Decimal(twse_row["reported_amount_ktwd"]), Decimal("123400.123"))
            self.assertEqual(twse_row["avg_price_ktwd_per_lot"], "100.00001864")
            self.assertEqual(twse_row["reported_avg_price_ktwd_per_lot"], "100.00001864")
            self.assertNotEqual(Decimal(twse_row["avg_price_ktwd_per_lot"]), sum(prices.values()) / 4)
            self.assertEqual((tpex_row["amount_ktwd"], tpex_row["avg_price_ktwd_per_lot"]), ("", ""))
            self.assertEqual(Decimal(tpex_row["reported_amount_ktwd"]), Decimal("123400"))
            self.assertEqual(tpex_row["reported_avg_price_ktwd_per_lot"], "100.00000000")
            self.assertEqual(tpex_row["exact_volume_amount"], "false")
            self.assertEqual((twse_row["return_close_ktwd_per_lot"], twse_row["known_at"]), ("", ""))
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["csv_format_version"], "4.0")
            for field in ("prices", "amount_ktwd", "reported_amount_ktwd", "avg_price_ktwd_per_lot",
                          "reported_avg_price_ktwd_per_lot"):
                self.assertIn("千元", manifest["csv_units"][field])
            self.assertIn("千元／張", manifest["csv_units"]["prices"])
            self.assertEqual(manifest["csv_average_rounding"]["decimal_places"], 8)
            self.assertEqual(manifest["csv_average_rounding"]["mode"], "ROUND_HALF_UP")
            for source in manifest["sources"]:
                self.assertEqual(source["raw_sha256"], hashlib.sha256(responses[source["market"]][0]).hexdigest())
                expected = ("股", "元") if source["market"] == "TWSE" else ("張", "仟元")
                self.assertEqual((source["units"]["source_volume"], source["units"]["source_amount"]), expected)

    def test_daily_average_has_eight_decimal_places_and_half_up_rounding(self):
        payload = sample_payload("TWSE")
        template = payload["data"][0]
        cases = (("114/05/02", "3", "301", "100.33333333"),
                 ("114/05/05", "200000000", "20000000001", "100.00000001"),
                 ("114/05/06", "200000000", "20000000000", "100.00000000"))
        payload["data"] = []
        for day, volume, amount, expected in cases:
            row = list(template)
            row[:3] = [day, volume, amount]
            payload["data"].append(row)
        responses = {"TWSE": self.good_response("TWSE", payload), "TPEX": self.good_response("TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            self.assertTrue(result["success"])
            rows = [row for row in self.read_daily_rows(result) if row["market"] == "TWSE"]
            self.assertEqual([row["avg_price_ktwd_per_lot"] for row in rows], [case[3] for case in cases])
            self.assertEqual([row["reported_avg_price_ktwd_per_lot"] for row in rows], [case[3] for case in cases])

    def test_source_csv_is_grouped_by_month_distinguished_from_cleaned_csv_and_preserves_source_values(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            self.assertTrue(result["success"])
            run = Path(result["run_dir"])
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            for source in manifest["sources"]:
                market, ticker = source["market"], source["ticker"]
                source_relative = f"source_csv/2025-05/{market}_{ticker}_2025-05_source.csv"
                self.assertEqual(source["source_csv"], source_relative)
                self.assertEqual(source["prices_csv"], f"monthly/2025-05/{market}_{ticker}_2025-05.csv")
                cleaned_path = run / source["prices_csv"]
                source_path = run / source_relative
                self.assertNotEqual(source_path.name, cleaned_path.name)
                self.assertTrue(cleaned_path.is_file())
                self.assertFalse((run / cleaned_path.name).exists())
                self.assertFalse((run / "source_csv" / cleaned_path.name).exists())
                payload = sample_payload(market)
                table = payload if market == "TWSE" else payload["tables"][0]
                with source_path.open(encoding="utf-8-sig", newline="") as handle:
                    self.assertEqual(list(csv.reader(handle)), [table["fields"], *table["data"]])
                self.assertIn("成交股數" if market == "TWSE" else "成交張數", table["fields"])
                self.assertIn("成交金額" if market == "TWSE" else "成交仟元", table["fields"])

    def test_zero_or_missing_turnover_has_no_average_even_when_ohlc_is_available(self):
        responses = {}
        for market in ("TWSE", "TPEX"):
            payload = sample_payload(market)
            table = payload if market == "TWSE" else payload["tables"][0]
            template = table["data"][0]
            zero, missing = list(template), list(template)
            zero[1:3] = ["0", "0"]
            missing[:3] = ["114/05/05", "--", "--"]
            table["data"] = [zero, missing]
            responses[market] = self.good_response(market, payload)
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            self.assertTrue(result["success"])
            rows = self.read_daily_rows(result)
            self.assertEqual(len(rows), 4)
            for row in rows:
                self.assertEqual(row["close_raw_ktwd_per_lot"], "101.00")
                self.assertEqual((row["avg_price_ktwd_per_lot"], row["reported_avg_price_ktwd_per_lot"]), ("", ""))
                if row["trade_date"] == "2025-05-05":
                    self.assertEqual((row["volume_lots"], row["amount_ktwd"],
                                      row["reported_volume_lots"], row["reported_amount_ktwd"]), ("",) * 4)

    def test_csv_conversion_preserves_core_row_and_ignores_callers_decimal_precision(self):
        payload = sample_payload("TWSE")
        payload["data"][0][1:3] = ["200000000", "20000000001"]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()
        parsed = twse.parse_month(body, ticker="2330", month="2025-05", fetched_at=FETCHED_AT, raw_sha256=digest)
        bar = parsed.bars[0]
        volume, amount = parsed.reported_quantities[0]
        row = bar.to_dict()
        row.update({"reported_volume_shares": str(volume), "reported_amount_twd": str(amount),
                    "source_volume_unit": parsed.volume_unit, "source_amount_unit": parsed.amount_unit,
                    "exact_volume_amount": parsed.exact_volume_amount})
        original_row = copy.deepcopy(row)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            with localcontext() as context:
                context.prec = 6
                _write_prices(path, [row])
            exported = self.read_csv(path)[0]
            self.assertEqual(Decimal(exported["volume_lots"]), Decimal("200000"))
            self.assertEqual(Decimal(exported["amount_ktwd"]), Decimal("20000000.001"))
            self.assertEqual(exported["avg_price_ktwd_per_lot"], "100.00000001")
            self.assertEqual(exported["reported_avg_price_ktwd_per_lot"], "100.00000001")
        self.assertEqual(row, original_row)
        self.assertEqual(bar.volume_shares, 200000000)
        self.assertEqual(bar.amount_twd, Decimal("20000000001"))
        self.assertEqual(bar.close_raw, Decimal("101"))
        self.assertEqual(bar.raw_sha256, digest)

    def test_html_and_http_403_preserve_raw_evidence_without_fake_market_csv(self):
        responses = {
            "TWSE": (b"<html>Service unavailable</html>", 200, "text/html"),
            "TPEX": (b'{"message":"Forbidden"}', 403, "application/json"),
        }
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            run = Path(result["run_dir"])
            self.assertFalse(result["success"])
            self.assertEqual(result["row_count"], 0)
            self.assertEqual(result["daily_prices"], [])
            self.assertNotIn("prices_csv", result)
            self.assertFalse((run / "prices.csv").exists())
            manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
            quality = json.loads((run / "data_quality.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["success"])
            self.assertFalse(quality["success"])
            self.assertFalse(manifest["submission_ready"])
            self.assertEqual(manifest["daily_prices"], [])
            self.assertNotIn("prices_csv", manifest)
            for source in manifest["sources"]:
                expected_body = responses[source["market"]][0]
                self.assertEqual(source["status"], "failed")
                self.assertIn("error", source)
                self.assertEqual((run / source["raw_path"]).read_bytes(), expected_body)
                self.assertEqual(source["raw_sha256"], hashlib.sha256(expected_body).hexdigest())
                self.assertNotIn("prices_csv", source)
                self.assertFalse((run / f'{source["market"]}_{source["ticker"]}_2025-05.csv').exists())
            self.assertEqual(list((run / "source_csv").iterdir()), [])

    def test_partial_download_keeps_valid_rows_but_does_not_claim_complete_success(self):
        responses = {
            "TWSE": self.good_response("TWSE"),
            "TPEX": (b"Forbidden", 403, "text/plain"),
        }
        with tempfile.TemporaryDirectory() as directory:
            result = download_history_sample("2025-05", Path(directory), fetcher=self.fetcher(responses))
            run = Path(result["run_dir"])
            self.assertFalse(result["success"])
            self.assertEqual(result["row_count"], 1)
            rows = self.read_daily_rows(result)
            self.assertEqual([(row["ticker"], row["trade_date"]) for row in rows], [("2330", "2025-05-02")])
            self.assertEqual(Decimal(rows[0]["volume_lots"]), Decimal("1234.001"))
            self.assertEqual(Decimal(rows[0]["volume_lots"]) * 1000, Decimal("1234001"))
            self.assertEqual(rows[0]["known_at"], "")
            self.assertEqual(rows[0]["tradable"], "false")
            self.assertTrue((run / "monthly" / "2025-05" / "TWSE_2330_2025-05.csv").exists())
            self.assertFalse((run / "monthly" / "2025-05" / "TPEX_5274_2025-05.csv").exists())
            self.assertEqual([(item["trade_date"], item["row_count"]) for item in result["daily_prices"]],
                             [("2025-05-02", 1)])
            self.assertEqual([source["status"] for source in result["sources"]], ["success", "failed"])
            quality = json.loads((run / "data_quality.json").read_text(encoding="utf-8"))
            self.assertFalse(quality["success"])
            self.assertEqual(quality["rows"], 1)

    def test_rerun_creates_new_directory_and_preserves_prior_evidence(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = download_history_sample("2025-05", output, fetcher=self.fetcher(responses))
            first_run = Path(first["run_dir"])
            original_files = {path.relative_to(first_run): path.read_bytes()
                              for path in first_run.rglob("*") if path.is_file()}
            second = download_history_sample("2025-05", output, fetcher=self.fetcher(responses))
            self.assertTrue(first["success"])
            self.assertTrue(second["success"])
            self.assertNotEqual(first["run_dir"], second["run_dir"])
            self.assertEqual(first["row_count"], 2)
            self.assertEqual(second["row_count"], 2)
            for relative, original in original_files.items():
                self.assertEqual((first_run / relative).read_bytes(), original)
            rows = self.read_daily_rows(second)
            tpex_row = next(row for row in rows if row["market"] == "TPEX")
            self.assertEqual((tpex_row["volume_lots"], tpex_row["amount_ktwd"]), ("", ""))
            self.assertEqual(Decimal(tpex_row["reported_volume_lots"]), Decimal("1234"))
            self.assertEqual(Decimal(tpex_row["reported_amount_ktwd"]), Decimal("123400"))
            self.assertEqual(tpex_row["exact_volume_amount"], "false")

    def test_offline_export_uses_verified_raw_preserves_evidence_and_never_fetches(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            original = download_history_sample("2025-05", output, fetcher=self.fetcher(responses))
            original_run = Path(original["run_dir"])
            manifest_path = Path(original["manifest"])
            original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # 舊樣本只有 manifest format_version=1.0，讀者 CSV 使用股數及重複網址。
            # 重匯出應重讀原始 JSON，不能要求舊 CSV 已經是新格式。
            original_manifest.pop("csv_format_version", None)
            original_manifest.pop("daily_prices", None)
            original_manifest["prices_csv"] = "prices.csv"
            manifest_path.write_text(json.dumps(original_manifest, ensure_ascii=False), encoding="utf-8")
            (original_run / "prices.csv").write_text(
                "trade_date,ticker,volume_shares,source_url\n"
                "2025-05-02,2330,1234001,https://www.twse.com.tw/legacy\n",
                encoding="utf-8-sig",
            )
            # 來源 CSV 只供閱讀；重輸出應以已核對的原始 JSON 重建欄位與單位。
            for source in original_manifest["sources"]:
                (original_run / source["source_csv"]).write_text("unusable source CSV\n", encoding="utf-8")
            original_files = {path.relative_to(original_run): path.read_bytes()
                              for path in original_run.rglob("*") if path.is_file()}
            manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            with patch("etf_agent.history.get_https", side_effect=AssertionError("離線匯出不可發出 HTTP")) as fetch:
                exported = export_history_sample(manifest_path, output)
            fetch.assert_not_called()
            self.assertTrue(exported["success"])
            self.assertEqual(exported["row_count"], 2)
            self.assertNotEqual(exported["run_dir"], original["run_dir"])
            for relative, contents in original_files.items():
                self.assertEqual((original_run / relative).read_bytes(), contents)
            exported_run = Path(exported["run_dir"])
            exported_manifest = json.loads(Path(exported["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(exported_manifest["csv_format_version"], "4.0")
            self.assertEqual(exported_manifest["purpose"], "offline_cached_export")
            self.assertEqual(exported_manifest["network_requests"], 0)
            self.assertEqual(exported_manifest["reexport_of"], {
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": manifest_digest,
                "run_id": original_manifest["run_id"],
            })
            self.assertFalse(exported_manifest["submission_ready"])
            for old_source, new_source in zip(original_manifest["sources"], exported_manifest["sources"], strict=True):
                for key in ("market", "ticker", "fetched_at", "raw_sha256", "requested_url", "effective_url"):
                    self.assertEqual(new_source[key], old_source[key])
                copied_raw = (exported_run / new_source["raw_path"]).read_bytes()
                self.assertEqual(hashlib.sha256(copied_raw).hexdigest(), new_source["raw_sha256"])
                self.assertEqual(copied_raw, (original_run / old_source["raw_path"]).read_bytes())
                payload = sample_payload(new_source["market"])
                table = payload if new_source["market"] == "TWSE" else payload["tables"][0]
                with (exported_run / new_source["source_csv"]).open(encoding="utf-8-sig", newline="") as handle:
                    self.assertEqual(list(csv.reader(handle)), [table["fields"], *table["data"]])
            rows = self.read_daily_rows(exported)
            twse_row = next(row for row in rows if row["market"] == "TWSE")
            tpex_row = next(row for row in rows if row["market"] == "TPEX")
            self.assertEqual(Decimal(twse_row["volume_lots"]), Decimal("1234.001"))
            self.assertEqual(Decimal(twse_row["volume_lots"]) * 1000, Decimal("1234001"))
            self.assertEqual(twse_row["fetched_at"], FETCHED_AT.isoformat())
            self.assertEqual(twse_row["known_at"], "")
            self.assertEqual((tpex_row["volume_lots"], tpex_row["amount_ktwd"]), ("", ""))
            self.assertEqual(Decimal(tpex_row["reported_volume_lots"]), Decimal("1234"))
            self.assertEqual(tpex_row["exact_volume_amount"], "false")

    def test_offline_export_rejects_changed_raw_hash(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            original = download_history_sample("2025-05", output, fetcher=self.fetcher(responses))
            manifest_path = Path(original["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_path = Path(original["run_dir"]) / manifest["sources"][0]["raw_path"]
            raw_path.write_bytes(raw_path.read_bytes() + b" ")
            with patch("etf_agent.history.get_https", side_effect=AssertionError("不可重新抓取來掩蓋證據變動")) as fetch:
                with self.assertRaises(HistoryDataError):
                    export_history_sample(manifest_path, output)
            fetch.assert_not_called()

    def test_offline_export_rejects_missing_source_evidence(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            original = download_history_sample("2025-05", output, fetcher=self.fetcher(responses))
            manifest_path = Path(original["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["sources"][0]["raw_sha256"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with patch("etf_agent.history.get_https", side_effect=AssertionError("不可外部補齊缺漏證據")) as fetch:
                with self.assertRaises(HistoryDataError):
                    export_history_sample(manifest_path, output)
            fetch.assert_not_called()

    def test_offline_export_rejects_raw_missing_price_fields_even_with_matching_hash(self):
        responses = {market: self.good_response(market) for market in ("TWSE", "TPEX")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            original = download_history_sample("2025-05", output, fetcher=self.fetcher(responses))
            manifest_path = Path(original["manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source = manifest["sources"][0]
            raw_path = Path(original["run_dir"]) / source["raw_path"]
            payload = json.loads(raw_path.read_bytes())
            payload["fields"][6] = "未辨識欄位"
            changed_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            raw_path.write_bytes(changed_body)
            source["raw_sha256"] = hashlib.sha256(changed_body).hexdigest()
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with patch("etf_agent.history.get_https", side_effect=AssertionError("不可外部補齊行情欄位")) as fetch:
                try:
                    exported = export_history_sample(manifest_path, output)
                except HistoryDataError:
                    pass
                else:
                    self.assertFalse(exported["success"])
                    rows = self.read_daily_rows(exported)
                    self.assertFalse(any(row["market"] == "TWSE" for row in rows))
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
