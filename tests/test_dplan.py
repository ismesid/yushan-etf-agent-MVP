"""編譯與封存驗收，模型、行情與帳戶全部為人工測試資料。"""

import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

from etf_agent.cli import main
from etf_agent.contracts import WeightedAgentDraft
from etf_agent.decision.dplan import compile_dplan, load_prepared_packet, write_compiled_plan
from test_portfolio import fixtures, swap_fixture


ROOT = Path(__file__).resolve().parents[1]


def compiler_fixture(swap=True):
    packet, raw = swap_fixture() if swap else fixtures()
    packet.update(packet_version="1.0", packet_version_id="artificial-packet",
                  scope="historical_demo_decision_input")
    packet["sources"] = [{"source_id": "S7", "authority": "other", "url": "https://example.invalid/artificial",
                          "name": "人工測試來源", "content_as_of_trade_date": "2025-09-30"},
                         {"source_id": "S9", "authority": "other", "url": "https://example.invalid/unused",
                          "name": "未引用測試來源", "content_as_of_trade_date": "2025-09-30"}]
    for observation in packet["observations"]:
        observation.update(source_ref=["S7"], statement="人工fixture股票價格及排名數值，僅測試而非真實行情。",
                           values={"scope": "test", "price": "1000", "stock_count": 26})
    rationale = "人工測試依據股票觀察核對配置，僅驗證完整股數公式與引用鏈，不宣稱真實投資決策。"
    raw["market_proposal"]["rationale"] = rationale
    for row in [*raw["selections"], *raw["held_reviews"]]:
        row["rationale"] = rationale
    metadata = {"model_provider": "other", "model_version": "ARTIFICIAL_UNIT_TEST_MODEL",
                "run_started_at": "2026-10-11T12:00:00+08:00", "run_completed_at": "2026-10-11T12:00:01+08:00",
                "code_version": "artificial-unit-test"}
    return packet, raw, metadata


class DPlanTests(unittest.TestCase):
    @staticmethod
    def read_csv(path):
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return reader.fieldnames, list(reader)

    def test_compiled_csv_swap_matches_orders_costs_positions_and_original_reasons(self):
        packet, raw, metadata = compiler_fixture()
        for role in ("selections", "held_reviews"):
            for row in raw[role]:
                row["rationale"] = f'人工{role}依據 {row["ticker"]} 的股票觀察,保留原文「理由」。\n僅測試引用鏈與配置，並非真實模型判斷。'
                row["counter_evidence"] = f'人工反證 {row["ticker"]},需要保留原文。'
        draft = WeightedAgentDraft.from_dict(raw)
        result = compile_dplan(packet, draft, agent_metadata=metadata)
        self.assertTrue(result["validation"]["local_validation_ok"], result["validation"])
        portfolio = result["portfolio"]
        with tempfile.TemporaryDirectory() as directory:
            outputs = write_compiled_plan(result, directory, project_root=ROOT, packet=packet, draft=draft)
            manifest = json.loads(Path(outputs["manifest_json"]).read_text(encoding="utf-8"))
            csv_keys = ("agent_decisions_csv", "orders_csv", "portfolio_positions_csv",
                        "portfolio_summary_csv", "validation_checks_csv")
            for key in csv_keys:
                with self.subTest(view=key):
                    path = Path(outputs[key])
                    body = path.read_bytes()
                    self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
                    self.assertEqual(hashlib.sha256(body).hexdigest(), manifest["artifact_sha256"][path.name])
            _, orders = self.read_csv(outputs["orders_csv"])
            self.assertEqual([{key: int(row[key]) if key == "shares" else row[key]
                               for key in ("ticker", "side", "shares", "decision_ref")}
                              for row in orders], portfolio["orders"])
            for side, total_key in (("BUY", "buy_notional_twd"), ("SELL", "sell_notional_twd")):
                self.assertEqual(sum((Decimal(row["estimated_notional_twd"]) for row in orders
                                      if row["side"] == side), Decimal(0)), Decimal(portfolio[total_key]))
            for field, total_key in (("estimated_fee_twd", "fees_twd"), ("estimated_tax_twd", "tax_twd")):
                self.assertEqual(sum((Decimal(row[field]) for row in orders), Decimal(0)),
                                 Decimal(portfolio[total_key]))
            for row in orders:
                notional = Decimal(row["close_twd_per_share"]) * int(row["shares"])
                self.assertEqual(Decimal(row["estimated_notional_twd"]), notional)
                self.assertEqual(Decimal(row["estimated_fee_twd"]), notional * Decimal("0.001425"))
                self.assertEqual(Decimal(row["estimated_tax_twd"]),
                                 notional * Decimal("0.003") if row["side"] == "SELL" else Decimal(0))
                self.assertEqual(row["price_basis"], "previous_close_estimate")
            _, positions = self.read_csv(outputs["portfolio_positions_csv"])
            exited = next(row for row in positions if row["ticker"] == "1000")
            self.assertEqual(int(exited["current_shares"]), 35000)
            self.assertEqual(int(exited["target_shares"]), 0)
            self.assertEqual(Decimal(exited["target_market_value_twd"]), Decimal(0))
            self.assertEqual({row["ticker"] for row in positions},
                             {row["ticker"] for row in portfolio["positions"]})
            _, decisions = self.read_csv(outputs["agent_decisions_csv"])
            self.assertEqual(next(row["action"] for row in decisions if row["ticker"] == "1000"), "SELL_ALL")
            for role, prefix in (("selections", "selection"), ("held_reviews", "held_review")):
                expected = {row["ticker"]: row for row in raw[role]}
                counter_field = "selection_counter_evidence" if role == "selections" else "held_counter_evidence"
                for row in decisions:
                    original = expected.get(row["ticker"], {})
                    self.assertEqual(row[f"{prefix}_rationale"], original.get("rationale", ""))
                    self.assertEqual(row[counter_field], original.get("counter_evidence", ""))

    def test_compiled_csv_no_orders_preserves_headers_all_keep_and_summary_money(self):
        packet, raw, metadata = compiler_fixture(swap=False)
        draft = WeightedAgentDraft.from_dict(raw)
        result = compile_dplan(packet, draft, agent_metadata=metadata)
        self.assertTrue(result["validation"]["local_validation_ok"], result["validation"])
        portfolio = result["portfolio"]
        with tempfile.TemporaryDirectory() as directory:
            outputs = write_compiled_plan(result, directory, project_root=ROOT, packet=packet, draft=draft)
            headers, orders = self.read_csv(outputs["orders_csv"])
            self.assertIn("shares", headers)
            self.assertIn("decision_ref", headers)
            self.assertEqual(orders, [])
            self.assertEqual(portfolio["orders"], [])
            _, decisions = self.read_csv(outputs["agent_decisions_csv"])
            self.assertEqual(len(decisions), 25)
            self.assertEqual(len(portfolio["no_trade_tickers"]), 25)
            self.assertEqual({row["ticker"] for row in decisions}, set(portfolio["no_trade_tickers"]))
            self.assertTrue(all(row["action"] == "KEEP" for row in decisions))
            self.assertTrue(all(row["current_shares"] == row["target_shares"] for row in decisions))
            _, summaries = self.read_csv(outputs["portfolio_summary_csv"])
            self.assertEqual(len(summaries), 1)
            summary = summaries[0]
            for key in ("cash_before_twd", "buy_notional_twd", "sell_notional_twd", "fees_twd",
                        "tax_twd", "cash_after_twd", "projected_nav_twd", "net_flow_twd", "cash_ratio"):
                self.assertEqual(Decimal(summary[key]), Decimal(portfolio[key]))
            self.assertEqual(summary["order_count"], "0")
            self.assertEqual(summary["no_trade_count"], "25")
            self.assertEqual(summary["original_holdings_count"], "25")
            self.assertEqual(summary["projected_holdings_count"], "25")
            self.assertEqual(summary["demo"], "true")
            self.assertEqual(summary["submission_ready"], "false")

    def test_compile_prunes_sources_and_preserves_reasons_and_whole_holdings(self):
        packet, raw, metadata = compiler_fixture()
        before = copy.deepcopy(packet)
        result = compile_dplan(packet, WeightedAgentDraft.from_dict(raw), agent_metadata=metadata)
        self.assertTrue(result["validation"]["local_validation_ok"], result["validation"])
        plan = result["plan"]
        self.assertEqual([s["source_id"] for s in plan["sources"]], ["S1"])
        self.assertEqual(len(plan["observations"]), 27)
        self.assertEqual(len(plan["orders"]), 4)
        self.assertEqual(len(plan["no_trade_decisions"]), 22)
        self.assertEqual([d["action"] for d in plan["decisions"]], ["SELL_ALL", "TRIM", "ADD", "BUY"])
        self.assertEqual(plan["inferences"][0]["logic"], raw["held_reviews"][0]["rationale"])
        self.assertFalse(result["real_agent_decision"])
        self.assertFalse(result["submission_ready"])
        self.assertEqual(packet, before)

    def test_missing_actual_model_metadata_blocks_without_fabrication(self):
        packet, raw, _ = compiler_fixture()
        result = compile_dplan(packet, WeightedAgentDraft.from_dict(raw))
        self.assertEqual(result["plan"]["agent_metadata"], {})
        self.assertFalse(result["validation"]["schema_ok"])
        self.assertFalse(result["validation"]["local_validation_ok"])

    def test_official_number_serialization_cannot_change_floor_silently(self):
        packet, raw, metadata = compiler_fixture(swap=False)
        raw["selections"][0]["target_weight"] = "0.0349999999999999999999999999999999999"
        raw["selections"][1]["target_weight"] = "0.0350000000000000000000000000000000001"
        raw["held_reviews"][0]["intent"] = "rebalance"
        result = compile_dplan(packet, WeightedAgentDraft.from_dict(raw), agent_metadata=metadata)
        self.assertTrue(result["portfolio"]["portfolio_ok"], result["portfolio"])
        self.assertFalse(result["validation"]["semantic_ok"])
        self.assertFalse(result["validation"]["local_validation_ok"])

    def test_keep_intent_block_cannot_be_hidden_by_no_trade_plan(self):
        packet, raw, metadata = compiler_fixture(swap=False)
        raw["selections"][0]["target_weight"] = "0.036"
        raw["selections"][1]["target_weight"] = "0.034"
        result = compile_dplan(packet, WeightedAgentDraft.from_dict(raw), agent_metadata=metadata)
        self.assertFalse(result["portfolio"]["portfolio_ok"])
        self.assertFalse(result["validation"]["local_validation_ok"])
        self.assertIn("portfolio_gate", {row["code"] for row in result["validation"]["issues"]})

    def test_write_artificial_candidate_and_archive_actual_dirty_code(self):
        packet, raw, metadata = compiler_fixture()
        draft = WeightedAgentDraft.from_dict(raw)
        result = compile_dplan(packet, draft, agent_metadata=metadata)
        with tempfile.TemporaryDirectory() as directory:
            outputs = write_compiled_plan(result, directory, project_root=ROOT, packet=packet, draft=draft)
            self.assertEqual(Path(outputs["plan_json"]).name, "dplan_candidate.json")
            self.assertFalse(outputs["accepted_demo_plan"])
            markdown = Path(outputs["plan_markdown"])
            self.assertEqual(markdown.name, "dplan_candidate.md")
            self.assertIn("BLOCK", markdown.read_text(encoding="utf-8"))
            manifest = json.loads(Path(outputs["manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["plan_markdown_file"], markdown.name)
            workspace = json.loads(Path(outputs["workspace_json"]).read_text(encoding="utf-8"))
            self.assertEqual(workspace["files"]["plan_markdown"], markdown.name)
            self.assertFalse(any(name.endswith(".md_csv") for name in workspace["files"]))
            self.assertTrue(manifest["code_archive"]["code_version"].startswith("sha256:"))
            for name, digest in manifest["artifact_sha256"].items():
                self.assertEqual(hashlib.sha256((Path(outputs["run_dir"]) / name).read_bytes()).hexdigest(), digest)
            code = Path(outputs["run_dir"]) / "code"
            for name, digest in manifest["code_archive"]["files_sha256"].items():
                self.assertEqual(hashlib.sha256((code / name).read_bytes()).hexdigest(), digest)

    def test_cli_saves_block_diagnosis_for_absent_model(self):
        packet, raw, _ = compiler_fixture()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            packet_path, draft_path = folder / "evidence_packet.json", folder / "draft.json"
            body = json.dumps(packet).encode()
            packet_path.write_bytes(body)
            draft_path.write_text(json.dumps(raw), encoding="utf-8")
            schema_path = folder / "weighted_agent_draft.schema.json"
            schema_body = (ROOT / "specs/internal/weighted_agent_draft.schema.json").read_bytes()
            schema_path.write_bytes(schema_body)
            (folder / "manifest.json").write_text(json.dumps({"packet_version_id": packet["packet_version_id"],
                "as_of": packet["as_of"], "trade_date": packet["trade_date"], "artifact_sha256": {
                packet_path.name: hashlib.sha256(body).hexdigest(), schema_path.name: hashlib.sha256(schema_body).hexdigest()}}), encoding="utf-8")
            self.assertEqual(load_prepared_packet(packet_path), packet)
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main(["compile-plan", "--packet", str(packet_path), "--draft", str(draft_path),
                             "--output", str(folder / "plans"), "--json"])
            self.assertEqual(code, 4)
            saved = json.loads(stream.getvalue())
            self.assertFalse(saved["result"]["validation"]["local_validation_ok"])
            self.assertTrue(Path(saved["outputs"]["validation_json"]).is_file())


if __name__ == "__main__":
    unittest.main()
