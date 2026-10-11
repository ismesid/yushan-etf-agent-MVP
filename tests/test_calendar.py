"""官方端點可能忽略年度參數：此實際遇到的錯年情境必須阻擋。"""

import json
import unittest

from etf_agent.calendar import CalendarError, parse_schedule


class CalendarTests(unittest.TestCase):
    def test_response_year_must_match_requested_year(self):
        payload = {"stat": "ok", "date": "20250101", "queryYear": 2025,
                   "fields": ["日期", "名稱", "說明"],
                   "data": [["2025-09-29", "教師節補假", "休市一日"]]}
        parsed = parse_schedule(json.dumps(payload).encode(), market="TWSE", year=2025)
        self.assertEqual(parsed[0]["trade_date"], "2025-09-29")
        self.assertFalse(parsed[0]["is_open"])
        payload.update(date="20260101", queryYear=2026)
        with self.assertRaises(CalendarError):
            parse_schedule(json.dumps(payload).encode(), market="TWSE", year=2025)
        # TPEx 的 year 證據在 HTML 標題；endDate 是最新可查範圍，不能當成回應年度。
        tpex = {"stat": "ok", "endDate": "20260101", "data": {"html":
            "<table><tr><td>中華民國114年有價證券櫃檯買賣市場開（休）市日期表</td></tr></table>"
            "<table><tr><th>紀念節日名稱</th><th>日期</th><th>星期</th><th>說明</th></tr>"
            "<tr><td>教師節</td><td>9月28日<br>9月29日</td><td>日 一</td><td>補假</td></tr></table>"}}
        days = parse_schedule(json.dumps(tpex).encode(), market="TPEX", year=2025)
        self.assertEqual([day["trade_date"] for day in days], ["2025-09-28", "2025-09-29"])
        self.assertTrue(all(not day["is_open"] for day in days))
        with self.assertRaises(CalendarError):
            parse_schedule(json.dumps(tpex).encode(), market="TPEX", year=2026)


if __name__ == "__main__":
    unittest.main()
