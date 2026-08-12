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
    window_start: str = "09:00"  # 台北;poll 窗起(HH:MM)。09:00 = 排除 08:55–09:00
    # 試撮窗(2026-08-12 拍板):試撮價可被假單操縱,家數/rows/連板收了會與騰落線/
    # 事件流(分鐘域 gate 天然不收)矛盾,且試撮漲停會讓連板誤 +1 —— 一律不進系統。
    window_end: str = "13:40"  # 台北;poll 窗迄(HH:MM)
    stale_secs: float = 30.0  # 窗內距上次成功超過此秒數 → state.stale
    backoff_max_secs: float = 60.0  # 連續失敗退避上限(10→20→40→60)
    quota_backoff_secs: float = 300.0  # FinMind 402 配額用盡的退避
    event_cooldown_secs: float = 600.0  # 市場事件(鎖板/開板)對帳冷卻,抑制邊界抖動
    chain_ttl_hours: float = 168.0  # 產業鏈對照表快取 TTL(7 天;過期也先用舊表)


def load_breadth_config(path: Path = CONFIG_PATH) -> BreadthConfig:
    """讀設定檔逐鍵覆寫;檔案不存在 → 全預設;未知鍵 / 值域違反 → ValueError。

    dataclass 預設路徑(檔不存在)不必驗 —— 預設值恆合法,驗的是**覆寫進來的值**。
    """
    if not path.exists():
        return BreadthConfig()
    cfg = load_dataclass_json(
        path,
        BreadthConfig,
        tuple_keys=(),
        unknown_label="未知家數帶參數",
    )
    if cfg.event_cooldown_secs <= 0:
        # 廣度事件 id 不含 `touch_count`,同 `(code, kind, direction, as_of)` 的重覆
        # 抑制**全靠**正冷卻;關掉冷卻後同 id 兩則會被前端去重吃掉一則,而畫面上
        # 只是「這則沒出現」(review round-2 HR-4)
        raise ValueError(
            f"event_cooldown_secs 必須 > 0(取得 {cfg.event_cooldown_secs}):"
            "廣度事件的 id 唯一性靠冷卻抑制同 as_of 重覆,關掉會讓前端去重吃掉真事件"
        )
    return cfg
