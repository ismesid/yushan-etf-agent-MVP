"""Codex provider的假subprocess測試；不呼叫模型或網路。"""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from etf_agent.decision.providers.codex_cli import CodexProvider, CodexProviderError, read_configured_model


ROOT = Path(__file__).resolve().parents[1]


class CodexProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        fixture = json.loads((ROOT / "tests/fixtures/contracts_demo.json").read_text(encoding="utf-8"))
        self.raw = copy.deepcopy(fixture["agent_draft"])
        self.raw["contract_version"] = "2.0"
        weights = {row["ticker"]: row["target_weight"] for row in fixture["portfolio_proposal"]["targets"]}
        for selection in self.raw["selections"]:
            del selection["conviction"]
            selection["target_weight"] = weights[selection["ticker"]]
        self.packet = {"allowed_tickers": list(weights), "held_tickers": list(weights),
                       "observations": [{"obs_id": f"O{i}"} for i in range(1, 26)],
                       "data_report": {"profile": {"weights": "artificial-profile"}, "rankings": []},
                       "scope": "artificial_provider_test"}
        self.schema = json.loads((ROOT / "specs/internal/weighted_agent_draft.schema.json").read_text(encoding="utf-8"))
        self.calls = []

    def runner(self, command, **kwargs):
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.145.0\n", "")
        self.calls.append((command, kwargs))
        response = Path(command[command.index("--output-last-message") + 1])
        response.write_text(json.dumps(self.raw), encoding="utf-8")
        events = [{"type": "thread.started", "thread_id": "artificial-thread"},
                  {"type": "item.completed", "item": {"type": "agent_message", "text": "artificial"}},
                  {"type": "turn.completed", "usage": {"input_tokens": 123, "output_tokens": 45}}]
        return subprocess.CompletedProcess(command, 0, "\n".join(json.dumps(event) for event in events), "")

    def provider(self, runner=None):
        return CodexProvider(model="artificial-explicit-model-id", command=["artificial-codex-executable"],
                             runner=runner or self.runner)

    def test_success_uses_stdin_read_only_and_real_event_usage_without_snapshot_claim(self):
        result = self.provider().generate(self.packet, self.schema, self.directory)
        self.assertEqual(len(self.calls), 1)
        command, kwargs = self.calls[0]
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("features.shell_tool=false", command)
        self.assertIn('web_search="disabled"', command)
        self.assertIn("artificial-profile", kwargs["input"])
        remote = json.loads(Path(command[command.index("--output-schema") + 1]).read_text(encoding="utf-8"))
        original = json.loads((self.directory / "provider_schema.json").read_text(encoding="utf-8"))
        self.assertEqual(original["properties"]["contract_version"]["const"], "2.0")
        self.assertEqual(remote["properties"]["contract_version"]["enum"], ["2.0"])
        self.assertNotIn("uniqueItems", remote["$defs"]["observation_refs"])
        self.assertNotIn("minLength", remote["$defs"]["weighted_selection"]["properties"]["rationale"])
        self.assertEqual(result.actual_model_version, "artificial-explicit-model-id")
        self.assertEqual(result.usage, {"input_tokens": 123, "output_tokens": 45})
        log = json.loads(Path(result.log_path).read_text(encoding="utf-8"))
        self.assertEqual(log["model_identity_basis"], "explicit_cli_model_id")
        self.assertIsNone(log["resolved_snapshot"])
        self.assertEqual(log["input_sha256"], log["input_sha256_after"])
        self.assertTrue((self.directory / "events.jsonl").is_file())

    def test_timeout_preserves_partial_events_and_does_not_retry(self):
        def timeout_runner(command, **kwargs):
            if command[-1] == "--version":
                return self.runner(command, **kwargs)
            self.calls.append((command, kwargs))
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial event", stderr="timeout fixture")
        with self.assertRaises(CodexProviderError):
            self.provider(timeout_runner).generate(self.packet, self.schema, self.directory)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.directory / "events.jsonl").read_text(encoding="utf-8"), "partial event")
        self.assertEqual(json.loads((self.directory / "codex_execution.json").read_text(encoding="utf-8"))["status"], "timeout")

    def test_invalid_final_json_is_rejected_and_raw_response_is_preserved(self):
        def invalid_runner(command, **kwargs):
            result = self.runner(command, **kwargs)
            if command[-1] != "--version":
                Path(command[command.index("--output-last-message") + 1]).write_text("{invalid", encoding="utf-8")
            return result
        with self.assertRaises(CodexProviderError):
            self.provider(invalid_runner).generate(self.packet, self.schema, self.directory)
        self.assertEqual((self.directory / "raw_response.json").read_text(), "{invalid")

    def test_tool_execution_event_rejects_whole_result(self):
        def tool_runner(command, **kwargs):
            result = self.runner(command, **kwargs)
            if command[-1] != "--version":
                result.stdout = json.dumps({"type": "item.started", "item": {"type": "command_execution"}}) + "\n" + result.stdout
            return result
        with self.assertRaises(CodexProviderError):
            self.provider(tool_runner).generate(self.packet, self.schema, self.directory)
        self.assertEqual(json.loads((self.directory / "codex_execution.json").read_text(encoding="utf-8"))["status"], "rejected")

    def test_missing_model_or_non_openai_provider_is_rejected_without_exposing_settings(self):
        path = self.directory / "config.toml"
        for content in ('unrelated_setting = "private-placeholder"',
                        'model = "configured-id"\nmodel_provider = "other"'):
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(CodexProviderError) as error:
                read_configured_model(path)
            self.assertNotIn("private-placeholder", str(error.exception))
        path.write_text('model = "configured-id"\nmodel_provider = "openai"', encoding="utf-8")
        self.assertEqual(read_configured_model(path), "configured-id")

    def test_unknown_tool_event_without_item_is_rejected_and_explained_in_log(self):
        def unknown_runner(command, **kwargs):
            result = self.runner(command, **kwargs)
            if command[-1] != "--version":
                result.stdout = json.dumps({"type": "tool.started"}) + "\n" + result.stdout
            return result
        with self.assertRaises(CodexProviderError):
            self.provider(unknown_runner).generate(self.packet, self.schema, self.directory)
        log = json.loads((self.directory / "codex_execution.json").read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "rejected")
        self.assertIn("未知或未授權事件", log["validation_error"])


if __name__ == "__main__":
    unittest.main()
