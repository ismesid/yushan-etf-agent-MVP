"""Mock the download/analysis boundaries; no network or real price cache."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from etf_agent import pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.account = self.root / "account.json"
        self.account.write_text(json.dumps({
            "contract_version": "1.0", "snapshot_id": "synthetic",
            "as_of_trade_date": "2025-09-30", "status": "demo", "demo": True,
            "reconciled": False, "cash_twd": "109109400.00", "nav_twd": "1000000000.00",
            "origin": "pipeline_mock", "origin_ref": None,
            "positions": [{"ticker": "2330", "shares": 27000}],
        }), encoding="utf-8")
        self.calendar = self.root / "calendar.json"
        self.calendar.write_text('{}', encoding="utf-8")
        self.profile = self.root / "ranking.json"
        self.profile.write_text('{"unchanged":true}', encoding="utf-8")
        self.arguments = dict(month="2025-09", as_of="2025-09-30", trade_date="2025-10-01",
                              account_path=self.account, output_dir=self.root / "shared",
                              universe=object(), calendar_path=self.calendar, profile_path=self.profile)

    @staticmethod
    def writer(filename, key):
        def write(report, output):
            directory = Path(output) / "mock-stage"
            directory.mkdir(parents=True)
            path = directory / filename
            path.write_text(json.dumps(report), encoding="utf-8")
            return {key: str(path)}
        return write

    def run_mock(self, *, failure=None):
        packet = {"packet_version": "1.0", "as_of": "2025-09-30", "trade_date": "2025-10-01",
                  "demo_decision_ready": True, "data_report": {}, "review_report": {},
                  "account_report": {}}

        def download(month, **kwargs):
            self.assertEqual(month, "2025-09")
            self.assertEqual(kwargs["as_of"], "2025-09-30")
            self.assertEqual(kwargs["transport"], "curl")
            self.assertNotIn("cache_manifest", kwargs)
            manifest = Path(kwargs["output"]) / "fresh-run" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('{"requested_month":"2025-09"}', encoding="utf-8")
            sources = [{"ticker": "2330", "status": "success"},
                       {"ticker": "3718", "status": "known_unavailable_skipped"}]
            if failure:
                sources.append({"ticker": failure, "status": "failed", "error": "mock HTTP failure"})
            return {"manifest": str(manifest), "sources": sources, "network_requests": 1, "cache_hits": 0}

        def write_packet(value, output, **kwargs):
            directory = Path(output) / "mock-decision"
            directory.mkdir(parents=True)
            (directory / "evidence_packet.json").write_text(json.dumps(value), encoding="utf-8")
            for filename in ("workspace.json", "manifest.json", "data_report.json", "review_report.json",
                             "account_report.json", "decision.md", "weighted_agent_draft.schema.json"):
                (directory / filename).write_text('{}', encoding="utf-8")
            return {"packet_json": str(directory / "evidence_packet.json"),
                    "workspace_json": str(directory / "workspace.json")}

        old_cache = self.root / "old-cache"
        old_cache.mkdir()
        original_read = Path.read_bytes

        def reject_old_reads(path):
            self.assertFalse(path.resolve().is_relative_to(old_cache))
            return original_read(path)

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "read_bytes", reject_old_reads))
            stack.enter_context(patch.object(pipeline, "load_calendar", return_value={"month": "2025-09"}))
            fetch = stack.enter_context(patch.object(pipeline.test_agent, "refresh_history", side_effect=download))
            windows = stack.enter_context(patch.object(pipeline, "check_history_windows", return_value={"input_valid": True}))
            stack.enter_context(patch.object(pipeline, "write_window_report", side_effect=self.writer("windows.json", "report_json")))
            stack.enter_context(patch.object(pipeline, "analyze_history_features", return_value={"as_of": "2025-09-30"}))
            stack.enter_context(patch.object(pipeline, "write_feature_analysis", side_effect=self.writer("features.json", "metadata_json")))
            rankings = stack.enter_context(patch.object(pipeline, "analyze_history_rankings", return_value={"as_of": "2025-09-30"}))
            stack.enter_context(patch.object(pipeline, "write_ranking_analysis", side_effect=self.writer("rankings.json", "metadata_json")))
            prepare = stack.enter_context(patch.object(pipeline, "prepare_decision", return_value=packet))
            stack.enter_context(patch.object(pipeline, "write_decision_packet", side_effect=write_packet))
            outputs = pipeline.refresh_prepare(**self.arguments)
            return outputs, fetch.call_args, windows.call_args, rankings.call_args, prepare.call_args

    def test_shared_run_uses_fresh_outputs_and_explicit_frozen_inputs(self):
        outputs, fetch, windows, rankings, prepare = self.run_mock()
        run_root = Path(outputs["run_root"])
        workspace = json.loads(Path(outputs["workspace_json"]).read_text(encoding="utf-8"))
        self.assertTrue(outputs["demo_decision_ready"])
        self.assertEqual(workspace["stage"], "prepared")
        self.assertEqual(workspace["roles"], ["data_agent", "test_agent", "account_agent", "etf_agent"])
        for relative in workspace["files"].values():
            if relative is not None:
                self.assertTrue((run_root / relative).exists())
                self.assertFalse(Path(relative).is_absolute())
        self.assertEqual(Path(fetch.kwargs["output"]), run_root / "market")
        self.assertEqual(str(windows.args[0]), outputs["history_manifest"])
        self.assertEqual(Path(rankings.args[1]), run_root / "inputs" / "ranking.json")
        self.assertEqual(Path(prepare.args[0]), run_root / "inputs" / "account_snapshot.json")
        self.assertEqual(prepare.args[1], outputs["ranking_metadata"])
        self.assertEqual(workspace["download_summary"]["cache_hits"], 0)
        self.assertFalse(workspace["time_policy"]["decision_day_market_data_allowed"])

    def test_wrong_dates_are_rejected_before_reading_or_downloading(self):
        with patch.object(pipeline.test_agent, "refresh_history") as download, \
                patch.object(pipeline, "load_calendar") as calendar:
            for change in ({"month": "2025-10"}, {"as_of": "2025-10-01"}, {"trade_date": "2025-10-02"}):
                with self.subTest(change=change), self.assertRaises(pipeline.PipelineError):
                    pipeline.refresh_prepare(**{**self.arguments, **change})
            download.assert_not_called()
            calendar.assert_not_called()

    def test_unexpected_source_failure_cannot_be_reported_as_ready(self):
        outputs, *_ = self.run_mock(failure="1101")
        self.assertFalse(outputs["demo_decision_ready"])
        self.assertEqual(outputs["download_summary"]["unexpected_failed_stock_count"], 1)
        self.assertTrue(any(issue["code"] == "fresh_history_failed" and issue["severity"] == "BLOCK"
                            for issue in outputs["issues"]))
        workspace = json.loads(Path(outputs["workspace_json"]).read_text(encoding="utf-8"))
        packet = json.loads(Path(outputs["packet_json"]).read_text(encoding="utf-8"))
        self.assertEqual(workspace["stage"], "prepared_blocked")
        self.assertFalse(packet["demo_decision_ready"])


class CachedPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "shared"
        self.root.mkdir()
        retained = {"history_manifest": "market/manifest.json", "window_report": "windows/report.json",
                    "feature_metadata": "features/metadata.json", "ranking_metadata": "rankings/metadata.json",
                    "ranking_profile": "inputs/ranking.json", "calendar": "inputs/calendar.json",
                    "model_availability": "inputs/model_availability.json"}
        for key, value in retained.items():
            path = self.root / value
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"as_of": "2025-09-30", "synthetic": key}), encoding="utf-8")
        self.ranking = self.root / retained["ranking_metadata"]
        old_files = {"decision_run": "deleted/run.json", "agent_result": "deleted/result.json",
                     "raw_response": "deleted/raw.json", "model_execution": "deleted/model.json",
                     "dplan": "deleted/plan.json", "validation": "deleted/validation.json",
                     "portfolio": "deleted/portfolio.json", "plan_manifest": "deleted/manifest.json",
                     "summary": "deleted/summary.json", "etf_orders_csv": "deleted/orders.csv"}
        self.workspace_path = self.root / "workspace.json"
        self.workspace_path.write_text(json.dumps({
            "workspace_version": "1.0", "as_of": "2025-09-30", "trade_date": "2025-10-01",
            "files": {**retained, **old_files}, "stage": "compiled_demo_frozen", "real_agent_decision": True,
            "accepted_demo_plan": True, "inputs": {"account": {"path": str(self.directory / "deleted-account.json")}},
            "artifact_sha256": {"deleted/plan.json": "old"}, "issues": [],
        }), encoding="utf-8")
        self.account = self.directory / "new_weak_account.json"
        self.account.write_text(json.dumps({
            "contract_version": "1.0", "snapshot_id": "ARTIFICIAL_WEAK_ACCOUNT",
            "as_of_trade_date": "2025-09-30", "status": "demo", "demo": True,
            "reconciled": False, "cash_twd": "109109400", "nav_twd": "1000000000",
            "origin": "cached_pipeline_mock", "origin_ref": None,
            "positions": [{"ticker": "2330", "shares": 27000}],
        }), encoding="utf-8")
        self.arguments = dict(account_path=self.account, ranking_metadata_path=self.ranking,
                              as_of="2025-09-30", trade_date="2025-10-01",
                              shared_run_root=self.root, universe=object())

    def mock_packet(self, account_path, ranking_path, **kwargs):
        return {"packet_version": "1.0", "as_of": kwargs["as_of"], "trade_date": kwargs["trade_date"],
                "account_snapshot": json.loads(Path(account_path).read_text(encoding="utf-8")),
                "demo_decision_ready": True}

    def mock_writer(self, packet, output, **kwargs):
        directory = Path(output) / "synthetic-new-input"
        directory.mkdir(parents=True)
        csv_names = ("data_candidates", "data_issues", "account_positions", "account_summary",
                     "review_status", "review_recommendations")
        names = ["evidence_packet.json", "data_report.json", "review_report.json", "account_report.json",
                 "workspace.json", "decision.md", "weighted_agent_draft.schema.json",
                 *(name + ".csv" for name in csv_names)]
        artifacts = {}
        for name in names:
            body = json.dumps(packet if name == "evidence_packet.json" else {"synthetic": name}).encode("utf-8")
            (directory / name).write_bytes(body)
            artifacts[name] = __import__("hashlib").sha256(body).hexdigest()
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({"artifact_sha256": artifacts}), encoding="utf-8")
        return {"run_dir": str(directory), "packet_json": str(directory / "evidence_packet.json"),
                "workspace_json": str(directory / "workspace.json"), "manifest_json": str(manifest),
                **{name + "_csv": str(directory / (name + ".csv")) for name in csv_names}}

    def test_cached_prepare_replaces_account_and_stale_indices_without_fetch_or_old_reads(self):
        original_market = (self.root / "market/manifest.json").read_bytes()
        with patch.object(pipeline, "prepare_decision", side_effect=self.mock_packet) as prepare, \
                patch.object(pipeline, "write_decision_packet", side_effect=self.mock_writer), \
                patch.object(pipeline.test_agent, "refresh_history") as fetch, \
                patch.object(pipeline, "analyze_history_features") as recompute:
            outputs = pipeline.prepare_cached(**self.arguments)
        fetch.assert_not_called()
        recompute.assert_not_called()
        self.assertEqual(Path(prepare.call_args.args[0]), self.root / "inputs/account_snapshot.json")
        self.assertEqual(Path(prepare.call_args.args[1]), self.ranking)
        self.assertEqual((self.root / "market/manifest.json").read_bytes(), original_market)
        workspace = json.loads(self.workspace_path.read_text(encoding="utf-8"))
        self.assertEqual(workspace["stage"], "prepared")
        self.assertFalse(workspace["real_agent_decision"])
        self.assertFalse(workspace["accepted_demo_plan"])
        self.assertEqual(len(workspace["artifact_sha256"]), 13)
        self.assertEqual(workspace["inputs"]["account"]["path"], str(self.account))
        for key, relative in workspace["files"].items():
            self.assertNotIn("deleted", relative)
            self.assertTrue((self.root / relative).exists(), key)
            self.assertFalse(Path(relative).is_absolute())
        self.assertEqual(len([key for key in workspace["files"] if key.endswith("_csv")]), 6)
        packet = json.loads(Path(outputs["packet_json"]).read_text(encoding="utf-8"))
        self.assertEqual(packet["account_snapshot"]["snapshot_id"], "ARTIFICIAL_WEAK_ACCOUNT")
        self.assertEqual(packet["refresh_workspace"]["workspace_json"], str(self.workspace_path))
        self.assertTrue(packet["packet_version_id"].startswith("decision-packet-v1-"))

    def test_cached_prepare_rejects_future_date_outside_run_and_wrong_ranking_cutoff(self):
        with patch.object(pipeline, "prepare_decision") as prepare, \
                patch.object(pipeline.test_agent, "refresh_history") as fetch:
            for change in ({"as_of": "2025-10-01"},
                           {"ranking_metadata_path": self.directory / "outside-ranking.json"}):
                with self.subTest(change=change), self.assertRaises(pipeline.PipelineError):
                    pipeline.prepare_cached(**{**self.arguments, **change})
            self.ranking.write_text('{"as_of":"2025-10-01"}', encoding="utf-8")
            with self.assertRaises(pipeline.PipelineError):
                pipeline.prepare_cached(**self.arguments)
        prepare.assert_not_called()
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
