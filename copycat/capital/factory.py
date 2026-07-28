"""從環境變數組裝 CapitalClient 單例(get_capital;結構對照 treading-king capital_factory)。

關鍵差異(user 拍板):CAPITAL_MAX_QTY / CAPITAL_MAX_AMOUNT 未設/空/0/解析失敗
→ None = 不限(safety 閘跳過該項),與 treading-king 的 fail-closed(未設=拒單)相反。

CAPITAL_ENV 未知值不可默認正式:SetAuthority 不呼叫/失敗的預設就是正式環境,
拼錯 env 寧可整個功能不啟用,也不可疑似落在真錢環境 → None + logger.error。
prod 啟用時印 banner(帳號只露末 4 碼)— 誤觸正式戶要在 log 明顯可見(SC-10)。

只建構不 start(SkcomCapitalCom 建構子惰性,不載 DLL);啟停由 app lifespan 負責。
測試重置慣例:monkeypatch.setattr(factory, "_client", None)。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from copycat.capital.client import CapitalClient
from copycat.capital.com import SkcomCapitalCom
from copycat.capital.safety import SafetyConfig

logger = logging.getLogger(__name__)

_client: CapitalClient | None = None

_VALID_ENVS = ("test", "prod")


def _env_limit(name: str) -> float | None:
    """上限環境變數 → 數值或 None(=不限)。未設/空/0/負值/解析失敗都是 None;
    解析失敗要留 warning — user 以為設了上限而實際不限,必須看得到。"""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r 解析失敗 → 視為未設(該閘不限)", name, raw)
        return None
    if value <= 0:
        return None
    return value


def get_capital() -> CapitalClient | None:
    """組裝並快取 CapitalClient;未設定 CAPITAL_USER_ID 時回 None(功能未啟用)。"""
    global _client
    if _client is not None:
        return _client
    user_id = (os.getenv("CAPITAL_USER_ID") or "").strip()
    if not user_id:
        return None
    env = (os.getenv("CAPITAL_ENV") or "test").strip().lower()
    if env not in _VALID_ENVS:
        logger.error("CAPITAL_ENV=%r 不是 test/prod,群益功能不啟用", env)
        return None
    max_qty = _env_limit("CAPITAL_MAX_QTY")
    safety = SafetyConfig(
        order_enabled=(os.getenv("CAPITAL_ORDER_ENABLED") or "").strip().lower() == "true",
        max_qty=int(max_qty) if max_qty is not None else None,
        max_amount=_env_limit("CAPITAL_MAX_AMOUNT"),
    )
    full_account = (os.getenv("CAPITAL_FULL_ACCOUNT") or "").strip()
    if env == "prod":
        # 正式環境 banner:誤觸真錢環境要在啟動 log 一眼看出;帳號只露末 4 碼
        tail = (full_account or user_id)[-4:]
        logger.warning("群益正式環境 | 帳號 ****%s", tail)
    audit_base = Path(os.getenv("CAPITAL_AUDIT_DIR") or os.getenv("TXO_AUDIT_DIR") or "data/audit")
    _client = CapitalClient(
        SkcomCapitalCom(dll_dir=(os.getenv("CAPITAL_DLL_DIR") or "").strip() or None),
        user_id=user_id,
        password=(os.getenv("CAPITAL_PASSWORD") or "").strip(),
        full_account=full_account,
        env=env,
        safety=safety,
        audit_base=audit_base,
    )
    return _client
