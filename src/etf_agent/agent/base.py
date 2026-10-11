"""所有投資模型遵守同一介面；本批只宣告介面，不呼叫模型。"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from etf_agent.contracts import AgentDraft, Contract, ContractError


@dataclass(frozen=True)
class AgentResult(Contract):
    draft: AgentDraft
    provider: Literal["openai", "anthropic", "fixture"]
    actual_model_version: str | None
    started_at: datetime | None
    completed_at: datetime | None
    usage: dict[str, int] | None
    raw_response_path: str | None
    log_path: str | None

    def _check(self):
        if self.provider == "fixture" and (self.actual_model_version is not None or self.usage is not None):
            raise ContractError("fixture 不可宣稱真實模型版本或模型用量")
        if self.usage is not None and any(value < 0 for value in self.usage.values()):
            raise ContractError("模型用量不可為負")
        if self.started_at is not None and self.completed_at is not None and self.completed_at < self.started_at:
            raise ContractError("模型執行結束不可早於開始")


class AgentProvider(Protocol):
    def generate(self, packet: dict, draft_schema: dict, run_dir: Path) -> AgentResult:
        """讀取凍結資料包，回傳草稿與真實執行資訊。"""
        ...
