"""前日交易檢視介面；目前僅誠實回報尚無可用的封存決策與成交。"""

from datetime import date
from pathlib import Path


class ReviewReportError(ValueError):
    """前日檢視報告與目前支援的合約或資料截止日不一致。"""


def refresh_history(month: str, *, as_of: str, output: Path | str, universe,
                    transport: str = "curl", progress=None) -> dict:
    """本角色負責既有九月下載入口；不擴張成決策日下載。"""
    if month != "2025-09" or _trade_date(as_of, "as_of") != "2025-09-30":
        raise ReviewReportError("本次重抓僅允許month=2025-09、as_of=2025-09-30，不讀10/1行情")
    from .history import download_history_universe
    return download_history_universe(
        month, output, universe=universe, cache_manifest=None, transport=transport,
        progress=progress, known_unavailable_tickers=("3718", "7769", "7828"),
    )


_REPORT_KEYS = {
    "report_version", "role", "scope", "status", "as_of", "data_through",
    "recommendations", "performance", "demo", "submission_ready", "reason",
}
_MISSING_REASON = (
    "目前沒有已封存的前日 D-Plan 與實際成交資料可供檢視；"
    "無法計算前日績效或提出有證據的決策改善建議。"
)


def _trade_date(value: str, label: str) -> str:
    try:
        if type(value) is not str or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise ReviewReportError(f"{label} 須為有效 YYYY-MM-DD 日期") from exc
    return value


def validate_review_report(report: dict, *, as_of: str) -> None:
    """純驗證；僅接受 prior_run_missing，不接受未實作的績效或建議。"""
    cutoff = _trade_date(as_of, "as_of")
    if type(report) is not dict or set(report) != _REPORT_KEYS:
        raise ReviewReportError("前日檢視報告欄位缺失或包含未知欄位")
    expected = {
        "report_version": "1.0", "role": "test_agent",
        "scope": "previous_trade_review", "status": "prior_run_missing",
    }
    for key, value in expected.items():
        if report[key] != value:
            raise ReviewReportError(f"前日檢視報告不支援 {key}={report[key]!r}")
    for key in ("as_of", "data_through"):
        if _trade_date(report[key], key) != cutoff:
            raise ReviewReportError(f"{key} 須等於資料截止日 {cutoff}，不得混入較晚或其他日期")
    if type(report["recommendations"]) is not list or report["recommendations"]:
        raise ReviewReportError("沒有封存決策與成交資料時，recommendations 必須為空陣列")
    if report["performance"] is not None:
        raise ReviewReportError("沒有實際成交資料時，performance 必須為 null，不能編造績效")
    if report["demo"] is not True or report["submission_ready"] is not False:
        raise ReviewReportError("目前前日檢視報告須為 demo，且不可標記可正式提交")
    if type(report["reason"]) is not str or not report["reason"].strip():
        raise ReviewReportError("前日檢視報告須說明缺少封存決策與成交資料")


def review_previous_day(*, as_of: str) -> dict:
    """不讀檔、不抓資料、不呼叫模型；缺資料時不產生假績效。

    後續接入已封存前日 D-Plan 與實際成交後，另擴充報告狀態、績效與
    建議的合約及驗證；目前這個入口沒有實作績效評估或最佳決策搜尋。
    """
    cutoff = _trade_date(as_of, "as_of")
    report = {
        "report_version": "1.0", "role": "test_agent",
        "scope": "previous_trade_review", "status": "prior_run_missing",
        "as_of": cutoff, "data_through": cutoff,
        "recommendations": [], "performance": None,
        "demo": True, "submission_ready": False, "reason": _MISSING_REASON,
    }
    validate_review_report(report, as_of=cutoff)
    return report


def evaluate_trade_day(workspace_path, *, output_dir, cache_manifest=None, transport="auto",
                       time_limit=120, progress=None) -> dict:
    """已封存決策之後才開放的隔離評估；不回寫首日review或重新呼叫模型。"""
    from etf_agent.sub_agents.test_agent.evaluation_runner import evaluate_frozen_plan
    return evaluate_frozen_plan(workspace_path, output_dir=output_dir, cache_manifest=cache_manifest,
                                transport=transport, time_limit=time_limit, progress=progress)
