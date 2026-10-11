"""本地 D-Plan 驗證；帳戶、價格、理由與模型名稱均為人工測試資料。"""

import copy
import json
import unittest
from pathlib import Path

from etf_agent.decision.validation import validate_dplan, validate_structure


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    tickers = ["2330", *[str(1100 + i) for i in range(19)]]
    metadata = {"model_provider": "other", "model_version": "synthetic-unit-test",
                "run_started_at": "2026-10-11T18:00:00+08:00",
                "run_completed_at": "2026-10-11T18:00:01+08:00", "code_version": "unit-test"}
    packet = {"as_of": "2025-09-30", "trade_date": "2025-10-01", "allowed_tickers": tickers,
              "account_snapshot": {"as_of_trade_date": "2025-09-30", "nav_twd": "2500000",
                                   "cash_twd": "500000", "positions": [{"ticker": t, "shares": 1000} for t in tickers]},
              "data_report": {"rankings": [{"ticker": t, "close_twd_per_share": "100"} for t in tickers]},
              "agent_metadata": metadata}
    plan = {"schema_version": "4.2", "doc_type": "D-Plan", "team_id": "SYNTHETIC_TEST",
            "trade_date": "2025-10-01",
            "sources": [{"source_id": "S1", "authority": "twse", "url": "https://www.twse.com.tw/",
                         "content_as_of": "2025-09-30T00:00:00+08:00"}],
            "observations": [{"obs_id": "O1", "source_ref": ["S1"],
                              "statement": "人工測試價格100元，不是真實行情", "values": {"test_price": 100}}],
            "market_view": {"basis_refs": ["O1"], "logic": "依人工測試資料驗證淨買情境與現金區間，本資料只供驗證程式並不代表真實市場判斷。", "regime": "neutral",
                            "stance": "neutral", "posture": {"net_exposure_intent": "increase",
                            "target_cash_pct_range": [0.1, 0.25]}, "counter_evidence": None},
            "inferences": [{"inf_id": "I1", "premise_refs": ["O1"], "logic": "依人工測試價格驗證加碼與續抱的股數推導，此情境用於核對機械計算及完整帳戶覆蓋。",
                            "counter_evidence": None}],
            "decisions": [{"decision_id": "D1", "ticker": "2330", "action": "ADD",
                           "target_weight": 0.08, "inference_refs": ["I1"]}],
            "no_trade_decisions": [{"ticker": t, "reason_refs": ["I1"]} for t in tickers if t != "2330"],
            "orders": [{"ticker": "2330", "side": "BUY", "shares": 1000, "decision_ref": "D1"}],
            "agent_metadata": metadata.copy()}
    return packet, plan


class ValidationTests(unittest.TestCase):
    def test_official_examples_structure_and_negative_orphan_i9(self):
        positive = json.loads((ROOT / "specs/official/08_D-Plan_positive_example_v4.2.json").read_text(encoding="utf-8"))
        negative = json.loads((ROOT / "specs/official/09_D-Plan_negative_example_v4.2.json").read_text(encoding="utf-8"))
        for plan in (positive, negative):
            self.assertTrue(all(row["severity"] == "PASS" for row in validate_structure(plan)))
        packet, _ = fixture()
        packet["trade_date"], packet["as_of"] = negative["trade_date"], "2026-10-26"
        result = validate_dplan(negative, packet)
        self.assertTrue(result["schema_ok"])
        self.assertFalse(result["semantic_ok"])
        self.assertTrue(any(row["code"] == "reference_chain" and "I9" in row["message"] for row in result["issues"]))

    def test_valid_synthetic_plan_keeps_demo_and_real_execution_dates(self):
        packet, plan = fixture()
        original = copy.deepcopy((packet, plan))
        result = validate_dplan(plan, packet)
        self.assertTrue(result["schema_ok"] and result["semantic_ok"] and result["local_validation_ok"], result["issues"])
        self.assertFalse(result["submission_ready"])
        self.assertEqual(result["scope"], "dplan_local")
        self.assertEqual((packet, plan), original)

    def test_frozen_facts_match_after_reindex_and_reject_modified_numbers_or_sources(self):
        packet, plan = fixture()
        packet["sources"] = [{**plan["sources"][0], "source_id": "S7"},
                             {**plan["sources"][0], "source_id": "S8", "authority": "tpex"}]
        packet["observations"] = [{**plan["observations"][0], "obs_id": "O9", "source_ref": ["S7"],
                                    "statement": plan["observations"][0]["statement"] + " 人工期初持股 1000 股。",
                                    "values": {"test_price": "100", "scope": "synthetic_test"}}]
        normal = validate_dplan(plan, packet)
        self.assertTrue(normal["local_validation_ok"], normal["issues"])
        for kind in ("number", "statement", "source_url", "source_authority", "source_ref"):
            changed = copy.deepcopy(plan)
            if kind == "number": changed["observations"][0]["values"]["test_price"] = 101
            elif kind == "statement": changed["observations"][0]["statement"] += "虛構訊息"
            elif kind == "source_url": changed["sources"][0]["url"] = "https://www.twse.com.tw/changed"
            elif kind == "source_authority": changed["sources"][0]["authority"] = "other"
            else: changed["sources"][0]["authority"] = "tpex"
            with self.subTest(kind=kind):
                result = validate_dplan(changed, packet)
                self.assertTrue(result["schema_ok"])
                self.assertFalse(result["semantic_ok"])
                self.assertTrue(any(row["code"] in ("frozen_source", "frozen_observation") for row in result["issues"]))

    def test_missing_duplicate_or_overlapping_held_review_blocks(self):
        packet, plan = fixture()
        for kind in ("missing", "duplicate", "overlap"):
            wrong = copy.deepcopy(plan)
            if kind == "missing":
                wrong["no_trade_decisions"].pop()
            elif kind == "duplicate":
                wrong["no_trade_decisions"].append(copy.deepcopy(wrong["no_trade_decisions"][0]))
            else:
                wrong["no_trade_decisions"].append({"ticker": "2330", "reason_refs": ["I1"]})
            with self.subTest(kind=kind):
                self.assertFalse(validate_dplan(wrong, packet)["semantic_ok"])

    def test_mutated_oversell_recomputes_and_does_not_trust_original_portfolio(self):
        packet, plan = fixture()
        plan["decisions"][0].update(action="SELL_ALL", target_weight=0)
        plan["orders"][0].update(side="SELL", shares=2000)
        result = validate_dplan(plan, packet, portfolio={"portfolio_ok": True})
        self.assertFalse(result["semantic_ok"])
        self.assertTrue(any(row["code"] == "no_oversell" for row in result["issues"]))

    def test_invalid_dates_numbers_empty_metadata_and_time_order_block_structure(self):
        _, normal = fixture()
        changes = []
        bad = copy.deepcopy(normal); bad["trade_date"] = "2025-02-30"; changes.append(bad)
        bad = copy.deepcopy(normal); bad["sources"][0]["content_as_of"] = "2025-02-30T12:00:00+08:00"; changes.append(bad)
        bad = copy.deepcopy(normal); bad["agent_metadata"]["run_started_at"] = "2026-10-11T18:00:00+00:00"; changes.append(bad)
        bad = copy.deepcopy(normal); bad["agent_metadata"]["run_completed_at"] = "2026-10-11T17:59:59+08:00"; changes.append(bad)
        bad = copy.deepcopy(normal); bad["decisions"][0]["target_weight"] = "0.08"; changes.append(bad)
        bad = copy.deepcopy(normal); bad["orders"][0]["shares"] = True; changes.append(bad)
        bad = copy.deepcopy(normal); bad["orders"][0]["shares"] = 0; changes.append(bad)
        bad = copy.deepcopy(normal); bad["observations"][0]["values"]["test_price"] = float("nan"); changes.append(bad)
        bad = copy.deepcopy(normal); bad["agent_metadata"] = {}; changes.append(bad)
        for index, bad in enumerate(changes):
            with self.subTest(index=index):
                self.assertTrue(any(row["severity"] == "BLOCK" for row in validate_structure(bad)))

    def test_reference_sequence_whitelist_formula_and_source_cutoff_errors_block(self):
        packet, normal = fixture()
        for kind in ("orphan", "sequence", "whitelist", "formula", "future_source", "keep_order"):
            bad = copy.deepcopy(normal)
            if kind == "orphan": bad["decisions"][0]["inference_refs"] = ["I9"]
            elif kind == "sequence": bad["observations"][0]["obs_id"] = "O2"
            elif kind == "whitelist": bad["decisions"][0]["ticker"] = "9999"
            elif kind == "formula": bad["orders"][0]["shares"] = 2000
            elif kind == "future_source": bad["sources"][0]["content_as_of"] = "2025-10-01T00:00:00+08:00"
            else: bad["orders"][0]["ticker"] = bad["no_trade_decisions"][0]["ticker"]
            with self.subTest(kind=kind):
                result = validate_dplan(bad, packet)
                self.assertTrue(result["schema_ok"])
                self.assertFalse(result["semantic_ok"])

    def test_funding_labels_require_real_shortfall_and_buy_reference(self):
        packet, plan = fixture()
        packet["allowed_tickers"].append("2891")
        packet["data_report"]["rankings"].append({"ticker": "2891", "close_twd_per_share": "100"})
        plan["decisions"] = [{"decision_id": "D1", "ticker": "2891", "action": "BUY", "target_weight": 0.08,
                              "inference_refs": ["I1"]},
                             {"decision_id": "D2", "ticker": "1100", "action": "SELL_ALL", "target_weight": 0,
                              "inference_refs": ["I1"], "funding_for": ["D1"]}]
        plan["orders"] = [{"ticker": "2891", "side": "BUY", "shares": 2000, "decision_ref": "D1"},
                          {"ticker": "1100", "side": "SELL", "shares": 1000, "decision_ref": "D2"}]
        plan["no_trade_decisions"] = [{"ticker": row["ticker"], "reason_refs": ["I1"]}
                                      for row in packet["account_snapshot"]["positions"] if row["ticker"] != "1100"]
        plan["market_view"]["posture"]["target_cash_pct_range"] = [0.15, 0.25]
        result = validate_dplan(plan, packet)
        self.assertTrue(result["local_validation_ok"], result["issues"])
        enough_cash = copy.deepcopy(plan)
        enough_cash["market_view"]["posture"]["target_cash_pct_range"] = [0.1, 0.25]
        self.assertTrue(any(row["code"] == "funding_shortfall" for row in validate_dplan(enough_cash, packet)["issues"]))
        wrong_ref = copy.deepcopy(plan)
        wrong_ref["decisions"][1]["funding_for"] = ["D2"]
        self.assertTrue(any(row["code"] == "funding_refs" for row in validate_dplan(wrong_ref, packet)["issues"]))


if __name__ == "__main__":
    unittest.main()
