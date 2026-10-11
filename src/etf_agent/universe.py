"""讀取 F05 v1 股票白名單，核對格式及本機來源；不取得行情。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


class UniverseError(ValueError):
    """白名單、版本或來源核對失敗。"""


COLUMNS = ("ticker", "name", "market")
EXPECTED_COUNTS = {"TWSE": 100, "TPEX": 50}


@dataclass(frozen=True)
class Stock:
    ticker: str
    name: str
    market: str

    def __post_init__(self):
        if not isinstance(self.ticker, str) or not re.fullmatch(r"[0-9]{4}", self.ticker):
            raise UniverseError("ticker 須為四位 ASCII 數字字串")
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise UniverseError(f"{self.ticker} 名稱不可空白或含首尾空格")
        if any(character in self.name for character in "\r\n\x00"):
            raise UniverseError(f"{self.ticker} 名稱不可含換行或空字元")
        if self.market not in EXPECTED_COUNTS:
            raise UniverseError(f"{self.ticker} 市場須為 TWSE 或 TPEX")


@dataclass(frozen=True)
class Universe:
    stocks: tuple[Stock, ...]
    universe_version: str
    source_path: Path
    source_sha256: str
    csv_sha256: str

    @property
    def allowed_tickers(self) -> frozenset[str]:
        return frozenset(stock.ticker for stock in self.stocks)

    def lookup(self, ticker: str, *, market: str | None = None) -> Stock:
        for stock in self.stocks:
            if stock.ticker == ticker:
                if market is not None and stock.market != market:
                    raise UniverseError(f"{ticker} 市場不符：F05 為 {stock.market}，收到 {market}")
                return stock
        raise UniverseError(f"{ticker} 不在 F05 白名單")

    def select_market(self, market: str) -> tuple[Stock, ...]:
        if market not in EXPECTED_COUNTS:
            raise UniverseError("市場須為 TWSE 或 TPEX")
        return tuple(stock for stock in self.stocks if stock.market == market)


def _require_mapping(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise UniverseError(f"manifest.{name} 須為 JSON object")
    return value


def _verify_hash(content: bytes, expected: object, name: str) -> str:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UniverseError(f"{name} SHA-256 格式錯誤")
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise UniverseError(f"{name} SHA-256 不符，停止讀取白名單")
    return actual


def _resolve_reference(base: Path, value: object, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise UniverseError(f"manifest.{name} 路徑不可空白")
    return (base / value).resolve()


def load_universe(
    csv_path: Path | str = Path("data/universe.csv"), *, manifest_path: Path | str | None = None,
) -> Universe:
    """核對本機 PDF／CSV 雜湊及 F05 v1 檔數，回傳可重用股票池。

    manifest 內的路徑以 manifest 所在目錄為基準。檔案缺失、版本不符或
    名單錯誤會拋 UniverseError；不補資料、不下載，也不代表行情可交易。
    """
    csv_path = Path(csv_path).resolve()
    manifest_path = Path(manifest_path).resolve() if manifest_path is not None else csv_path.with_suffix(".manifest.json")
    try:
        metadata = _require_mapping(json.loads(manifest_path.read_text(encoding="utf-8-sig")), "root")
        if metadata.get("format_version") != "1.0":
            raise UniverseError("不支援的白名單 manifest 版本")
        source = _require_mapping(metadata.get("official_source"), "official_source")
        csv_info = _require_mapping(metadata.get("csv"), "csv")
        if source.get("id") != "F05" or source.get("version") != "v1":
            raise UniverseError("本批僅支援官方 F05 v1")
        if metadata.get("expected_counts") != EXPECTED_COUNTS:
            raise UniverseError("F05 v1 檔數須為 100 TWSE／50 TPEX")
        if csv_info.get("columns") != list(COLUMNS):
            raise UniverseError("manifest CSV 欄位須為 ticker,name,market")
        indexed_csv = _resolve_reference(manifest_path.parent, csv_info.get("path"), "csv.path")
        if indexed_csv != csv_path:
            raise UniverseError("manifest CSV 索引與指定檔案不符")
        source_path = _resolve_reference(manifest_path.parent, source.get("path"), "official_source.path")
        source_hash = _verify_hash(source_path.read_bytes(), source.get("sha256"), "官方 F05 PDF")
        content = csv_path.read_bytes()
        csv_hash = _verify_hash(content, csv_info.get("sha256"), "白名單 CSV")
        version = f"F05-v1-{csv_hash[:12]}"
        if metadata.get("universe_version") != version:
            raise UniverseError("白名單 universe_version 與 CSV 內容不符")

        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        if next(reader, None) != list(COLUMNS):
            raise UniverseError("CSV 欄位須依序為 ticker,name,market，不接受額外欄位")
        stocks: list[Stock] = []
        seen: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(COLUMNS):
                raise UniverseError(f"CSV 第 {line_number} 列欄位數錯誤")
            stock = Stock(*row)
            if stock.ticker in seen:
                raise UniverseError(f"CSV 第 {line_number} 列股票代號重複：{stock.ticker}")
            seen.add(stock.ticker)
            stocks.append(stock)
        counts = dict(Counter(stock.market for stock in stocks))
        if counts != EXPECTED_COUNTS:
            raise UniverseError(f"F05 v1 須有 150 檔（100 TWSE／50 TPEX）；實際為 {counts}")
        return Universe(tuple(stocks), version, source_path, source_hash, csv_hash)
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
        raise UniverseError(f"白名單檔案讀取失敗：{exc}") from exc
