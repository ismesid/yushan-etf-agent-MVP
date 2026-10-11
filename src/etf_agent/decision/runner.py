"""真實決策、一次必要修正與 demo 封存；不取得交易日行情、不更新帳務。"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError

from etf_agent.decision.providers.codex_cli import CodexProvider, CodexProviderError
from etf_agent.decision.dplan import archive_code, compile_dplan, load_prepared_packet, write_compiled_plan


class DecisionRunError(ValueError):
    pass


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _frozen_inputs(packet_path):
    directory = packet_path.parent
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["artifact_sha256"].items():
        candidate = (directory / name).resolve()
        if not candidate.is_relative_to(directory) or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise DecisionRunError("凍結輸入 hash 不符，禁止模型呼叫")


def decide_plan(packet_path, *, output_dir, project_root, team_id="DEMO", max_attempts=2,
                provider=None, progress=None) -> dict:
    """最多初次及一次必要修正，保留兩次完整紀錄；工具／逾時／連線失敗不自動重試。"""
    if type(max_attempts) is not int or max_attempts not in (1, 2):
        raise DecisionRunError("max_attempts 只能為1或2")
    packet_file = Path(packet_path).resolve()
    packet = load_prepared_packet(packet_file)
    _frozen_inputs(packet_file)
    if (packet.get("as_of"), packet.get("trade_date")) != ("2025-09-30", "2025-10-01"):
        raise DecisionRunError("本批只支援9/30截止的10/1歷史決策")
    if not packet.get("demo_decision_ready"):
        raise DecisionRunError("決策輸入未通過demo檢查，禁止模型呼叫")
    schema = json.loads((packet_file.parent / "weighted_agent_draft.schema.json").read_text(encoding="utf-8"))
    instructions = (packet_file.parent / "decision.md").read_text(encoding="utf-8")
    selected_provider = provider or CodexProvider()
    now = datetime.now(timezone(timedelta(hours=8)))
    run_id = now.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    run_dir = Path(output_dir).resolve() / packet["trade_date"] / ("decision_" + run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    before = archive_code(project_root, run_dir / "code_before")
    report = {"scope": "real_historical_demo_decision", "as_of": packet["as_of"],
              "trade_date": packet["trade_date"], "packet_json": str(packet_file),
              "run_dir": str(run_dir), "max_attempts": max_attempts, "attempts": [],
              "real_agent_decision": False, "accepted_demo_plan": False, "submission_ready": False,
              "decision_day_market_data_read": False, "code_version_before": before["code_version"]}
    report_path = run_dir / "decision_run.json"
    feedback = None
    for index in range(1, max_attempts + 1):
        attempt_dir = run_dir / f"attempt_{index}"
        attempt_dir.mkdir()
        prompt = instructions + (
            "\n\n編譯限制來自F04 v4.2：decisions最多30筆、orders最多30筆，"
            "需要同時涵蓋退出的原持股與新買入。續抱股數不變會進no_trade_decisions。"
            "keep的target_weight可採account_report.current_positions內的weight_of_input_nav；"
            "仍由程式核對官方floor公式，不能把keep標成股數不同的調整。"
            "請考慮買賣費用及賣出稅，費後現金須落在所宣告區間。"
            "increase/reduce/hold須符合前收估算淨買賣；hold容差採F07的NAV百分之二。"
        )
        if feedback is not None:
            _save(attempt_dir / "repair_context.json", feedback)
            prompt += "\n\n前一次草稿未通過驗證，這是唯一一次修正。不得改動輸入資料；請根據下列實際問題修正草稿。\n" + json.dumps(feedback, ensure_ascii=False)
        (attempt_dir / "decision.md").write_text(prompt, encoding="utf-8")
        entry = {"attempt": index, "directory": str(attempt_dir), "status": "started"}
        report["attempts"].append(entry)
        _save(report_path, report)
        if progress:
            progress(f"真實Codex決策呼叫 {index}/{max_attempts}，只提供9/30凍結資料")
        try:
            _frozen_inputs(packet_file)
            result = selected_provider.generate(copy.deepcopy(packet), schema, attempt_dir)
            report["real_agent_decision"] = True
            _save(attempt_dir / "agent_result.json", result.to_dict())
            Draft202012Validator(schema).validate(result.draft.to_dict())
            _frozen_inputs(packet_file)
            after = archive_code(project_root, attempt_dir / "code_after")
            if after != before:
                raise DecisionRunError("模型呼叫期间程式或設定變更，禁止封存有效計畫")
            metadata = {"model_provider": result.provider, "model_version": result.actual_model_version,
                        "run_started_at": result.started_at.isoformat(), "run_completed_at": result.completed_at.isoformat(),
                        "code_version": before["code_version"]}
            if result.usage is not None:
                for name in ("input_tokens", "output_tokens"):
                    if name in result.usage:
                        metadata[name] = result.usage[name]
            execution_packet = copy.deepcopy(packet)
            execution_packet["agent_metadata"] = metadata
            compiled = compile_dplan(execution_packet, result.draft, agent_metadata=metadata,
                                     team_id=team_id, decision_source="real")
            # 編譯器本身會加日期與run_id；不要再巢狀在decision/<run_id>下觸發Windows路徑限制。
            outputs = write_compiled_plan(compiled, Path(output_dir).resolve() / "compiled", project_root=project_root,
                                          packet=execution_packet, draft=result.draft)
            entry.update(status="accepted" if outputs["accepted_demo_plan"] else "validation_blocked",
                         outputs=outputs, actual_model_version=result.actual_model_version, usage=result.usage,
                         issues=compiled["validation"]["issues"])
            report["outputs"] = outputs
            if outputs["accepted_demo_plan"]:
                report["accepted_demo_plan"] = True
                break
            feedback = {"issues": compiled["validation"]["issues"],
                        "portfolio_issues": compiled["portfolio"]["issues"], "previous_draft": result.draft.to_dict()}
        except CodexProviderError as exc:
            entry.update(status="provider_rejected", message=str(exc))
            raw_path = attempt_dir / "raw_response.json"
            execution_log = attempt_dir / "codex_execution.json"
            events_path = attempt_dir / "events.jsonl"
            events = events_path.read_text(encoding="utf-8") if events_path.is_file() else ""
            log = json.loads(execution_log.read_text(encoding="utf-8")) if execution_log.is_file() else {}
            # 完成但格式／合約不合才可修正；工具呼叫或環境錯誤不能當作格式失敗重試。
            tool_free = True
            for line in events.splitlines():
                try:
                    item = json.loads(line).get("item")
                    if item is not None and item.get("type") not in ("agent_message", "reasoning"):
                        tool_free = False
                except (ValueError, AttributeError):
                    tool_free = False
            if (raw_path.is_file() and '"turn.completed"' in events and tool_free
                    and '"turn.failed"' not in events and '"error"' not in events
                    and log.get("status") == "rejected"
                    and log.get("error_type") in ("JSONDecodeError", "ContractError", "ValidationError")):
                feedback = {"issues": [log.get("validation_error") or str(exc)],
                            "previous_response": raw_path.read_text(encoding="utf-8")}
            else:
                break
        except DecisionRunError as exc:
            entry.update(status="input_or_code_changed", message=str(exc))
            break
        except OSError as exc:
            entry.update(status="archive_or_io_failed", message=str(exc))
            break
        except (ValueError, SchemaValidationError) as exc:
            entry.update(status="draft_invalid", message=str(exc))
            feedback = {"issues": [str(exc)], "previous_draft": result.draft.to_dict()}
        finally:
            _save(report_path, report)
    report["report_json"] = str(report_path)
    report["completed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
    _save(report_path, report)
    shared = packet.get("refresh_workspace", {})
    if shared.get("workspace_json"):
        shared_path = Path(shared["workspace_json"]).resolve()
        shared_root = Path(shared["run_root"]).resolve()
        if shared_path.is_relative_to(shared_root) and run_dir.is_relative_to(shared_root):
            workspace = json.loads(shared_path.read_text(encoding="utf-8"))
            workspace["files"]["decision_run"] = report_path.relative_to(shared_root).as_posix()
            latest_attempt = Path(report["attempts"][-1]["directory"])
            for key, name in (("agent_result", "agent_result.json"), ("raw_response", "raw_response.json"),
                              ("model_execution", "codex_execution.json")):
                model_file = latest_attempt / name
                if model_file.is_file():
                    workspace["files"][key] = model_file.relative_to(shared_root).as_posix()
            if report.get("outputs"):
                for name, output in (("dplan", "plan_json"), ("validation", "validation_json"),
                                     ("portfolio", "portfolio_json"), ("plan_manifest", "manifest_json"),
                                     ("plan_markdown", "plan_markdown")):
                    workspace["files"][name] = Path(report["outputs"][output]).relative_to(shared_root).as_posix()
                for name, output in report["outputs"].items():
                    if name.endswith("_csv"):
                        workspace["files"][name] = Path(output).relative_to(shared_root).as_posix()
            workspace.update(stage="compiled_demo_frozen" if report["accepted_demo_plan"] else "decision_blocked",
                             real_agent_decision=report["real_agent_decision"],
                             accepted_demo_plan=report["accepted_demo_plan"])
            _save(shared_path, workspace)
    return report
