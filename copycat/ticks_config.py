"""盤中個股 tick 存檔的設定(spec #257)。

慣例沿用 `breadth_config.py`:frozen dataclass 帶預設值,`configs/ticks.json` 逐鍵覆寫,
未知鍵直接 raise(打錯字不該靜默套預設)。設定檔不存在 = 全用預設 —— repo 預設不附
`configs/ticks.json`,盤中發現存檔拖累看盤時建一份 `{"enabled": false}` 重啟即關。

值域在建構當下就擋(round-1 Spec F-07):`book_keep_days` 0 會讓保留一次刪光所有簿檔、
`flush_secs` 0 會讓 timer 空轉、`retry_secs` 0 會讓 13:45 起每輪 tick 再開一個子程序 ——
這些在 log 上零訊號,只能在載入時拒絕。`compact_time` 以 `strptime("%H:%M")` 驗證兼解析
(pr-263 F-24:`isdigit()` 手刻會放行全形「１３:４５」),`due_time()` 給排程用。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from copycat.configio import load_dataclass_json

__all__ = ["CONFIG_PATH", "REPO_ROOT", "TicksConfig", "load_ticks_config", "resolve_ticks_dir"]

#: repo root 的唯一推導點(`copycat/` 的上一層);寫入端目錄解析與轉檔子程序的 cwd 都引這一顆,
#: 不各自 `parents[n]` 一份(檔案搬家只壞一邊 → 子程序靜默跑到另一棵樹)
REPO_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = REPO_ROOT
CONFIG_PATH = REPO_ROOT / "configs" / "ticks.json"


def _parse_hhmm(value: str) -> _dt.time:
    """`HH:MM` → time;非此形(含全形數字 / 越界)→ ValueError(strptime 一次做完驗證與解析)。"""
    if not isinstance(value, str) or not value.isascii():
        raise ValueError(f"compact_time 須為 HH:MM(收到 {value!r})")
    try:
        return _dt.datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"compact_time 須為 HH:MM(收到 {value!r})") from exc


@dataclass(frozen=True, slots=True)
class TicksConfig:
    enabled: bool = True  # False = 零檔案、零 handle、不排轉檔
    dir: str = "data/ticks"  # 相對路徑以 repo root 為基準(`resolve_ticks_dir`)
    flush_secs: float = 30.0  # 64 KB 緩衝之外的定時 flush(當機最多丟這麼久)
    compact_time: str = "13:45"  # 台北 HH:MM;交易日轉 parquet 的時刻
    retry_secs: float = 900.0  # 轉檔失敗的重試間隔
    retry_max: int = 3  # 轉檔重試上限,再失敗 WARNING 放棄(jsonl 留著)
    compact_timeout_secs: float = 300.0  # 轉檔子程序逾時 kill,算失敗一次
    book_keep_days: int = 120  # 簿檔保留交易日數;成交檔永久

    def __post_init__(self) -> None:
        if self.flush_secs <= 0:
            raise ValueError(f"flush_secs 須 > 0(收到 {self.flush_secs})")
        if self.retry_secs <= 0:
            raise ValueError(f"retry_secs 須 > 0(收到 {self.retry_secs})")
        if self.retry_max < 0:
            raise ValueError(f"retry_max 須 ≥ 0(收到 {self.retry_max})")
        if self.compact_timeout_secs <= 0:
            raise ValueError(f"compact_timeout_secs 須 > 0(收到 {self.compact_timeout_secs})")
        if self.book_keep_days < 1:
            raise ValueError(f"book_keep_days 須 ≥ 1(收到 {self.book_keep_days};0 = 一次刪光簿檔)")
        _parse_hhmm(self.compact_time)

    def due_time(self) -> _dt.time:
        """`compact_time` 解析後的 time(排程唯一的取用點;不再各自 split)。"""
        return _parse_hhmm(self.compact_time)


def resolve_ticks_dir(cfg: TicksConfig, *, base_dir: Path = _REPO_ROOT) -> Path:
    """`dir` 相對路徑以 repo root 為基準、絕對路徑照用;寫入端與 CLI 共用同一條規則。"""
    d = Path(cfg.dir)
    return d if d.is_absolute() else base_dir / d


def load_ticks_config(path: Path = CONFIG_PATH) -> TicksConfig:
    """讀設定檔逐鍵覆寫;檔案不存在 → 全預設;未知鍵 / 出界 → ValueError。"""
    if not path.exists():
        return TicksConfig()
    return load_dataclass_json(
        path,
        TicksConfig,
        tuple_keys=(),
        unknown_label="未知 tick 存檔參數",
    )
