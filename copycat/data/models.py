"""1K bar 標準模型與時間轉換(沿 neigui 研究慣例:09:01 bar = 索引 0)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bar1K:
    m: int  # 台北分鐘索引,09:01=0 … 13:30=269(bar 以收盤時刻標記)
    open: float
    high: float
    low: float
    close: float
    volume: float  # 張
    up_volume: float  # 外盤張數(價漲方向成交)
    down_volume: float  # 內盤張數
    unch_volume: float


def taipei_min(time_utc: str) -> int:
    """UTC HHMMSS(無前導零)→ 台北分鐘索引(09:01=0 … 13:30=269)."""
    s = time_utc.zfill(6)
    hh, mm = int(s[:2]) + 8, int(s[2:4])
    return (hh - 9) * 60 + mm - 1


def fmt_min(m: int) -> str:
    """分鐘索引 → 'HH:MM'(台北)."""
    total = 9 * 60 + 1 + m
    return f"{total // 60:02d}:{total % 60:02d}"


def _num(raw: dict[str, str], key: str) -> float:
    v = raw[key]
    return float(v) if v else 0.0


def parse_raw_bar(raw: dict[str, str]) -> Bar1K:
    """neigui 原始 bar dict(全字串)→ Bar1K。欄位缺漏 raise ValueError."""
    try:
        return Bar1K(
            m=taipei_min(raw["Time"]),
            open=float(raw["Open"]),
            high=float(raw["High"]),
            low=float(raw["Low"]),
            close=float(raw["Close"]),
            volume=_num(raw, "Volume"),
            up_volume=_num(raw, "UpVolume"),
            down_volume=_num(raw, "DownVolume"),
            unch_volume=_num(raw, "UnchVolume"),
        )
    except KeyError as exc:
        raise ValueError(f"raw bar 欄位缺漏: {exc}") from exc
