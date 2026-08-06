"""industry chain 的 disk cache(market-overview R4 design §4.2)。

`breadth_engine._save` / `_restore` 同款紀律:tmp + `os.replace` 原子寫(讀者永遠
看到完整的一份),版本 / 形狀不符一律回 `None` 讓呼叫端當「沒有快取」處理 ——
never-raise,壞檔只降級成一次 FinMind 取數,不得拖垮 poll 或 boot。

**`fetched_at` 是 epoch(`time.time()`,由呼叫端供)不是單調鐘**:TTL 要跨重啟
算得準,而單調鐘的原點每次 process 重啟都不同,落檔後的值下次讀出來毫無意義。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_FILE_VERSION = 1


def load_chain(path: Path) -> tuple[list[dict], float] | None:
    """讀 chain 快取,回 `(rows, fetched_at)`;檔缺 / 壞檔 / 形狀不符一律 `None`。"""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        logger.warning("chain 快取讀取失敗(視為無快取):%r", e)
        return None
    if not isinstance(payload, dict) or payload.get("_version") != _FILE_VERSION:
        logger.warning("chain 快取版本不符(視為無快取):%s", path)
        return None
    rows = payload.get("rows")
    fetched_at = payload.get("fetched_at")
    if not isinstance(rows, list) or not isinstance(fetched_at, (int, float)):
        logger.warning("chain 快取形狀不符(視為無快取):%s", path)
        return None
    return rows, float(fetched_at)


def save_chain(path: Path, rows: list[dict], fetched_at: float) -> None:
    """tmp + `os.replace` 原子寫;落檔失敗只降級(記憶體那份照用),不外拋。"""
    payload = {
        "_version": _FILE_VERSION,
        "fetched_at": fetched_at,
        "rows": rows,
    }
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("chain 快取落檔失敗(續行):%r", e)
