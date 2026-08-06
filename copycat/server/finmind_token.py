"""FinMind token 解析(server 不載 dotenv:env → repo root .env 逐 key fallback)。

自 `oi_levels.py` 抽出(market-overview R2 Task 1):breadth 引擎與 OI 撐壓共用同一把
token,兩份各自解析必然漂移。**stdlib-only** —— conftest 是每一條測試都載的模組,
中和 FinMind 憑證時不該被迫拉進 fastapi([live] extras 未裝的環境會 ImportError)。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_KEY = "FINMIND_TOKEN"


def _dotenv_values() -> dict[str, str]:
    """repo root .env 逐 key 解析。utf-8-sig:Windows BOM 會讓首 key 靜默失效;
    never-raise:壞檔視同無檔(對齊 capital/factory 與 notify 的慣例)。"""
    env_file = Path(".env")
    try:
        if not env_file.exists():
            return {}
        text = env_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(".env 讀取失敗,%s 的 dotenv fallback 視同無檔:%s", _ENV_KEY, e)
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            out[key.strip()] = value.strip()
    return out


_dotenv_cache: dict[str, str] | None = None


def resolve_token() -> str | None:
    """`FINMIND_TOKEN in os.environ` 即用(含空字串 = 未設,可壓制 .env)→ 否則 .env。

    空字串當未設而**不**往下 fallback:operator 用 `set FINMIND_TOKEN=` 清空是明確的
    「這台不要打 FinMind」,被檔案值復活就違反那個意圖。
    """
    global _dotenv_cache
    if _ENV_KEY in os.environ:
        return os.environ[_ENV_KEY].strip() or None
    if _dotenv_cache is None:
        _dotenv_cache = _dotenv_values()
    return (_dotenv_cache.get(_ENV_KEY) or "").strip() or None
