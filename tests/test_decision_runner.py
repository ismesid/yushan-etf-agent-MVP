"""Decision orchestration uses synthetic AgentResult objects, never models."""

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from etf_agent.decision import runner as decision_runner
from etf_agent.decision.providers.base import AgentResult
from etf_agent.decision.providers.codex_cli import CodexProviderError
from etf_agent.contracts import WeightedAgentDraft
from etf_agent.decision.dplan import DPlanError
from test_dplan import ROOT, compiler_fixture


class DecisionRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.packet, self.raw, self.metadata = compiler_fixture(swap=False)
        self.packet_path = self.directory / "evidence_packet.json"
        self.packet_body = json.dumps(self.packet, ensure_ascii=False).encode("utf-8")
        self.packet_path.write_bytes(self.packet_body)
        schema_body = (ROOT / "specs/internal/weighted_agent_draft.schema.json").read_bytes()
        (self.directory / "weighted_agent_draft.schema.json").write_bytes(schema_body)
        (self.directory / "decision.md").write_text("Synthetic prompt: use only the supplied packet.", encoding="utf-8")
        artifacts = {name: hashlib.sha256((self.directory / name).read_bytes()).hexdigest() for name in
                     ("evidence_packet.json", "weighted_agent_draft.schema.json", "decision.md")}
        (self.directory / "manifest.json").write_text(json.dumps({
            "packet_version_id": self.packet["packet_version_id"], "as_of": self.packet["as_of"],
            "trade_date": self.packet["trade_date"], "artifact_sha256": artifacts,
        }), encoding="utf-8")
        self.arguments = {"output_dir": self.directory / "outputs", "project_root": ROOT}
        self.code = {"code_version": "sha256:artificial-code", "files_sha256": {"fake.py": "a" * 64}}

    def result(self, raw):
        return AgentResult(
            draft=WeightedAgentDraft.from_dict(raw), provider="openai",
            actual_model_version="ARTIFICIAL_UNIT_TEST_MODEL",
            started_at=datetime.fromisoformat(self.metadata["run_started_at"]),
            completed_at=datetime.fromisoformat(self.metadata["run_completed_at"]),
            usage=None, raw_response_path=None, log_path=None,
        )

    def invalid_financial_draft(self):
        raw = copy.deepcopy(self.raw)
        raw["selections"][0]["target_weight"] = "0.036"
        raw["selections"][1]["target_weight"] = "0.034"
        return raw

    def run_mock(self, provider, *, archive=None):
        def write(compiled, output, **kwargs):
            return {"accepted_demo_plan": compiled["validation"]["local_validation_ok"],
                    "run_dir": str(output)}
        with patch.object(decision_runner, "archive_code", side_effect=archive,
                          return_value=self.code), \
                patch.object(decision_runner, "write_compiled_plan", side_effect=write) as writer:
            report = decision_runner.decide_plan(self.packet_path, provider=provider, **self.arguments)
            return report, writer

    def test_invalid_finance_is_limited_to_two_calls_and_never_accepted(self):
        provider = Mock()
        provider.generate.return_value = self.result(self.invalid_financial_draft())
        report, _ = self.run_mock(provider)
        self.assertEqual(provider.generate.call_count, 2)
        self.assertEqual(len(report["attempts"]), 2)
        self.assertFalse(report["accepted_demo_plan"])
        self.assertTrue(all(row["status"] == "validation_blocked" for row in report["attempts"]))
        self.assertEqual(self.packet_path.read_bytes(), self.packet_body)
        self.assertEqual(provider.generate.call_args_list[0].args[0],
                         provider.generate.call_args_list[1].args[0])
        self.assertEqual(provider.generate.call_args_list[0].args[0], self.packet)

    def test_financial_repair_changes_only_draft_and_preserves_original_packet(self):
        provider = Mock()
        provider.generate.side_effect = [self.result(self.invalid_financial_draft()), self.result(self.raw)]
        report, writer = self.run_mock(provider)
        self.assertEqual(provider.generate.call_count, 2)
        self.assertTrue(report["accepted_demo_plan"])
        self.assertEqual(report["attempts"][0]["status"], "validation_blocked")
        repair_path = Path(report["attempts"][1]["directory"]) / "repair_context.json"
        feedback = json.loads(repair_path.read_text(encoding="utf-8"))
        self.assertIn("keep_target_mismatch", {item["code"] for item in feedback["portfolio_issues"]})
        self.assertEqual(self.packet_path.read_bytes(), self.packet_body)
        self.assertNotIn("agent_metadata", self.packet)
        self.assertFalse(report["submission_ready"])
        expected_directory = self.arguments["output_dir"].resolve() / "compiled"
        self.assertTrue(all(call.args[1] == expected_directory for call in writer.call_args_list))

    def test_archive_io_failure_is_reported_without_retry_or_acceptance(self):
        provider = Mock()
        provider.generate.return_value = self.result(self.raw)
        with patch.object(decision_runner, "archive_code", return_value=self.code), \
                patch.object(decision_runner, "write_compiled_plan", side_effect=OSError("synthetic path failure")):
            report = decision_runner.decide_plan(self.packet_path, provider=provider, **self.arguments)
        self.assertEqual(provider.generate.call_count, 1)
        self.assertFalse(report["accepted_demo_plan"])
        self.assertEqual(report["attempts"][0]["status"], "archive_or_io_failed")
        saved = json.loads(Path(report["report_json"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["attempts"][0]["status"], "archive_or_io_failed")

    def test_shared_workspace_points_to_hashed_markdown_from_same_plan(self):
        workspace = self.directory / "workspace.json"
        workspace.write_text(json.dumps({"files": {}}), encoding="utf-8")
        self.packet["refresh_workspace"] = {"run_root": str(self.directory), "workspace_json": str(workspace)}
        self.packet_body = json.dumps(self.packet, ensure_ascii=False).encode("utf-8")
        self.packet_path.write_bytes(self.packet_body)
        manifest_path = self.packet_path.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifact_sha256"][self.packet_path.name] = hashlib.sha256(self.packet_body).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        provider = Mock()
        provider.generate.return_value = self.result(self.raw)
        report = decision_runner.decide_plan(self.packet_path, provider=provider, **self.arguments)
        self.assertTrue(report["accepted_demo_plan"])
        provider.generate.assert_called_once()
        indexed = json.loads(workspace.read_text(encoding="utf-8"))["files"]["plan_markdown"]
        self.assertFalse(Path(indexed).is_absolute())
        markdown = self.directory / indexed
        self.assertEqual(markdown, Path(report["outputs"]["plan_markdown"]))
        saved = json.loads(Path(report["outputs"]["manifest_json"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["artifact_sha256"][markdown.name], hashlib.sha256(markdown.read_bytes()).hexdigest())
        self.assertEqual(self.packet_path.read_bytes(), self.packet_body)

    def test_tool_and_network_failures_are_not_retried(self):
        for kind in ("tool", "network"):
            with self.subTest(kind=kind):
                provider = Mock()

                def reject(packet, schema, directory):
                    if kind == "tool":
                        (directory / "raw_response.json").write_text("{}", encoding="utf-8")
                        events = [{"type": "item.completed", "item": {"type": "command_execution"}},
                                  {"type": "turn.completed"}]
                        (directory / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
                        (directory / "codex_execution.json").write_text('{"status":"rejected"}', encoding="utf-8")
                    raise CodexProviderError("Synthetic tool or connection rejection")

                provider.generate.side_effect = reject
                report, writer = self.run_mock(provider)
                self.assertEqual(provider.generate.call_count, 1)
                self.assertFalse(report["accepted_demo_plan"])
                writer.assert_not_called()

    def test_frozen_hash_mismatch_prevents_any_model_call(self):
        self.packet_path.write_bytes(self.packet_body + b" ")
        provider = Mock()
        with self.assertRaises((DPlanError, decision_runner.DecisionRunError)):
            decision_runner.decide_plan(self.packet_path, provider=provider, **self.arguments)
        provider.generate.assert_not_called()

    def test_code_change_during_model_call_blocks_compilation(self):
        provider = Mock()
        provider.generate.return_value = self.result(self.raw)
        after = {**self.code, "code_version": "sha256:changed"}
        report, writer = self.run_mock(provider, archive=[self.code, after])
        self.assertEqual(provider.generate.call_count, 1)
        self.assertEqual(report["attempts"][0]["status"], "input_or_code_changed")
        self.assertFalse(report["accepted_demo_plan"])
        writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
