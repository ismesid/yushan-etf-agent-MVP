"""有單位、時間與來源的共用資料合約；只使用 Python 標準庫。

內部 Decimal 序列化為字串；AgentDraft 的比例為 JSON 數字。
這裡的檢查不取代官方 D-Plan schema、股數公式或語意驗證。
"""

from __future__ import annotations

import math
import re
import types
from dataclasses import MISSING, dataclass, fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints


class ContractError(ValueError):
    """欄位、型別或資料合約不一致。"""


def _decode(value: Any, annotation: Any, path: str) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _decode(value, option, path)
            except ContractError:
                pass
        raise ContractError(f"{path}: 型別或值不符合 {annotation}")
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in args):
            return value
        raise ContractError(f"{path}: 必須為 {args}")
    if annotation is type(None):
        if value is None:
            return None
        raise ContractError(f"{path}: 必須為 null")
    if annotation is Decimal:
        if isinstance(value, Decimal):
            result = value
        elif type(value) is str:
            try:
                result = Decimal(value)
            except InvalidOperation as exc:
                raise ContractError(f"{path}: 無效十進位數字") from exc
        else:
            raise ContractError(f"{path}: 金額/權重須為十進位字串或 Decimal，不能用 float")
        if not result.is_finite():
            raise ContractError(f"{path}: 數字必須有限")
        return result
    if annotation is datetime:
        if type(value) is str:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+08:00", value):
                raise ContractError(f"{path}: 時間須含台北時區 +08:00")
            try:
                value = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ContractError(f"{path}: 無效時間") from exc
        if type(value) is not datetime or value.utcoffset() != timedelta(hours=8):
            raise ContractError(f"{path}: 時間須含台北時區 +08:00")
        return value
    if annotation is date:
        if type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ContractError(f"{path}: 無效日期") from exc
        if type(value) is not date:
            raise ContractError(f"{path}: 日期須為 YYYY-MM-DD")
        return value
    if origin is tuple:
        if type(value) not in (list, tuple):
            raise ContractError(f"{path}: 必須為陣列")
        return tuple(_decode(item, args[0], f"{path}[{i}]") for i, item in enumerate(value))
    if origin is dict:
        if type(value) is not dict:
            raise ContractError(f"{path}: 必須為物件")
        return {_decode(k, args[0], path): _decode(v, args[1], f"{path}.{k}") for k, v in value.items()}
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        if type(value) is annotation:
            return value
        return annotation.from_dict(value)
    if annotation is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ContractError(f"{path}: 必須為有限的 JSON 數字")
        return float(value)
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ContractError(f"{path}: 必須為 {annotation.__name__}")
        return value
    raise ContractError(f"{path}: 未支援的欄位型別 {annotation}")


def _encode(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


class Contract:
    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        if type(data) is not dict:
            raise ContractError(f"{cls.__name__}: 必須為物件")
        definitions = {field.name: field for field in fields(cls)}
        unknown = set(data) - definitions.keys()
        missing = {name for name, field in definitions.items()
                   if name not in data and field.default is MISSING and field.default_factory is MISSING}
        if unknown or missing:
            raise ContractError(f"{cls.__name__}: 未知欄位={sorted(unknown)}；缺少欄位={sorted(missing)}")
        hints = get_type_hints(cls)
        return cls(**{name: _decode(value, hints[name], f"{cls.__name__}.{name}")
                      for name, value in data.items()})

    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            object.__setattr__(self, field.name,
                               _decode(getattr(self, field.name), hints[field.name],
                                       f"{type(self).__name__}.{field.name}"))
        self._check()

    def _check(self):
        pass

    def to_dict(self) -> dict[str, Any]:
        return _encode(self)


def _require(condition: bool, message: str):
    if not condition:
        raise ContractError(message)


def _ticker(value: str):
    _require(re.fullmatch(r"[0-9]{4}", value) is not None, "ticker 必須為四位數字字串")


def _unique(values, name: str):
    values = list(values)
    _require(len(values) == len(set(values)), f"{name}: 不可重複")


def _refs(values: tuple[str, ...], prefix: str):
    _require(bool(values), f"{prefix} 引用不可為空")
    _unique(values, f"{prefix} 引用")
    _require(all(re.fullmatch(rf"{prefix}[1-9][0-9]{{0,2}}", v) for v in values), f"{prefix} 引用格式錯誤")


@dataclass(frozen=True)
class PriceBar(Contract):
    trade_date: date
    ticker: str
    market: Literal["TWSE", "TPEX"]
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close_raw: Decimal | None
    return_close: Decimal | None
    volume_shares: int | None
    amount_twd: Decimal | None
    source_key: str
    known_at: datetime | None
    fetched_at: datetime
    raw_sha256: str | None
    data_version: str
    adjustment_status: Literal["raw", "adjusted", "unresolved"]
    price_valid: bool
    tradable: bool

    def _check(self):
        _ticker(self.ticker)
        _require(bool(self.source_key) and bool(self.data_version), "行情須有來源與版本")
        for name in ("open", "high", "low", "close_raw", "return_close"):
            value = getattr(self, name)
            _require(value is None or value > 0, f"{name}: 價格須大於零或為 null")
        _require(self.volume_shares is None or self.volume_shares >= 0, "成交股數不可為負")
        _require(self.amount_twd is None or self.amount_twd >= 0, "成交金額不可為負")
        _require(not self.price_valid or self.close_raw is not None, "有效行情須有原始收盤價")
        _require(not self.tradable or self.price_valid, "可交易行情須有有效價格")
        if self.high is not None and self.low is not None:
            _require(self.high >= self.low, "最高價不可低於最低價")
            for price in (self.open, self.close_raw):
                _require(price is None or self.low <= price <= self.high, "開盤/收盤須在高低價之間")
        if self.raw_sha256 is not None:
            _require(re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256) is not None, "raw_sha256 須為64位十六進位")


@dataclass(frozen=True)
class MarketSnapshot(Contract):
    contract_version: Literal["1.0"]
    snapshot_id: str
    trade_date: date
    previous_trade_date: date
    snapshot_cutoff: datetime
    data_origin: Literal["fixture", "official_cache", "official_live"]
    dataset_version: str
    prices: tuple[PriceBar, ...]
    timezone: Literal["Asia/Taipei"] = "Asia/Taipei"

    def _check(self):
        _require(bool(self.snapshot_id) and bool(self.dataset_version), "快照須有ID與資料集版本")
        _require(self.previous_trade_date < self.trade_date, "前一交易日須早於決策交易日")
        _require(self.snapshot_cutoff.date() == self.trade_date, "截止時間須在本次決策交易日")
        _unique(((p.trade_date, p.ticker) for p in self.prices), "快照行情日期/股票")
        for price in self.prices:
            _require(price.trade_date <= self.previous_trade_date, "盤前快照不可含 T 日或未來行情")
            _require(price.known_at is None or price.known_at <= self.snapshot_cutoff, "行情在快照截止後才已知")
            if self.data_origin != "fixture":
                _require(price.known_at is not None, "正式來源缺少可核實已知時間")
                _require(price.raw_sha256 is not None, "正式來源缺少原始資料hash")


@dataclass(frozen=True)
class Position(Contract):
    ticker: str
    shares: int

    def _check(self):
        _ticker(self.ticker)
        _require(self.shares > 0, "持股須為正整數；零持股省略")


@dataclass(frozen=True)
class AccountSnapshot(Contract):
    contract_version: Literal["1.0"]
    snapshot_id: str
    as_of_trade_date: date
    status: Literal["demo", "projected", "simulated", "official_confirmed"]
    cash_twd: Decimal
    nav_twd: Decimal
    positions: tuple[Position, ...]
    origin: str
    reconciled: bool
    demo: bool
    origin_ref: str | None = None

    def _check(self):
        _require(self.cash_twd >= 0 and self.nav_twd > 0, "現金不可為負，NAV須大於零")
        _require(self.cash_twd <= self.nav_twd, "現金不可大於NAV")
        _require(bool(self.snapshot_id) and bool(self.origin), "帳戶須有ID與來源")
        _unique((p.ticker for p in self.positions), "帳戶持股")
        if self.status == "demo":
            _require(self.demo and not self.reconciled, "demo帳須標記demo且未正式核對")
        if self.status == "official_confirmed":
            _require(not self.demo and self.reconciled and bool(self.origin_ref), "官方已確認帳須有真實核對來源")


@dataclass(frozen=True)
class FeatureRow(Contract):
    ticker: str
    window_start: date
    window_end: date
    values: dict[str, float | None]
    missing_reasons: dict[str, str]
    source_refs: tuple[str, ...]
    observation_ids: tuple[str, ...]
    eligible: bool
    rank: int | None

    def _check(self):
        _ticker(self.ticker)
        _require(self.window_start <= self.window_end, "因子視窗日期顛倒")
        _require(bool(self.source_refs), "因子須保留來源")
        _refs(self.observation_ids, "O")
        _require(self.rank is None or self.rank > 0, "排名須為正整數或null")
        for name, value in self.values.items():
            _require(value is not None or bool(self.missing_reasons.get(name)), f"缺失因子 {name} 須有原因")


@dataclass(frozen=True)
class FeatureTable(Contract):
    contract_version: Literal["1.0"]
    snapshot_id: str
    dataset_version: str
    feature_version: str
    factor_profile: str
    origin: Literal["fixture", "computed"]
    rows: tuple[FeatureRow, ...]

    def _check(self):
        _require(all((self.snapshot_id, self.dataset_version, self.feature_version, self.factor_profile)), "因子須有快照/資料/計算版本")
        _unique((row.ticker for row in self.rows), "因子股票")


@dataclass(frozen=True)
class MarketProposal(Contract):
    regime: Literal["risk_on", "neutral", "risk_off"]
    stance: Literal["aggressive", "neutral", "defensive"]
    cash_target: float
    proposed_cash_range: tuple[float, ...]
    intended_flow: Literal["increase", "hold", "reduce"]
    basis_obs_ids: tuple[str, ...]
    rationale: str
    counter_evidence: str | None

    def _check(self):
        _require(0 <= self.cash_target <= 0.25, "草稿現金目標須在0～25%")
        _require(len(self.proposed_cash_range) == 2, "現金區間須有兩個數字")
        low, high = self.proposed_cash_range
        _require(0 <= low <= self.cash_target <= high <= 0.25, "現金目標/區間不一致")
        _refs(self.basis_obs_ids, "O")
        _require(bool(self.rationale.strip()), "市場提案須有理由")


@dataclass(frozen=True)
class Selection(Contract):
    ticker: str
    conviction: float
    supporting_obs_ids: tuple[str, ...]
    rationale: str
    counter_evidence: str | None

    def _check(self):
        _ticker(self.ticker)
        _require(self.conviction in (0.8, 1.0, 1.2), "conviction 只允許0.8/1.0/1.2")
        _refs(self.supporting_obs_ids, "O")
        _require(bool(self.rationale.strip()), "選股須有理由")


@dataclass(frozen=True)
class HeldReview(Contract):
    ticker: str
    intent: Literal["keep", "rebalance", "exit"]
    supporting_obs_ids: tuple[str, ...]
    rationale: str
    counter_evidence: str | None

    def _check(self):
        _ticker(self.ticker)
        _refs(self.supporting_obs_ids, "O")
        _require(bool(self.rationale.strip()), "持股review須有理由")


@dataclass(frozen=True)
class AgentDraft(Contract):
    market_proposal: MarketProposal
    selections: tuple[Selection, ...]
    held_reviews: tuple[HeldReview, ...]

    def _check(self):
        _require(20 <= len(self.selections) <= 30, "草稿須提案20～30檔；實際正股數仍由後續驗證")
        _require(len(self.held_reviews) <= 30, "持股review不可超過30筆")
        _unique((s.ticker for s in self.selections), "草稿選股")
        _unique((r.ticker for r in self.held_reviews), "原持股review")

    def validate_context(self, *, allowed_tickers, held_tickers, observation_ids):
        allowed, held, observations = set(allowed_tickers), set(held_tickers), set(observation_ids)
        _require({s.ticker for s in self.selections} <= allowed, "草稿選股超出候選池")
        _require({r.ticker for r in self.held_reviews} == held, "草稿須完整且精確覆蓋原持股")
        refs = set(self.market_proposal.basis_obs_ids)
        for item in (*self.selections, *self.held_reviews):
            refs.update(item.supporting_obs_ids)
        _require(refs <= observations, "草稿引用不存在的觀察")


@dataclass(frozen=True)
class TargetWeight(Contract):
    ticker: str
    target_weight: Decimal
    reason_refs: tuple[str, ...]

    def _check(self):
        _ticker(self.ticker)
        _require(0 <= self.target_weight <= 1, "內部權重須在0～1；官方個股上限另驗")
        _refs(self.reason_refs, "O")


@dataclass(frozen=True)
class PortfolioProposal(Contract):
    contract_version: Literal["1.0"]
    market_snapshot_id: str
    account_snapshot_id: str
    allocation_method: Literal["fixture", "equal_weight", "capped_score_inverse_vol"]
    cash_target: Decimal
    targets: tuple[TargetWeight, ...]

    def _check(self):
        _unique((t.ticker for t in self.targets), "配置股票")
        _require(0 <= self.cash_target <= 1, "內部現金權重須在0～1")
        _require(sum((t.target_weight for t in self.targets), Decimal(0)) + self.cash_target == 1, "完整目標權重加現金須等於1")

    def validate_context(self, *, held_tickers, selected_tickers):
        _require({t.ticker for t in self.targets} == set(held_tickers) | set(selected_tickers), "完整配置須包含全部原持股與選股，退出股也須列零權重")


@dataclass(frozen=True)
class ValidationCheck(Contract):
    check_id: str
    severity: Literal["PASS", "WARN", "BLOCK"]
    passed: bool
    details: str
    related_ids: tuple[str, ...]


@dataclass(frozen=True)
class ValidationReport(Contract):
    contract_version: Literal["1.0"]
    scope: Literal["contract_only", "dplan_local", "official"]
    mode: Literal["demo", "formal"]
    official_rules_confirmed: bool
    account_reconciled: bool
    real_agent_decision: bool
    submission_ready: bool
    checks: tuple[ValidationCheck, ...]

    def _check(self):
        _unique((c.check_id for c in self.checks), "檢查ID")
        if self.submission_ready:
            _require(self.scope != "contract_only" and self.mode == "formal", "合約檢查/demo不可標正式可提交")
            _require(self.official_rules_confirmed and self.account_reconciled and self.real_agent_decision, "正式可提交須具備規則/帳戶/真實決策")
            _require(bool(self.checks) and not any(c.severity == "BLOCK" and not c.passed for c in self.checks), "有阻擋項或缺檢查不可提交")


@dataclass(frozen=True)
class DatasetSplitPlan(Contract):
    """未來研究用切分設定；本批只檢查日期，不執行回測或交易日gap。"""

    dataset_version: str
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date
    label_horizon_trading_days: int
    gap_trading_days: int
    final_test_locked: bool

    def _check(self):
        _require(self.train_start <= self.train_end < self.validation_start <= self.validation_end
                 < self.test_start <= self.test_end, "訓練、驗證、測試須依時間先後且不可重疊")
        _require(self.label_horizon_trading_days > 0, "標籤預測期間須為正交易日數")
        _require(self.gap_trading_days >= self.label_horizon_trading_days, "切分間隔設定須至少涵蓋標籤期間")
        _require(self.final_test_locked, "保留最終測試區間，不能用來調參")
