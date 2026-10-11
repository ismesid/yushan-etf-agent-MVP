"""CSV只供檢查；JSON保留主資料，空欄表示未知，不以顯示值回寫核心。"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def _json_decimal(value):
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    raise TypeError("CSV JSON欄只支援可重現的有限Decimal")


def _cell(value):
    if value is None:
        return ""
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("CSV數值不可為NaN或Infinity")
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, default=_json_decimal)
    if type(value) is float and not math.isfinite(value):
        raise ValueError("CSV數值不可為NaN或Infinity")
    return str(value)


def write_csv_view(path: Path | str, columns: Sequence[str], rows: Iterable[Mapping]) -> str:
    """UTF-8 BOM、Decimal原字串、None空欄；回傳完整檔案SHA-256。"""
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(value) for key, value in row.items()})
    return hashlib.sha256(path.read_bytes()).hexdigest()
