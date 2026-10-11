"""一次受限制的 Codex CLI 決策；沒有自動重試，不下載行情或修改設定。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from etf_agent.decision.providers.base import AgentResult
from etf_agent.contracts import ContractError, WeightedAgentDraft
from etf_agent.paths import project_root


class CodexProviderError(ValueError):
    """模型設定、執行或回覆不能通過決策合約；保留實際輸出，不重試。"""


def read_configured_model(config_path: Path | str | None = None) -> str:
    """只回傳設定的模型ID，拒絕非OpenAI provider；不回傳或記錄其他設定。"""
    path = Path(config_path) if config_path is not None else Path.home() / ".codex" / "config.toml"
    try:
        settings = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CodexProviderError("無法讀取本機Codex模型設定") from exc
    if settings.get("model_provider", "openai") != "openai":
        raise CodexProviderError("本批只支援已確認的OpenAI provider")
    model = settings.get("model")
    if type(model) is not str or not model.strip():
        raise CodexProviderError("本機未設定可核對的model ID；不能猜模型版本")
    return model.strip()


def _command() -> list[str]:
    executable = shutil.which("codex.cmd") if os.name == "nt" else shutil.which("codex")
    if not executable:
        raise CodexProviderError("找不到Codex CLI")
    if Path(executable).suffix.lower() in (".cmd", ".bat"):
        entry = Path(executable).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node.exe")
        if not node or not entry.is_file():
            raise CodexProviderError("Windows Codex需要已安裝node.exe與codex.js；不以shell拼接cmd")
        return [node, str(entry)]
    return [executable]


def _run_cli(command, *, input=None, cwd=None, timeout=220, **kwargs):
    """逾時結束自身CLI進程樹；不讓模型子程序在背景繼續運行。"""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                               cwd=cwd, shell=False)
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, text=True, timeout=10, check=False, shell=False)
        process.kill()
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _text(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remote_schema(value):
    """遠端Structured Outputs投影；完整限制仍以原schema在本地檢查。"""
    if isinstance(value, list):
        return [_remote_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    projected = {}
    for key, item in value.items():
        if key in {"uniqueItems", "minLength", "maxLength"}:
            continue
        if key == "const":
            projected["enum"] = [item]
        else:
            projected[key] = _remote_schema(item)
    return projected


class CodexProvider:
    def __init__(self, *, model: str | None = None, timeout_seconds: int = 220,
                 runner=None, command: list[str] | None = None):
        self.model = model if model is not None else read_configured_model()
        if type(self.model) is not str or not self.model.strip():
            raise CodexProviderError("必須提供可核對的model ID")
        if not 180 <= timeout_seconds <= 240:
            raise CodexProviderError("本批模型timeout須在180～240秒")
        self.timeout_seconds = timeout_seconds
        self.runner = runner or _run_cli
        self.command = command if command is not None else _command()

    def generate(self, packet: dict, draft_schema: dict, run_dir: Path) -> AgentResult:
        """單次呼叫；預算／最多一次修正由外部流程控制，不在provider內重試。"""
        directory = Path(run_dir).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / "codex_execution.json").exists() or (directory / "raw_response.json").exists():
            raise CodexProviderError("每次模型呼叫須使用新的run_dir，不能覆寫前次原始回覆")
        model_work = directory / "model_work"
        model_work.mkdir(exist_ok=True)
        source_prompt = directory / "decision.md"
        if not source_prompt.is_file():
            source_prompt = project_root() / "prompts" / "decision.md"
        try:
            instructions = source_prompt.read_text(encoding="utf-8-sig")
            packet_body = json.dumps(packet, ensure_ascii=False, sort_keys=True, allow_nan=False)
            schema_body = json.dumps(draft_schema, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (OSError, UnicodeError, ValueError) as exc:
            raise CodexProviderError("無法建立凍結模型輸入") from exc
        packet_path, schema_path = directory / "provider_packet.json", directory / "provider_schema.json"
        output_schema_path = directory / "provider_output_schema.json"
        packet_path.write_text(packet_body + "\n", encoding="utf-8")
        schema_path.write_text(schema_body + "\n", encoding="utf-8")
        output_schema_path.write_text(json.dumps(_remote_schema(draft_schema), ensure_ascii=False,
                                                sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        prompt_path, response_path = directory / "provider_stdin.txt", directory / "raw_response.json"
        prompt = (instructions + "\n\n全部輸入已提供於STDIN。不得使用任何工具或讀取任何檔案。"
                  "只返回WeightedAgentDraft 2.0 JSON；不得包含shares或事後行情。\n"
                  + "\nFROZEN_EVIDENCE_PACKET:\n" + packet_body + "\nOUTPUT_SCHEMA:\n" + schema_body)
        prompt_path.write_text(prompt, encoding="utf-8")
        watched = [packet_path, schema_path, output_schema_path, prompt_path, source_prompt]
        before = {str(path): _hash(path) for path in watched}
        events_path, stderr_path, log_path = directory / "events.jsonl", directory / "stderr.txt", directory / "codex_execution.json"
        try:
            version = self.runner([*self.command, "--version"], cwd=str(model_work), timeout=20,
                                  capture_output=True, text=True, encoding="utf-8", shell=False)
            cli_version = _text(version.stdout).strip()
            if version.returncode or not cli_version:
                raise CodexProviderError("無法核對實際CLI版本")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodexProviderError("無法核對實際CLI版本") from exc
        command = [*self.command, "exec", "--ignore-user-config", "--ignore-rules",
                   "--sandbox", "read-only", "--json", "--model", self.model,
                   "--output-schema", str(output_schema_path), "--output-last-message", str(response_path),
                   "--ephemeral", "--skip-git-repo-check", "-C", str(model_work),
                   "-c", "project_doc_max_bytes=0", "-c", 'web_search="disabled"',
                   "-c", "features.shell_tool=false", "-c", "features.unified_exec=false",
                   "-c", "features.browser_use=false", "-c", "features.computer_use=false",
                   "-c", "features.apps=false", "-c", "features.plugins=false",
                   "-c", "features.code_mode_host=false", "-c", "features.image_generation=false",
                   "-c", "features.multi_agent=false", "-c", "features.multi_agent_v2=false",
                   "-c", "features.skill_search=false", "-c", "features.hooks=false", "-"]
        started = datetime.now(timezone(timedelta(hours=8)))
        log = {"provider": "openai", "requested_model": self.model, "cli_version": cli_version,
               "model_identity_basis": "explicit_cli_model_id", "resolved_snapshot": None,
               "started_at": started.isoformat(), "input_sha256": before, "status": "started",
               "timeout_seconds": self.timeout_seconds, "tool_calls_allowed": False}
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        stdout = stderr = ""
        try:
            result = self.runner(command, input=prompt, cwd=str(model_work), timeout=self.timeout_seconds,
                                 capture_output=True, text=True, encoding="utf-8", shell=False)
            stdout, stderr = _text(result.stdout), _text(result.stderr)
            if result.returncode:
                raise CodexProviderError(f"Codex執行失敗（exit {result.returncode}）；詳見保存紀錄")
            events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            completed, usage = False, None
            allowed_events = {"thread.started", "turn.started", "item.started", "item.updated",
                              "item.completed", "turn.completed"}
            for event in events:
                if not isinstance(event, dict):
                    raise CodexProviderError("CLI事件須為JSON object")
                event_type = event.get("type")
                if event_type in ("error", "turn.failed"):
                    raise CodexProviderError("模型事件回報失敗")
                if type(event_type) is not str or event_type not in allowed_events:
                    raise CodexProviderError("模型回報未知或未授權事件類型")
                item = event.get("item")
                if event_type.startswith("item.") and not isinstance(item, dict):
                    raise CodexProviderError("CLI item事件缺少可核對的item")
                if item is not None and (not isinstance(item, dict) or item.get("type") not in ("agent_message", "reasoning")):
                    raise CodexProviderError("模型使用了未授權工具；整次結果拒絕")
                if event.get("type") == "turn.completed":
                    completed = True
                    raw_usage = event.get("usage")
                    if isinstance(raw_usage, dict):
                        usage = {key: value for key, value in raw_usage.items() if type(value) is int and value >= 0} or None
            if not completed:
                raise CodexProviderError("未取得turn.completed；不能宣稱模型完成")
            if any(_hash(path) != before[str(path)] for path in watched):
                raise CodexProviderError("模型呼叫期間凍結輸入已變更")
            raw = json.loads(response_path.read_text(encoding="utf-8-sig"))
            Draft202012Validator(draft_schema).validate(raw)
            draft = WeightedAgentDraft.from_dict(raw)
            draft.validate_context(allowed_tickers=packet["allowed_tickers"],
                                   held_tickers=packet["held_tickers"],
                                   observation_ids={row["obs_id"] for row in packet["observations"]})
            completed_at = datetime.now(timezone(timedelta(hours=8)))
            log.update(status="completed", completed_at=completed_at.isoformat(), usage=usage,
                       actual_model_version=self.model, input_sha256_after=before)
            return AgentResult(draft=draft, provider="openai", actual_model_version=self.model,
                               started_at=started, completed_at=completed_at, usage=usage,
                               raw_response_path=str(response_path), log_path=str(log_path))
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = _text(exc.output), _text(exc.stderr)
            log.update(status="timeout", validation_error="Codex決策逾時；不自動重試")
            raise CodexProviderError("Codex決策逾時；不自動重試") from exc
        except (OSError, ValueError, ContractError, ValidationError) as exc:
            log.update(status="rejected", error_type=type(exc).__name__)
            if isinstance(exc, (ContractError, CodexProviderError, json.JSONDecodeError, ValidationError)):
                log["validation_error"] = str(exc)
            if isinstance(exc, CodexProviderError):
                raise
            raise CodexProviderError("模型回覆或凍結輸入無法通過驗證；詳見保存紀錄") from exc
        finally:
            events_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            log["finished_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
            log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
