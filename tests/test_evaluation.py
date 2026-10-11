"""人工單日fixture：驗證結算、缺成交保留、資料隔離與整數求解。"""

import copy
import csv
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from etf_agent.contracts import AccountSnapshot
from etf_agent.sub_agents.test_agent.evaluation import EvaluationError, simulate, verify_frozen
from etf_agent.sub_agents.test_agent.evaluation_runner import evaluate_frozen_plan
from etf_agent.sub_agents.test_agent.hindsight import optimize_hindsight


def fixtures(count=25):
    tickers = [str(1000+i) for i in range(count)]
    account = {"contract_version": "1.0", "snapshot_id": "ARTIFICIAL_EVAL", "as_of_trade_date": "2025-09-30",
               "status": "demo", "cash_twd": "1000000", "nav_twd": "3500000",
               "positions": [{"ticker": t, "shares": 1000} for t in tickers[:25]],
               "origin": "artificial_unit_test", "reconciled": False, "demo": True, "origin_ref": None}
    previous = {t: "100" for t in tickers}
    quotes = {t: {"ticker": t, "trade_date": "2025-10-01", "close_twd_per_share": "100",
                  "vwap_twd_per_share": "100", "volume_shares": 1000, "amount_twd": "100000"} for t in tickers}
    return account, tickers, previous, quotes


class EvaluationTests(unittest.TestCase):
    def test_vwap_cash_fees_tax_nav_and_skip_attribution(self):
        account, _, previous, quotes = fixtures(26)
        quotes["1000"].update(close_twd_per_share="90", vwap_twd_per_share="95", amount_twd="95000")
        quotes["1025"].update(close_twd_per_share="110", vwap_twd_per_share="105", amount_twd="105000")
        orders = [{"ticker": "1000", "side": "SELL", "shares": 1000},
                  {"ticker": "1025", "side": "BUY", "shares": 1000}]
        result = simulate(account, orders, quotes, trade_date="2025-10-01", previous_closes=previous, scenario="test")
        summary = result["summary"]
        self.assertEqual(Decimal(summary["cash_twd"]), Decimal("989430"))
        self.assertEqual(Decimal(summary["fees_twd"]), Decimal("285"))
        self.assertEqual(Decimal(summary["tax_twd"]), Decimal("285"))
        self.assertEqual(Decimal(summary["end_nav_twd"]), Decimal("3499430"))
        baseline = simulate(account, [], quotes, trade_date="2025-10-01", previous_closes=previous, scenario="base")
        gain = Decimal(summary["end_nav_twd"]) - Decimal(baseline["summary"]["end_nav_twd"])
        self.assertEqual(gain, sum((Decimal(f["benefit_vs_skip_twd"]) for f in result["fills"]), Decimal(0)))
        self.assertEqual(account["cash_twd"], "1000000")
        self.assertEqual(AccountSnapshot.from_dict(result["account_snapshot"]).status, "simulated")

    def test_missing_sell_quote_retains_holding_and_partial_nav_unknown(self):
        account, _, previous, quotes = fixtures()
        del quotes["1000"]
        result = simulate(account, [{"ticker": "1000", "side": "SELL", "shares": 1000}], quotes,
                          trade_date="2025-10-01", previous_closes=previous, scenario="test")
        self.assertEqual(result["fills"][0]["fill_status"], "unfilled_missing_vwap")
        self.assertEqual(result["positions"][0]["end_shares"], 1000)
        self.assertIsNone(result["summary"]["end_nav_twd"])
        self.assertIsNone(result["summary"]["return_ratio"])
        self.assertIsNone(result["account_snapshot"])
        self.assertEqual({r["code"] for r in result["issues"]}, {"order_missing_vwap", "held_missing_close"})

    def test_missing_trade_price_can_still_value_holdings_at_close(self):
        account, _, previous, quotes = fixtures()
        quotes["1000"].update(vwap_twd_per_share=None, amount_twd=None, volume_shares=None)
        result = simulate(account, [{"ticker": "1000", "side": "SELL", "shares": 1000}], quotes,
                          trade_date="2025-10-01", previous_closes=previous, scenario="test")
        self.assertEqual(result["summary"]["filled_orders"], 0)
        self.assertEqual(result["positions"][0]["end_shares"], 1000)
        self.assertEqual(Decimal(result["summary"]["end_nav_twd"]), Decimal("3500000"))

    def test_reject_future_prices_oversell_day_trade_and_bad_vwap(self):
        account, _, previous, quotes = fixtures()
        scenarios = []
        wrong = copy.deepcopy(quotes)
        wrong["1000"]["trade_date"] = "2025-10-02"
        scenarios.append(([], wrong))
        wrong = copy.deepcopy(quotes)
        wrong["1000"]["vwap_twd_per_share"] = "99"
        scenarios.append(([], wrong))
        scenarios.append(([{"ticker": "1000", "side": "SELL", "shares": 2000}], quotes))
        scenarios.append(([{"ticker": "1000", "side": "SELL", "shares": 1000},
                           {"ticker": "1000", "side": "BUY", "shares": 1000}], quotes))
        for orders, prices in scenarios:
            with self.subTest(orders=orders), self.assertRaises(EvaluationError):
                simulate(account, orders, prices, trade_date="2025-10-01", previous_closes=previous, scenario="test")

    def test_gate_rejects_unfrozen_and_hash_tampered_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace.json"
            workspace.write_text(json.dumps({"real_agent_decision": False}), encoding="utf-8")
            with self.assertRaises(EvaluationError):
                verify_frozen(workspace)
            artifact = root / "packet.json"
            artifact.write_text('{}', encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"artifact_sha256": {"packet.json": "wrong"}}), encoding="utf-8")
            workspace.write_text(json.dumps({"real_agent_decision": True, "accepted_demo_plan": True,
                                             "files": {"decision_manifest": "manifest.json", "plan_manifest": "manifest.json"}}), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationError, "hash"):
                verify_frozen(workspace)

    def test_output_inside_decision_tree_blocked_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            frozen = {"root": str(Path(directory).resolve())}
            with patch('etf_agent.sub_agents.test_agent.evaluation_runner.verify_frozen', return_value=frozen), \
                    patch('etf_agent.sub_agents.test_agent.evaluation_runner.get_https') as fetch:
                with self.assertRaises(EvaluationError):
                    evaluate_frozen_plan('artificial_workspace', output_dir=Path(directory) / 'evaluation')
                fetch.assert_not_called()

    def test_isolated_run_csv_matches_json_and_frozen_input_stays_unchanged(self):
        account, tickers, previous, quotes = fixtures(26)
        account.update(cash_twd="500000", nav_twd="3000000")
        for row in quotes.values():
            row.update(name="artificial", market="TWSE", trading_status="traded", source_key="artificial",
                       source_url="https://example.invalid/artificial", raw_sha256="artificial")
        quotes["1025"]["close_twd_per_share"] = "110"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decision = root / 'decision'
            decision.mkdir()
            plan_path = decision / 'plan.json'
            orders = [{"ticker": "1025", "side": "BUY", "shares": 1000}]
            plan_path.write_text(json.dumps({"orders": orders}), encoding='utf-8')
            hashes = {str(plan_path): hashlib.sha256(plan_path.read_bytes()).hexdigest()}
            frozen = {"root": str(decision), "workspace_path": str(decision/'workspace.json'),
                      "files": {"dplan": plan_path}, "as_of": "2025-09-30", "trade_date": "2025-10-01",
                      "account": account, "previous_closes": previous, "frozen_sha256": hashes,
                      "plan": {"orders": orders}, "packet": {"allowed_tickers": tickers}}

            def artificial_market(context, run, **kwargs):
                manifest = {"sources": [], "network_requests": 0, "note": "artificial unit test"}
                (run/'market_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                return copy.deepcopy(quotes), manifest

            with patch('etf_agent.sub_agents.test_agent.evaluation_runner.verify_frozen', return_value=frozen), \
                    patch('etf_agent.sub_agents.test_agent.evaluation_runner._market', side_effect=artificial_market), \
                    patch('etf_agent.sub_agents.test_agent.evaluation_runner.get_https') as fetch:
                result = evaluate_frozen_plan('artificial', output_dir=root/'quarantine', time_limit=5)
                fetch.assert_not_called()
            run = Path(result['run_dir'])
            self.assertEqual(result['hindsight_status'], 'optimal')
            self.assertTrue(result['original_frozen_unchanged'])
            self.assertEqual(hashes[str(plan_path)], hashlib.sha256(plan_path.read_bytes()).hexdigest())
            manifest = json.loads((run/'manifest.json').read_text('utf-8'))
            self.assertFalse(manifest['decision_input_allowed'])
            self.assertEqual(manifest['new_model_calls'], 0)
            for name, expected in manifest['artifact_sha256'].items():
                self.assertEqual(hashlib.sha256((run/name).read_bytes()).hexdigest(), expected)
            self.assertEqual(len(result['csv_files']), 8)
            for name in result['csv_files']:
                self.assertTrue(Path(name).read_bytes().startswith(b'\xef\xbb\xbf'))
            with (run/'performance.csv').open(encoding='utf-8-sig', newline='') as handle:
                self.assertEqual(list(csv.DictReader(handle))[1]['end_nav_twd'], result['scenarios'][1]['end_nav_twd'])
            with (run/'fills.csv').open(encoding='utf-8-sig', newline='') as handle:
                fills = list(csv.DictReader(handle))
                self.assertEqual(sum((Decimal(f['fee_twd']) for f in fills), Decimal(0)),
                                 Decimal(result['scenarios'][1]['fees_twd']))
            with (run/'hindsight_orders.csv').open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
                best = json.loads((run/'hindsight_optimization.json').read_text('utf-8'))
                self.assertEqual([{**r, 'shares': int(r['shares'])} for r in rows], best['orders'])


class HindsightTests(unittest.TestCase):
    def test_full_pool_optimizer_trades_toward_winner_and_passes_decimal_checks(self):
        account, tickers, previous, quotes = fixtures(26)
        account["cash_twd"] = "500000"
        account["nav_twd"] = "3000000"
        quotes["1025"]["close_twd_per_share"] = "110"
        best = optimize_hindsight(account, tickers, previous, quotes, trade_date="2025-10-01", time_limit=5)
        self.assertEqual(best["status"], "optimal", best)
        self.assertEqual(best["candidate_count"], 26)
        self.assertTrue(best["optimal_to_solver_tolerance"])
        self.assertTrue(best["solution"]["constraint_checks_ok"])
        self.assertTrue(all(best["previous_close_checks"].values()))
        self.assertTrue(any(o["ticker"] == "1025" and o["side"] == "BUY" for o in best["orders"]))
        self.assertGreater(Decimal(best["solution"]["summary"]["end_nav_twd"]), Decimal(account["nav_twd"]))

    def test_zero_edge_keeps_all_holdings_without_fee_destroying_trades(self):
        account, tickers, previous, quotes = fixtures(26)
        account.update(cash_twd="500000", nav_twd="3000000")
        best = optimize_hindsight(account, tickers, previous, quotes, trade_date="2025-10-01", time_limit=5)
        self.assertEqual(best["status"], "optimal")
        self.assertEqual(best["orders"], [])
        self.assertEqual(Decimal(best["solution"]["summary"]["profit_twd"]), 0)

    def test_missing_candidate_blocks_full_pool_claim_without_shrinking_pool(self):
        account, tickers, previous, quotes = fixtures(26)
        del quotes["1025"]
        best = optimize_hindsight(account, tickers, previous, quotes, trade_date="2025-10-01", time_limit=5)
        self.assertEqual(best["status"], "blocked_missing_data")
        self.assertEqual(best["candidate_count"], 26)
        self.assertEqual(best["missing_tickers"], ["1025"])
        self.assertFalse(best["optimal_to_solver_tolerance"])

    def test_confirmed_zero_trade_unheld_candidate_remains_in_pool_with_zero_target(self):
        account, tickers, previous, quotes = fixtures(26)
        account.update(cash_twd="500000", nav_twd="3000000")
        quotes["1025"].update(trading_status="no_trade", close_twd_per_share=None,
                              vwap_twd_per_share=None, volume_shares=None, amount_twd=None)
        best = optimize_hindsight(account, tickers, previous, quotes, trade_date="2025-10-01", time_limit=5)
        self.assertEqual(best["status"], "optimal")
        self.assertEqual(best["candidate_count"], 26)
        self.assertEqual(best["tradable_candidate_count"], 25)
        self.assertEqual(best["no_trade_tickers"], ["1025"])
        self.assertEqual(best["target_shares"]["1025"], 0)
        self.assertEqual(best["orders"], [])

    def test_limit_incumbent_is_feasible_without_claiming_proven_optimum(self):
        import numpy as np
        account, tickers, previous, quotes = fixtures(26)
        account.update(cash_twd="500000", nav_twd="3000000")
        x = np.zeros(6 * 26 + 4)
        x[:25] = 1
        x[3 * 26:3 * 26 + 25] = 1
        result = SimpleNamespace(x=x, status=1, message='artificial time limit', mip_gap=0.02,
                                 mip_node_count=1, mip_dual_bound=-3.1)
        with patch('scipy.optimize.milp', return_value=result):
            best = optimize_hindsight(account, tickers, previous, quotes, trade_date='2025-10-01', time_limit=5)
        self.assertEqual(best['status'], 'feasible_limit_reached')
        self.assertFalse(best['optimal_to_solver_tolerance'])
        self.assertTrue(best['solution']['constraint_checks_ok'])
        self.assertEqual(best['solver_upper_bound_nav_twd'], '3100000.0')


if __name__ == '__main__':
    unittest.main()
