"""家數帶 / 騰落線的輪詢與退避門檻(market-overview R2 design §5)。

慣例沿用 `signals_config.py`:frozen dataclass 帶預設值,`configs/breadth.json`
逐鍵覆寫,未知鍵直接 raise(打錯字不該靜默套預設)。設定檔不存在 = 全用預設,
不是錯誤 —— repo 預設不附 `configs/breadth.json`,要調門檻才建。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from copycat.configio import load_dataclass_json

__all__ = ["CONFIG_PATH", "BreadthConfig", "load_breadth_config"]

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "breadth.json"


@dataclass(frozen=True, slots=True)
class BreadthConfig:
    poll_secs: float = 10.0  # 輪詢間隔(FinMind snapshot)
    window_start: str = "08:55"  # 台北;poll 窗起(HH:MM)
    window_end: str = "13:40"  # 台北;poll 窗迄(HH:MM)
    stale_secs: float = 30.0  # 窗內距上次成功超過此秒數 → state.stale
    backoff_max_secs: float = 60.0  # 連續失敗退避上限(10→20→40→60)
    quota_backoff_secs: float = 300.0  # FinMind 402 配額用盡的退避
    event_cooldown_secs: float = 600.0  # 市場事件(鎖板/開板)對帳冷卻,抑制邊界抖動
    chain_ttl_hours: float = 168.0  # 產業鏈對照表快取 TTL(7 天;過期也先用舊表)


def load_breadth_config(path: Path = CONFIG_PATH) -> BreadthConfig:
    """讀設定檔逐鍵覆寫;檔案不存在 → 全預設;未知鍵 → ValueError。"""
    if not path.exists():
        return BreadthConfig()
    return load_dataclass_json(
        path,
        BreadthConfig,
        tuple_keys=(),
        unknown_label="未知家數帶參數",
    )
