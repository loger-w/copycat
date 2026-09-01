"""訊號偵測門檻(stock-signals design §2)— 全部 magic number 收在此處.

慣例沿用 `strategy_config.py`:frozen dataclass 帶預設值,`configs/signals.json`
逐鍵覆寫,未知鍵直接 raise(打錯字不該靜默套預設)。設定檔不存在 = 全用預設,
不是錯誤 —— repo 預設不附 `configs/signals.json`,要調門檻才建。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from copycat.configio import load_dataclass_json

__all__ = ["CONFIG_PATH", "SignalsConfig", "load_signals_config"]

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "signals.json"


@dataclass(frozen=True, slots=True)
class SignalsConfig:
    # --- CDP 穿越(SC-1)---
    cdp_rearm_ticks: int = 5  # 觸發後需離開該線 N 個 tick 才解除 suppressed
    # 觸發後需**連續**待在線外 N 秒才解除 suppressed;0 = 離線即解除(舊行為)
    cdp_rearm_dwell_secs: float = 300.0
    cdp_cooldown_secs: float = 600.0  # per (code, level) 冷卻
    # --- 爆拉 / 爆跌(SC-2)---
    surge_pct: float = 2.0  # 窗內漲跌幅門檻(%)
    surge_window_secs: float = 300.0  # 滾動窗長度(爆量共用)
    surge_cooldown_secs: float = 1800.0  # per (code, kind) 冷卻
    # --- 爆拉回檔(spec #174)---
    # 武裝參數沿用 surge_pct / surge_window_secs(per-rule config 讓兩者獨立,同 vol_burst 借窗)。
    # pullback_pct 是 rule_config 的映射載體:detector 只透過 per-rule config 讀到它,而該欄
    # 恆由規則 params["pct"] 覆寫(種子卡的 pct 又是綁名稱的字面值)—— 在 configs/signals.json
    # 覆寫本鍵**沒有任何效果**,不是可調門檻(two-axis review N-1,刻意留欄不留旋鈕)。
    pullback_pct: float = 1.0  # 自波峰回落幅度門檻(%);僅 per-rule 映射載體,見上
    pullback_cooldown_secs: float = 60.0  # per code 冷卻(一波一則已由重武裝把關,這裡只防 flapping)
    # --- 爆量(SC-3)---
    vol_ratio: float = 3.0  # 窗內量 / 全日均量的倍數門檻
    vol_min_elapsed_min: float = 15.0  # 開盤未滿此分鐘數不評估(均量不穩)
    vol_min_window_lots: int = 100  # 窗內量地板(張)
    vol_min_day_lots: int = 500  # 全日量地板(張)— 擋低量股
    vol_cooldown_secs: float = 1800.0  # per code 冷卻
    # --- 鎖漲跌停 / 打開(SC-4)---
    limit_cooldown_secs: float = 600.0
    # --- 接線層(SignalHub)---
    discord_per_min: int = 30  # Discord 每分鐘送出上限(只擋 Discord,不擋 jsonl/WS)
    basis_gap_secs: float = 0.2  # CDP 基準 worker 逐檔間隔(測試注入 0)
    basis_retry_delay_secs: float = 30.0  # CDP 基準取得失敗後的重試間隔(X-2b;測試注入 0)


def load_signals_config(path: Path = CONFIG_PATH) -> SignalsConfig:
    """讀設定檔逐鍵覆寫;檔案不存在 → 全預設;未知鍵 → ValueError。"""
    if not path.exists():
        return SignalsConfig()
    return load_dataclass_json(
        path,
        SignalsConfig,
        tuple_keys=(),
        unknown_label="未知訊號參數",
    )
