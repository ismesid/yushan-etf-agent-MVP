"""Rebuild the September demo inputs in one shared run, without model calls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from etf_agent.sub_agents.account_agent.account import load_account_json
from etf_agent.calendar import load_calendar
from etf_agent.evidence import prepare_decision, write_decision_packet
from etf_agent.sub_agents.data_agent.features import analyze_history_features, write_feature_analysis
from etf_agent.sub_agents.data_agent.history_windows import check_history_windows, write_window_report
from etf_agent.sub_agents.data_agent.ranking import analyze_history_rankings, write_ranking_analysis
from etf_agent.sub_agents import test_agent


class PipelineError(ValueError):
    """A shared input run could not be prepared; no investment decision is made."""


KNOWN_UNAVAILABLE = frozenset({"3718", "7769", "7828"})


def prepare_cached(*, account_path, ranking_metadata_path, as_of: str,
                   trade_date: str, shared_run_root, universe) -> dict:
    """Replace decision inputs in an explicit existing September shared run.

    Only the new supplied account and retained ranking are loaded. Old model
    files and old account references in the workspace are never dereferenced.
    No HTTP, factor recomputation, model call or decision-day market read occurs.
    """
    if (as_of, trade_date) != ("2025-09-30", "2025-10-01"):
        raise PipelineError("僅允許9/30截止、10/1決策；不讀決策日行情")
    shared_root = Path(shared_run_root).resolve()
    ranking_file = Path(ranking_metadata_path).resolve()
    if not ranking_file.is_relative_to(shared_root):
        raise PipelineError("排名必須位於明確指定的 shared run，不能混入其他快取")
    workspace_file = shared_root / "workspace.json"
    try:
        workspace = json.loads(workspace_file.read_text(encoding="utf-8"))
        ranking = json.loads(ranking_file.read_text(encoding="utf-8-sig"))
        if (type(workspace) is not dict or workspace.get("workspace_version") != "1.0"
                or (workspace.get("as_of"), workspace.get("trade_date")) != (as_of, trade_date)
                or type(workspace.get("files")) is not dict
                or type(ranking) is not dict or ranking.get("as_of") != as_of):
            raise PipelineError("既有 shared workspace／排名的格式或資料日期不符")
        account_file = Path(account_path).resolve()
        account = load_account_json(account_file)
        if account.as_of_trade_date.isoformat() != as_of:
            raise PipelineError("新期初帳戶日期須與9/30排名相同")
        account_body = account_file.read_bytes()
        account_digest = hashlib.sha256(account_body).hexdigest()

        def relative(path):
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(shared_root):
                raise PipelineError("新產物必須留在相同 shared run")
            return resolved.relative_to(shared_root).as_posix()

        retained = {}
        prefixes = ("market", "history", "coverage", "daily", "monthly", "window", "feature", "ranking",
                    "calendar", "model_availability")
        for key, value in workspace["files"].items():
            if not key.startswith(prefixes) or not isinstance(value, str):
                continue
            candidate = (shared_root / value).resolve()
            if candidate.is_relative_to(shared_root) and candidate.exists():
                retained[key] = relative(candidate)
        inputs_dir = shared_root / "inputs"
        inputs_dir.mkdir(exist_ok=True)
        account_copy = inputs_dir / "account_snapshot.json"
        account_copy.write_bytes(account_body)
        retained["account_snapshot"] = relative(account_copy)
        retained["ranking_metadata"] = relative(ranking_file)
        account_reference = {"path": str(account_file), "sha256": account_digest,
                             "frozen_path": relative(account_copy)}
        old_inputs = workspace.get("inputs")
        workspace["inputs"] = dict(old_inputs) if type(old_inputs) is dict else {}
        workspace["inputs"]["account"] = account_reference
        workspace["inputs"]["ranking_metadata"] = {
            "path": str(ranking_file), "sha256": hashlib.sha256(ranking_file.read_bytes()).hexdigest()}
        for key in ("agent_metadata", "decision_run", "agent_result", "raw_response", "model_execution", "dplan",
                    "validation", "portfolio", "plan_manifest", "summary", "final_summary", "decision_attempts",
                    "attempts", "outputs", "code_version_before", "code_version_after", "artifact_sha256"):
            workspace.pop(key, None)
        workspace.update(files=retained, stage="preparing_decision", real_agent_decision=False,
                         accepted_demo_plan=False, submission_ready=False, demo_decision_ready=False,
                         roles=["data_agent", "test_agent", "account_agent", "etf_agent"])
        workspace["time_policy"] = {"max_market_trade_date": as_of,
                                    "decision_day_market_data_allowed": False}
        source_codes = {"known_history_unavailable", "fresh_history_failed", "fresh_window_input_invalid"}
        workspace["issues"] = [item for item in workspace.get("issues", [])
                               if isinstance(item, dict) and item.get("code") in source_codes]
        workspace_file.write_text(json.dumps(workspace, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                  encoding="utf-8", newline="\n")
        packet = prepare_decision(account_copy, ranking_file, as_of=as_of, trade_date=trade_date, universe=universe)
        if any(item.get("severity") == "BLOCK" for item in workspace["issues"]):
            packet["demo_decision_ready"] = False
        packet["pipeline_issues"] = list(workspace["issues"])
        packet["refresh_workspace"] = {"run_root": str(shared_root), "workspace_json": str(workspace_file)}
        packet.pop("packet_version_id", None)
        body = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        packet["packet_version_id"] = "decision-packet-v1-" + hashlib.sha256(body).hexdigest()[:12]
        outputs = write_decision_packet(packet, shared_root / "decision_input",
                                         project_root=Path(__file__).resolve().parents[2])
        decision_dir = Path(outputs["packet_json"]).parent
        manifest_path = Path(outputs["manifest_json"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prepared_hashes = {}
        for filename, expected in manifest["artifact_sha256"].items():
            artifact = (decision_dir / filename).resolve()
            if not artifact.is_relative_to(decision_dir) or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                raise PipelineError("新決策輸入產物 hash 不符")
            prepared_hashes[relative(artifact)] = expected
        for key, filename in (("evidence_packet", "evidence_packet.json"), ("data_report", "data_report.json"),
                              ("review_report", "review_report.json"), ("account_report", "account_report.json"),
                              ("decision_manifest", "manifest.json"), ("decision_workspace", "workspace.json"),
                              ("prompt", "decision.md"), ("draft_schema", "weighted_agent_draft.schema.json")):
            workspace["files"][key] = relative(decision_dir / filename)
        for key, value in outputs.items():
            if key.endswith("_csv"):
                workspace["files"][key] = relative(value)
        workspace.update(artifact_sha256=prepared_hashes, demo_decision_ready=packet["demo_decision_ready"],
                         stage="prepared" if packet["demo_decision_ready"] else "prepared_blocked")
        workspace_file.write_text(json.dumps(workspace, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                  encoding="utf-8", newline="\n")
        history_reference = workspace["files"].get("history_manifest")
        return {**outputs, "run_root": str(shared_root), "workspace_json": str(workspace_file),
                "decision_workspace_json": outputs.get("workspace_json"),
                "history_manifest": str(shared_root / history_reference) if history_reference else None,
                "ranking_metadata": str(ranking_file), "demo_decision_ready": packet["demo_decision_ready"],
                "issues": workspace["issues"], "download_summary": workspace.get("download_summary", {})}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(f"既有 shared run 的決策準備失敗：{exc}") from exc


def refresh_prepare(*, month: str, as_of: str, trade_date: str, account_path,
                    output_dir, universe, calendar_path,
                    profile_path="config/ranking.json", progress=None) -> dict:
    """Fetch September afresh, recompute existing factors and freeze a packet.

    The old history cache is neither searched nor deleted here. The caller
    controls any separately authorized deletion. Calendar and account inputs
    are explicit; this function never reads decision-day prices or calls LLMs.
    """
    if (month, as_of, trade_date) != ("2025-09", "2025-09-30", "2025-10-01"):
        raise PipelineError("本次只允許九月行情、9/30 截止、10/1 決策；禁止取得或讀入 10/1 行情")
    calendar_file, account_file, profile_file = (
        Path(value).resolve() for value in (calendar_path, account_path, profile_path))
    calendar = load_calendar(calendar_file)
    if calendar.get("month") != month:
        raise PipelineError("必須提供既有官方九月日曆，不重抓日曆")
    account = load_account_json(account_file)
    if account.as_of_trade_date.isoformat() != as_of:
        raise PipelineError("輸入帳戶必須截至 2025-09-30")
    originals = {}
    for key, path in (("account", account_file), ("calendar", calendar_file), ("profile", profile_file)):
        body = path.read_bytes()
        originals[key] = {"path": str(path), "sha256": hashlib.sha256(body).hexdigest()}
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_root = Path(output_dir).resolve() / trade_date / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    workspace_path = run_root / "workspace.json"
    workspace = {
        "workspace_version": "1.0", "scope": "shared_fresh_history_run",
        "run_id": run_id, "as_of": as_of, "trade_date": trade_date,
        "roles": ["data_agent", "test_agent", "account_agent", "etf_agent"],
        "stage": "initializing", "inputs": originals,
        "files": {"agent_result": None, "dplan": None}, "issues": [],
        "time_policy": {"max_market_trade_date": as_of, "decision_day_market_data_allowed": False},
        "demo_decision_ready": False, "real_agent_decision": False, "submission_ready": False,
    }

    def save_workspace(stage):
        workspace["stage"] = stage
        workspace_path.write_text(json.dumps(workspace, ensure_ascii=False, indent=2,
                                            allow_nan=False) + "\n", encoding="utf-8", newline="\n")

    def relative(path):
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(run_root):
            raise PipelineError("產物必須留在同一次 shared run，不能混入舊快取")
        return resolved.relative_to(run_root).as_posix()

    save_workspace("initializing")
    try:
        inputs_dir = run_root / "inputs"
        inputs_dir.mkdir()
        account_copy = inputs_dir / "account_snapshot.json"
        account_copy.write_bytes(account_file.read_bytes())
        if hashlib.sha256(account_copy.read_bytes()).hexdigest() != originals["account"]["sha256"]:
            raise PipelineError("輸入帳戶在凍結期間已變更")
        profile_copy = inputs_dir / "ranking.json"
        profile_copy.write_bytes(profile_file.read_bytes())
        if hashlib.sha256(profile_copy.read_bytes()).hexdigest() != originals["profile"]["sha256"]:
            raise PipelineError("排名設定在凍結期間已變更")
        workspace["files"].update(account_snapshot=relative(account_copy), ranking_profile=relative(profile_copy))
        save_workspace("downloading_september")
        history = test_agent.refresh_history(month, as_of=as_of, output=run_root / "market",
                                           universe=universe, transport="curl", progress=progress)
        history_manifest = Path(history["manifest"]).resolve()
        workspace["files"]["history_manifest"] = relative(history_manifest)
        for key in ("coverage_report", "daily_dir", "monthly_dir"):
            if history.get(key):
                workspace["files"][key] = relative(history[key])
        bad_sources = [source for source in history.get("sources", []) if source.get("status") != "success"]
        extra_failures = [source for source in bad_sources if source.get("ticker") not in KNOWN_UNAVAILABLE]
        for source in bad_sources:
            workspace["issues"].append({
                "code": "known_history_unavailable" if source not in extra_failures else "fresh_history_failed",
                "severity": "WARN" if source not in extra_failures else "BLOCK",
                "ticker": source.get("ticker"), "message": source.get("error") or source.get("status"),
            })
        workspace["download_summary"] = {
            "successful_stock_count": sum(source.get("status") == "success" for source in history.get("sources", [])),
            "known_unavailable_stock_count": len(bad_sources) - len(extra_failures),
            "unexpected_failed_stock_count": len(extra_failures),
            "network_requests": history.get("network_requests"), "cache_hits": history.get("cache_hits"),
            "coverage_complete": history.get("coverage_complete", False),
        }
        save_workspace("checking_windows")
        windows = check_history_windows(history_manifest, as_of=as_of, calendar=calendar, universe=universe)
        window_outputs = write_window_report(windows, run_root / "windows")
        workspace["files"]["window_report"] = relative(window_outputs["report_json"])
        if window_outputs.get("report_csv"):
            workspace["files"]["window_csv"] = relative(window_outputs["report_csv"])
        save_workspace("computing_features")
        features = analyze_history_features(window_outputs["report_json"])
        feature_outputs = write_feature_analysis(features, run_root / "features")
        workspace["files"]["feature_metadata"] = relative(feature_outputs["metadata_json"])
        if feature_outputs.get("features_csv"):
            workspace["files"]["features_csv"] = relative(feature_outputs["features_csv"])
        rankings = analyze_history_rankings(feature_outputs["metadata_json"], profile_copy)
        ranking_outputs = write_ranking_analysis(rankings, run_root / "rankings")
        workspace["files"]["ranking_metadata"] = relative(ranking_outputs["metadata_json"])
        if ranking_outputs.get("rankings_csv"):
            workspace["files"]["rankings_csv"] = relative(ranking_outputs["rankings_csv"])
        save_workspace("preparing_decision")
        packet = prepare_decision(account_copy, ranking_outputs["metadata_json"], as_of=as_of,
                                  trade_date=trade_date, universe=universe)
        if extra_failures or windows.get("input_valid") is not True:
            packet["demo_decision_ready"] = False
            if windows.get("input_valid") is not True:
                workspace["issues"].append({"code": "fresh_window_input_invalid", "severity": "BLOCK",
                                             "ticker": None, "message": "新行情的價格視窗資料未通過檢查"})
        packet["pipeline_issues"] = list(workspace["issues"])
        packet["refresh_workspace"] = {"run_root": str(run_root), "workspace_json": str(workspace_path)}
        packet.pop("packet_version_id", None)
        body = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        packet["packet_version_id"] = "decision-packet-v1-" + hashlib.sha256(body).hexdigest()[:12]
        outputs = write_decision_packet(packet, run_root / "decision_input",
                                         project_root=Path(__file__).resolve().parents[2])
        packet_file = Path(outputs["packet_json"])
        decision_dir = packet_file.parent
        for key, name in (("evidence_packet", "evidence_packet.json"), ("data_report", "data_report.json"),
                          ("review_report", "review_report.json"), ("account_report", "account_report.json"),
                          ("decision_manifest", "manifest.json"), ("decision_workspace", "workspace.json"),
                          ("prompt", "decision.md"), ("draft_schema", "weighted_agent_draft.schema.json")):
            workspace["files"][key] = relative(decision_dir / name)
        for key, path in outputs.items():
            if key.endswith("_csv"):
                workspace["files"][key] = relative(path)
        workspace["demo_decision_ready"] = packet["demo_decision_ready"]
        save_workspace("prepared" if packet["demo_decision_ready"] else "prepared_blocked")
        return {**outputs, "run_root": str(run_root), "workspace_json": str(workspace_path),
                "decision_workspace_json": outputs.get("workspace_json"),
                "history_manifest": str(history_manifest), "ranking_metadata": ranking_outputs["metadata_json"],
                "demo_decision_ready": packet["demo_decision_ready"], "issues": workspace["issues"],
                "download_summary": workspace["download_summary"]}
    except Exception as exc:
        workspace["issues"].append({"code": "fresh_pipeline_failed", "severity": "BLOCK",
                                     "ticker": None, "message": str(exc)})
        save_workspace("failed")
        raise PipelineError(f"重新準備失敗；診斷保存在 {workspace_path}：{exc}") from exc
