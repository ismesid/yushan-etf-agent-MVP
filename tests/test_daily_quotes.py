"""單日全市場解析驗收；價格／股票全部人工，不連網或讀本機行情。"""

import copy
import hashlib
import json
import unittest
from decimal import Decimal, localcontext
from urllib.parse import parse_qs, urlparse

from etf_agent.sub_agents.test_agent.providers.daily import DailyQuotesError, daily_url, parse_daily


def sample(market="TWSE"):
    if market == "TWSE":
        fields = ["證券代號", "證券名稱", "成交股數", "成交金額", "收盤價"]
        table = {"title": "114年10月01日 每日收盤行情", "hints": "單位：元、股", "fields": fields,
                 "data": [["1000", "人工甲", "1,003", "123,456.78", "123.45"]]}
        return {"stat": "OK", "date": "20251001", "params": {"date": "20251001"},
                "tables": [{"title": "指數", "fields": ["指數"], "data": [["人工指數"]]}, table, {}]}
    fields = ["代號", "名稱", "收盤", "均價", "成交股數", "成交金額(元)",
              "最後買量(張數)", "次日 參考價"]
    table = {"title": "上櫃股票行情", "date": "114/10/01", "fields": fields,
             "data": [["1001", "人工乙", "123.45", "123.00", "1,003", "123,456.78", "999", "777"]]}
    return {"stat": "ok", "date": "20251001", "tables": [table, {"title": "管理股票", "fields": fields, "data": []}]}


def encode(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class DailyQuotesTests(unittest.TestCase):
    def test_urls_always_request_one_explicit_day(self):
        for market, day in (("TWSE", "20251001"), ("TPEX", "2025/10/01")):
            parsed = urlparse(daily_url(market, "2025-10-01"))
            self.assertEqual(parse_qs(parsed.query)["date"], [day])
            self.assertNotIn("tradingStock", parsed.path)
            self.assertNotIn("STOCK_DAY", parsed.path)
        for market, day in (("OTHER", "2025-10-01"), ("TWSE", "2025-1-1"), ("TPEX", "2025-02-30")):
            with self.subTest(market=market, day=day), self.assertRaises(DailyQuotesError):
                daily_url(market, day)

    def test_exact_amount_shares_vwap_and_source_ignore_rounded_average_and_bid_lots(self):
        for market, ticker in (("TWSE", "1000"), ("TPEX", "1001")):
            body = encode(sample(market))
            quote = parse_daily(body, market, "2025-10-01")[ticker]
            self.assertEqual(quote["volume_shares"], 1003)
            self.assertEqual(quote["amount_twd"], "123456.78")
            self.assertEqual(quote["close_twd_per_share"], "123.45")
            self.assertEqual(quote["trading_status"], "traded")
            with localcontext() as context:
                context.prec = 50
                self.assertEqual(Decimal(quote["vwap_twd_per_share"]), Decimal("123456.78") / Decimal(1003))
            self.assertEqual(quote["trade_date"], "2025-10-01")
            self.assertEqual(quote["market"], market)
            self.assertEqual(quote["raw_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(quote["source_url"], daily_url(market, "2025-10-01"))
            self.assertTrue(quote["source_key"].startswith(market))
            self.assertNotIn("次日 參考價", quote)

    def test_date_response_params_and_table_mismatch_are_blocked(self):
        for mutation in ("response_date", "params_date", "table_date", "title_date", "stat"):
            payload = sample()
            if mutation == "response_date":
                payload["date"] = "20251002"
            elif mutation == "params_date":
                payload["params"]["date"] = "20251002"
            elif mutation == "table_date":
                payload["tables"][1]["date"] = "20251002"
            elif mutation == "title_date":
                payload["tables"][1]["title"] = "114年10月02日 每日收盤行情"
            else:
                payload["stat"] = "查無資料"
            with self.subTest(mutation=mutation), self.assertRaises(DailyQuotesError):
                parse_daily(encode(payload), "TWSE", "2025-10-01")

    def test_missing_trade_is_preserved_without_zero_or_previous_price(self):
        for market in ("TWSE", "TPEX"):
            payload = sample(market)
            table = payload["tables"][1 if market == "TWSE" else 0]
            names = ("收盤價", "成交股數", "成交金額") if market == "TWSE" else ("收盤", "成交股數", "成交金額(元)")
            for marker in ("---", "0", None):
                changed = copy.deepcopy(payload)
                row = changed["tables"][1 if market == "TWSE" else 0]["data"][0]
                for field in names:
                    row[table["fields"].index(field)] = marker
                quote = next(iter(parse_daily(encode(changed), market, "2025-10-01").values()))
                for key in ("close_twd_per_share", "volume_shares", "amount_twd", "vwap_twd_per_share"):
                    self.assertIsNone(quote[key])
                self.assertEqual(quote["trading_status"], "no_trade" if marker == "0" else "unknown")

    def test_explicit_zero_trade_and_missing_amount_or_volume_have_distinct_status(self):
        for volume, amount, status in (("0", "0", "no_trade"),
                                       (0, 0, "no_trade"),
                                       ("---", "---", "unknown"),
                                       (None, None, "unknown"),
                                       ("0", None, "unknown"),
                                       (None, "0", "unknown")):
            payload = sample("TPEX")
            table = payload["tables"][0]
            row = table["data"][0]
            row[table["fields"].index("代號")] = "3260"
            row[table["fields"].index("收盤")] = "---"
            row[table["fields"].index("成交股數")] = volume
            row[table["fields"].index("成交金額(元)")] = amount
            with self.subTest(volume=volume, amount=amount):
                quote = parse_daily(encode(payload), "TPEX", "2025-10-01")["3260"]
                self.assertEqual(quote["trading_status"], status)
                for key in ("close_twd_per_share", "volume_shares", "amount_twd", "vwap_twd_per_share"):
                    self.assertIsNone(quote[key])

    def test_zero_volume_with_positive_amount_or_reverse_is_blocked(self):
        for volume, amount in (("0", "1000"), ("1000", "0")):
            payload = sample("TPEX")
            table = payload["tables"][0]
            table["data"][0][table["fields"].index("成交股數")] = volume
            table["data"][0][table["fields"].index("成交金額(元)")] = amount
            with self.subTest(volume=volume, amount=amount), self.assertRaisesRegex(DailyQuotesError, "不一致"):
                parse_daily(encode(payload), "TPEX", "2025-10-01")

    def test_all_quote_tables_merge_and_duplicate_tickers_are_blocked(self):
        payload = sample("TPEX")
        row = copy.deepcopy(payload["tables"][0]["data"][0])
        row[0] = "1002"
        payload["tables"][1]["data"] = [row]
        payload["tables"][1]["date"] = "20251001"
        quotes = parse_daily(encode(payload), "TPEX", "2025-10-01")
        self.assertEqual(set(quotes), {"1001", "1002"})
        payload["tables"][1]["data"][0][0] = "1001"
        with self.assertRaisesRegex(DailyQuotesError, "重複"):
            parse_daily(encode(payload), "TPEX", "2025-10-01")

    def test_tpex_actual_roc_table_date_and_empty_undated_management_table(self):
        for empty_date in (None, "absent"):
            payload = sample("TPEX")
            if empty_date is None:
                payload["tables"][1]["date"] = None
            quotes = parse_daily(encode(payload), "TPEX", "2025-10-01")
            self.assertEqual(set(quotes), {"1001"})
            self.assertEqual(quotes["1001"]["trade_date"], "2025-10-01")

    def test_tpex_wrong_or_malformed_roc_table_date_is_blocked(self):
        for returned_date in ("114/10/02", "114/09/30", "114/10/1", "114/02/30", "20251002"):
            payload = sample("TPEX")
            payload["tables"][0]["date"] = returned_date
            with self.subTest(date=returned_date), self.assertRaises(DailyQuotesError):
                parse_daily(encode(payload), "TPEX", "2025-10-01")

    def test_tpex_populated_table_cannot_inherit_date_when_missing(self):
        for returned_date in (None, "absent"):
            payload = sample("TPEX")
            if returned_date is None:
                payload["tables"][0]["date"] = None
            else:
                del payload["tables"][0]["date"]
            with self.subTest(date=returned_date), self.assertRaisesRegex(DailyQuotesError, "缺少日期"):
                parse_daily(encode(payload), "TPEX", "2025-10-01")

    def test_wrong_units_nonintegral_volume_or_nonfinite_values_are_blocked(self):
        for mutation in ("volume_unit", "amount_unit", "hints", "fractional_volume", "invalid_amount", "row_width"):
            payload = sample()
            table = payload["tables"][1]
            if mutation == "volume_unit":
                table["fields"][2] = "成交仟股"
            elif mutation == "amount_unit":
                table["fields"][3] = "成交仟元"
            elif mutation == "hints":
                table["hints"] = "單位：仟元、仟股"
            elif mutation == "fractional_volume":
                table["data"][0][2] = "1.5"
            elif mutation == "invalid_amount":
                table["data"][0][3] = "NaN"
            else:
                table["data"][0].pop()
            with self.subTest(mutation=mutation), self.assertRaises(DailyQuotesError):
                parse_daily(encode(payload), "TWSE", "2025-10-01")


if __name__ == "__main__":
    unittest.main()
