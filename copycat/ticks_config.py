"""盤中個股 tick 存檔的設定(spec #257)。

慣例沿用 `breadth_config.py`:frozen dataclass 帶預設值,`configs/ticks.json` 逐鍵覆寫,
未知鍵直接 raise(打錯字不該靜默套預設)。設定檔不存在 = 全用預設 —— repo 預設不附
`configs/ticks.json`,盤中發現存檔拖累看盤時建一份 `{"enabled": false}` 重啟即關。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from copycat.configio import load_dataclass_json

__all__ = ["CONFIG_PATH", "TicksConfig", "load_ticks_config"]

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "ticks.json"


@dataclass(frozen=True, slots=True)
class TicksConfig:
    enabled: bool = True  # False = 零檔案、零 handle、不排轉檔
    dir: str = "data/ticks"  # 相對路徑以 repo root 為基準(app 層解析)
    flush_secs: float = 30.0  # 64 KB 緩衝之外的定時 flush(當機最多丟這麼久)
    compact_time: str = "13:45"  # 台北 HH:MM;交易日轉 parquet 的時刻
    retry_secs: float = 900.0  # 轉檔失敗的重試間隔
    retry_max: int = 3  # 轉檔重試上限,再失敗 WARNING 放棄(jsonl 留著)
    compact_timeout_secs: float = 300.0  # 轉檔子程序逾時 kill,算失敗一次
    book_keep_days: int = 120  # 簿檔保留交易日數;成交檔永久


def load_ticks_config(path: Path = CONFIG_PATH) -> TicksConfig:
    """讀設定檔逐鍵覆寫;檔案不存在 → 全預設;未知鍵 → ValueError。"""
    if not path.exists():
        return TicksConfig()
    return load_dataclass_json(
        path,
        TicksConfig,
        tuple_keys=(),
        unknown_label="未知 tick 存檔參數",
    )
