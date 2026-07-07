# 評分引擎 + 歷史 Replay(回測基建 MVP)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `docs/strategy.md` Phase 2(鎖板品質)+ Phase 3(T+1 開盤)訊號實作成事件驅動評分引擎 + 歷史 replay CLI,重現 `docs/evidence/` golden 數字。

**Architecture:** 純 stdlib Python package `copycat/`。資料層把 neigui 種子資料(1K/日線/事件)標準化到 `data/`;引擎是逐 bar 餵入的狀態機(無 lookahead 為結構保證);replay runner 對事件清單跑引擎,輸出 events.jsonl + summary.md;validate 對照 evidence golden。

**Tech Stack:** Python 3.13(venv)、stdlib only(runtime 零依賴)、pytest + ruff + pyright(dev)。

**Spec:** `docs/superpowers/specs/2026-07-07-broker-fingerprint-replay-design.md`(本計畫的需求來源,任務衝突時以 spec 為準)

## Global Constraints

- 每個 `.py` 第一行(註解後)必須是 `from __future__ import annotations`
- Type hints 無例外(函式參數 + 回傳、module-level globals);`dict | None` / `list[dict]` 風格,不用 `Optional` / `List`
- `logger = logging.getLogger(__name__)`,**禁止 `print`**(CLI 的使用者輸出走 `sys.stdout.write` 或 logging,報表寫檔)
- ruff line-length 100;pyright basic;pytest(全部同步 code,無 async)
- 引擎(`copycat/engine/`)零 IO 依賴;`feed()` 時間戳倒流 raise;不 catch 不懂的錯誤
- 策略門檻一律進 `StrategyConfig`,不散落在引擎 code
- watchlist 只影響事件標記/報表分組,不進評分邏輯
- 漲停價 = 事件自帶 `limitup_close`;T+1 觸停/漲停開閾值 = 前日漲停 ×1.095
- 時間座標 = 台北分鐘索引:09:01 bar = 0 … 13:30 bar = 269(沿研究慣例,bar 以收盤時刻標記)
- 資料單位:量一律「張」(日線 volume 是股,匯入時 ÷1000)
- 種子資料來源(唯讀,絕不寫入):`C:\side-project\neigui\backend\data\research\five-tigers\`
- Commit 風格:`<type>(<scope>): <subject>`,本計畫 scope 用 `replay`;測試與實作同 commit
- 測試 mock 走 `monkeypatch` / `tmp_path`,不用 `unittest.mock`

## File Structure

```
pyproject.toml                  # Task 1
.gitignore                      # Task 1
copycat/__init__.py             # Task 1
copycat/data/__init__.py        # Task 2
copycat/data/models.py          # Task 2:Bar1K + 時間轉換
copycat/data/store.py           # Task 3:標準化 1K 的讀寫(data/1k/)
copycat/data/daily.py           # Task 4:日線 loader(adv20 / one_price / next_date / limitup set / board_streak)
copycat/data/import_neigui.py   # Task 5:種子資料匯入 + 事件清單構建 + manifest
copycat/strategy_config.py      # Task 6:StrategyConfig(全部門檻)
copycat/engine/__init__.py      # Task 7
copycat/engine/lock_quality.py  # Task 7-8:LockTracker + LockQualitySignals + tier
copycat/engine/t1_open.py       # Task 9:EventContext + T1Tracker + T1OpenSignals
copycat/watchlist.py            # Task 5(事件標記用)
copycat/replay/__init__.py      # Task 10
copycat/replay/runner.py        # Task 10:事件迴圈 → events.jsonl
copycat/replay/report.py        # Task 11:summary.md 彙總表
copycat/replay/validate.py      # Task 12:golden 對照
copycat/replay/compare.py       # Task 13:兩份 run 並排
copycat/cli.py                  # Task 5/10/12/13 逐步接 subcommand
copycat/__main__.py             # Task 5(`python -m copycat`)
watchlists/four_tigers.json     # Task 5
watchlists/five_tigers.json     # Task 5
tests/…                         # 每 task 對應 test 檔
data/                           # git-ignored(匯入產物)
out/                            # git-ignored(replay 產物)
```

**neigui 種子資料格式(已盤點,2026-07-07)**:

- `k1_bars.jsonl` / `k1_control.jsonl`:每行 `{"stock_id": "1104", "date": "2025-09-10", "bars": [{"Time": "10100"(UTC HHMMSS 無前導零,bar 收盤時刻), "Open": "30.05", …, "Volume": "1936", "UpTick", "UpVolume", "DownTick", "DownVolume", "UnchVolume"}(全字串)]}`
- `prices.csv`:`stock_id,date,open,high,low,close,spread,volume`(volume = 股)
- `all_limitup_events.csv`:`stock_id,date,close,spread,pct,volume`(3511 漲停事件;close = 漲停收盤價)
- 虎事件 CSV(在 copycat repo):`docs/evidence/five_tigers_events_2025-06-30_2026-06-26.csv`,per-tiger rows,欄位 `date,stock_id,stock_name,tiger,broker_id,buy_lots,…,limitup_close,t1_date,…,gap,again`
- `ticks/`:MVP 不匯入(僅虎事件有,訊號全 1K-based)

---

### Task 1: 專案 scaffold(pyproject + venv + 工具鏈 smoke)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `copycat/__init__.py`
- Test: `tests/test_sanity.py`

**Interfaces:**
- Produces: 可運作的 venv(`.venv/`)與 `pytest` / `ruff` / `pyright` 指令;後續所有 task 用 `.venv\Scripts\python -m pytest` 跑測試。

- [ ] **Step 1: 建立 pyproject.toml**

```toml
[project]
name = "copycat"
version = "0.1.0"
description = "分點行為指紋辨識 — 評分引擎 + 歷史 replay(回測基建)"
requires-python = ">=3.13"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5", "pyright>=1.1"]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.pyright]
typeCheckingMode = "basic"
include = ["copycat", "tests"]
exclude = ["**/__pycache__", ".venv", "spikes", "docs"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]   # tests 跨檔共用 fixture helper(tests.data.test_import_neigui)需要

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["copycat*"]
```

- [ ] **Step 2: 建立 .gitignore**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
data/
out/
spikes/TCPY/
spikes/catalog_dump/
spikes/.ruff_cache/
.claude/
```

(`spikes/TCPY/` 是官方 sample 的嵌套 git clone,不納版控;`spikes/*.py` 探測腳本保留追蹤。)

- [ ] **Step 3: 建立 package 與 sanity test**

`copycat/__init__.py`:

```python
"""copycat — 分點行為指紋辨識:評分引擎 + 歷史 replay."""
from __future__ import annotations
```

`tests/test_sanity.py`:

```python
from __future__ import annotations

import copycat


def test_package_importable() -> None:
    assert copycat.__doc__ is not None
```

- [ ] **Step 4: 建 venv 並安裝**

Run(PowerShell,工作目錄 `C:\side-project\copycat`):
```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```
Expected: 安裝成功,無 error。(注意:`py` launcher 預設 3.14,必須明確 `-3.13`。)

- [ ] **Step 5: 跑工具鏈 smoke**

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check copycat tests
.venv\Scripts\python -m pyright
```
Expected: pytest `1 passed`;ruff 無 error;pyright `0 errors`。

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml .gitignore copycat/__init__.py tests/test_sanity.py
git commit -m "chore(replay): 專案 scaffold — pyproject + venv 工具鏈(pytest/ruff/pyright)"
```

---

### Task 2: 資料模型與時間轉換(models.py)

**Files:**
- Create: `copycat/data/__init__.py`(空 module,僅 future import + docstring)
- Create: `copycat/data/models.py`
- Test: `tests/data/test_models.py`

**Interfaces:**
- Produces:
  - `Bar1K`(frozen dataclass):`m: int`(台北分鐘索引 09:01=0…13:30=269)、`open/high/low/close: float`、`volume/up_volume/down_volume/unch_volume: float`(張)
  - `taipei_min(time_utc: str) -> int`:UTC HHMMSS(無前導零)→ 分鐘索引
  - `fmt_min(m: int) -> str`:分鐘索引 → `"09:01"` 格式
  - `parse_raw_bar(raw: dict[str, str]) -> Bar1K`:neigui 原始 bar dict → Bar1K(欄位缺漏/非數字 raise `ValueError`)

- [ ] **Step 1: Write the failing test**

`tests/data/test_models.py`:

```python
from __future__ import annotations

import pytest

from copycat.data.models import Bar1K, fmt_min, parse_raw_bar, taipei_min


def test_taipei_min_first_bar() -> None:
    # UTC 01:01 = 台北 09:01 = 索引 0
    assert taipei_min("10100") == 0


def test_taipei_min_last_bar() -> None:
    # UTC 05:30 = 台北 13:30 收盤競價根 = 索引 269
    assert taipei_min("53000") == 269


def test_taipei_min_mid() -> None:
    # UTC 02:00 = 台北 10:00 = 索引 59
    assert taipei_min("20000") == 59


def test_fmt_min_roundtrip() -> None:
    assert fmt_min(0) == "09:01"
    assert fmt_min(59) == "10:00"
    assert fmt_min(269) == "13:30"


def test_parse_raw_bar() -> None:
    raw = {
        "Time": "10100", "Open": "30.05", "High": "30.7", "Low": "30",
        "Close": "30.6", "Volume": "1936", "UpTick": "101", "UpVolume": "1792",
        "DownTick": "49", "DownVolume": "144", "UnchVolume": "0",
    }
    bar = parse_raw_bar(raw)
    assert bar == Bar1K(m=0, open=30.05, high=30.7, low=30.0, close=30.6,
                        volume=1936.0, up_volume=1792.0, down_volume=144.0,
                        unch_volume=0.0)


def test_parse_raw_bar_empty_volume_is_zero() -> None:
    raw = {"Time": "10100", "Open": "30", "High": "30", "Low": "30",
           "Close": "30", "Volume": "", "UpTick": "0", "UpVolume": "",
           "DownTick": "0", "DownVolume": "", "UnchVolume": ""}
    bar = parse_raw_bar(raw)
    assert bar.volume == 0.0 and bar.up_volume == 0.0


def test_parse_raw_bar_missing_field_raises() -> None:
    with pytest.raises(ValueError):
        parse_raw_bar({"Time": "10100"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/data/test_models.py -q`
Expected: FAIL(`ModuleNotFoundError: copycat.data.models`)

- [ ] **Step 3: Write minimal implementation**

`copycat/data/__init__.py`:

```python
"""資料層:標準模型、儲存、匯入."""
from __future__ import annotations
```

`copycat/data/models.py`:

```python
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
    """neigui 原始 bar dict(全字串)→ Bar1K。欄位缺漏 raise KeyError→ValueError."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/data/test_models.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/data tests/data
git commit -m "feat(replay): Bar1K 標準模型與台北分鐘索引轉換"
```

---

### Task 3: 標準化 1K 儲存(store.py)

**Files:**
- Create: `copycat/data/store.py`
- Test: `tests/data/test_store.py`

**Interfaces:**
- Consumes: `Bar1K`(Task 2)
- Produces:
  - `bars_path(data_dir: Path, stock_id: str, date: str) -> Path` → `data_dir/1k/{stock_id}/{date}.json`
  - `write_bars(data_dir: Path, stock_id: str, date: str, bars: list[Bar1K]) -> None`(atomic:寫 `.tmp` 再 `os.replace`;bars 必須已按 m 遞增,否則 raise `ValueError`)
  - `read_bars(data_dir: Path, stock_id: str, date: str) -> list[Bar1K] | None`(檔案不存在回 None)
  - 檔案格式:`{"stock_id","date","bars":[[m,o,h,l,c,v,uv,dv,unch],…]}`(compact array)

- [ ] **Step 1: Write the failing test**

`tests/data/test_store.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from copycat.data.models import Bar1K
from copycat.data.store import bars_path, read_bars, write_bars


def _bar(m: int, px: float = 10.0, v: float = 100.0) -> Bar1K:
    return Bar1K(m=m, open=px, high=px, low=px, close=px,
                 volume=v, up_volume=v, down_volume=0.0, unch_volume=0.0)


def test_roundtrip(tmp_path: Path) -> None:
    bars = [_bar(0), _bar(1, px=10.5)]
    write_bars(tmp_path, "2330", "2026-07-03", bars)
    assert read_bars(tmp_path, "2330", "2026-07-03") == bars


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_bars(tmp_path, "9999", "2026-01-01") is None


def test_write_rejects_unsorted(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_bars(tmp_path, "2330", "2026-07-03", [_bar(5), _bar(3)])


def test_path_layout(tmp_path: Path) -> None:
    assert bars_path(tmp_path, "2330", "2026-07-03") == tmp_path / "1k" / "2330" / "2026-07-03.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/data/test_store.py -q`
Expected: FAIL(`ModuleNotFoundError: copycat.data.store`)

- [ ] **Step 3: Write minimal implementation**

`copycat/data/store.py`:

```python
"""標準化 1K 的本機 JSON 儲存(atomic write,無 DB — 沿專案慣例)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from copycat.data.models import Bar1K


def bars_path(data_dir: Path, stock_id: str, date: str) -> Path:
    return data_dir / "1k" / stock_id / f"{date}.json"


def write_bars(data_dir: Path, stock_id: str, date: str, bars: list[Bar1K]) -> None:
    if any(b2.m <= b1.m for b1, b2 in zip(bars, bars[1:])):
        raise ValueError(f"bars 未按分鐘索引遞增: {stock_id} {date}")
    payload = {
        "stock_id": stock_id,
        "date": date,
        "bars": [[b.m, b.open, b.high, b.low, b.close,
                  b.volume, b.up_volume, b.down_volume, b.unch_volume] for b in bars],
    }
    path = bars_path(data_dir, stock_id, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def read_bars(data_dir: Path, stock_id: str, date: str) -> list[Bar1K] | None:
    path = bars_path(data_dir, stock_id, date)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Bar1K(m=int(r[0]), open=r[1], high=r[2], low=r[3], close=r[4],
                  volume=r[5], up_volume=r[6], down_volume=r[7], unch_volume=r[8])
            for r in payload["bars"]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/data/test_store.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/data/store.py tests/data/test_store.py
git commit -m "feat(replay): 1K 標準格式 atomic JSON 儲存"
```

---

### Task 4: 日線 loader(daily.py)

**Files:**
- Create: `copycat/data/daily.py`
- Test: `tests/data/test_daily.py`

**Interfaces:**
- Consumes: 標準化日線 CSV `data_dir/daily/prices.csv`(欄位 `stock_id,date,open,high,low,close,volume_lots`;volume_lots = 張)與 `data_dir/events/limitup_all.csv`(欄位 `stock_id,date,close`)
- Produces: `DailyIndex` class:
  - `DailyIndex.load(data_dir: Path) -> DailyIndex`
  - `.open_of(stock_id, date) -> float | None`
  - `.one_price(stock_id, date) -> bool | None`(high == low)
  - `.adv20(stock_id, date) -> float | None`(**含 date 當日**往前最多 20 個交易日 volume_lots 簡單平均;不足 20 日用實際天數;該股無資料回 None)
  - `.next_date(stock_id, date) -> str | None`(該股下一個有日線的交易日)
  - `.is_limitup(stock_id, date) -> bool`(在 limitup_all 集合中)
  - `.board_streak(stock_id, date) -> int`(含 date 往前連續 limitup 天數,以該股日線日序回溯;date 本身非 limitup 回 0)

- [ ] **Step 1: Write the failing test**

`tests/data/test_daily.py`:

```python
from __future__ import annotations

import csv
from pathlib import Path

from copycat.data.daily import DailyIndex


def _write_fixture(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    events = tmp_path / "events"
    daily.mkdir()
    events.mkdir()
    rows = [
        # 3 個交易日,量 100/200/300 張
        {"stock_id": "1101", "date": "2026-07-01", "open": "10.0", "high": "10.5",
         "low": "9.9", "close": "10.2", "volume_lots": "100"},
        {"stock_id": "1101", "date": "2026-07-02", "open": "10.2", "high": "11.2",
         "low": "11.2", "close": "11.2", "volume_lots": "200"},
        {"stock_id": "1101", "date": "2026-07-03", "open": "11.5", "high": "12.3",
         "low": "11.4", "close": "12.3", "volume_lots": "300"},
    ]
    with (daily / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (events / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
        # 07-02 與 07-03 連續漲停
        w.writerow({"stock_id": "1101", "date": "2026-07-02", "close": "11.2"})
        w.writerow({"stock_id": "1101", "date": "2026-07-03", "close": "12.3"})


def test_open_and_one_price(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.open_of("1101", "2026-07-03") == 11.5
    assert idx.one_price("1101", "2026-07-02") is True   # high == low(一價到底 proxy)
    assert idx.one_price("1101", "2026-07-03") is False
    assert idx.open_of("9999", "2026-07-03") is None


def test_adv20_partial_window(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    # 含當日往前:07-02 的 adv = (100+200)/2
    assert idx.adv20("1101", "2026-07-02") == 150.0


def test_next_date(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.next_date("1101", "2026-07-02") == "2026-07-03"
    assert idx.next_date("1101", "2026-07-03") is None


def test_limitup_and_board_streak(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.is_limitup("1101", "2026-07-02") is True
    assert idx.is_limitup("1101", "2026-07-01") is False
    assert idx.board_streak("1101", "2026-07-03") == 2  # 07-02、07-03 連兩板
    assert idx.board_streak("1101", "2026-07-02") == 1
    assert idx.board_streak("1101", "2026-07-01") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/data/test_daily.py -q`
Expected: FAIL(`ModuleNotFoundError: copycat.data.daily`)

- [ ] **Step 3: Write minimal implementation**

`copycat/data/daily.py`:

```python
"""日線索引:adv20 / 一價到底 / 下一交易日 / 漲停集合 / 連板數."""
from __future__ import annotations

import csv
import logging
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _DayRow:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume_lots: float


class DailyIndex:
    def __init__(self, rows: dict[str, list[_DayRow]], limitup: set[tuple[str, str]]) -> None:
        self._rows = rows          # stock_id → 按 date 排序的日線
        self._limitup = limitup    # {(stock_id, date)}

    @classmethod
    def load(cls, data_dir: Path) -> DailyIndex:
        rows: dict[str, list[_DayRow]] = {}
        with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.setdefault(r["stock_id"], []).append(_DayRow(
                    date=r["date"], open=float(r["open"]), high=float(r["high"]),
                    low=float(r["low"]), close=float(r["close"]),
                    volume_lots=float(r["volume_lots"]),
                ))
        for lst in rows.values():
            lst.sort(key=lambda x: x.date)
        limitup: set[tuple[str, str]] = set()
        with (data_dir / "events" / "limitup_all.csv").open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                limitup.add((r["stock_id"], r["date"]))
        logger.info("DailyIndex: %d stocks, %d limitup events", len(rows), len(limitup))
        return cls(rows, limitup)

    def _find(self, stock_id: str, date: str) -> tuple[list[_DayRow], int] | None:
        lst = self._rows.get(stock_id)
        if not lst:
            return None
        i = bisect_left([r.date for r in lst], date)
        if i >= len(lst) or lst[i].date != date:
            return None
        return lst, i

    def open_of(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        return hit[0][hit[1]].open if hit else None

    def one_price(self, stock_id: str, date: str) -> bool | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        row = hit[0][hit[1]]
        return row.high == row.low

    def adv20(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        window = lst[max(0, i - 19): i + 1]
        return sum(r.volume_lots for r in window) / len(window)

    def next_date(self, stock_id: str, date: str) -> str | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        return lst[i + 1].date if i + 1 < len(lst) else None

    def is_limitup(self, stock_id: str, date: str) -> bool:
        return (stock_id, date) in self._limitup

    def board_streak(self, stock_id: str, date: str) -> int:
        hit = self._find(stock_id, date)
        if not hit or not self.is_limitup(stock_id, date):
            return 0
        lst, i = hit
        streak = 0
        while i >= 0 and self.is_limitup(stock_id, lst[i].date):
            streak += 1
            i -= 1
        return streak
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/data/test_daily.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/data/daily.py tests/data/test_daily.py
git commit -m "feat(replay): 日線索引 — adv20/一價到底/下一交易日/連板數"
```

---

### Task 5: Watchlist(可替換分點集合)

**Files:**
- Create: `copycat/watchlist.py`
- Create: `watchlists/four_tigers.json`
- Create: `watchlists/five_tigers.json`
- Test: `tests/test_watchlist.py`

**Interfaces:**
- Produces:
  - `Watchlist`(frozen dataclass):`name: str`、`broker_ids: frozenset[str]`
  - `load_watchlist(path: Path) -> Watchlist`
  - JSON schema:`{"name": "...", "members": [{"broker_id": "9227", "name": "凱基城中", "role": "leader"}, …]}`(role 僅供報表註記,引擎不用)
- **broker_id 大小寫敏感**(779Z 安和 ≠ 779z 博愛,evidence 已踩過)— 載入時不得 normalize。

- [ ] **Step 1: Write the failing test**

`tests/test_watchlist.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from copycat.watchlist import Watchlist, load_watchlist


def test_load_watchlist(tmp_path: Path) -> None:
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({
        "name": "test",
        "members": [
            {"broker_id": "9227", "name": "凱基城中", "role": "leader"},
            {"broker_id": "779Z", "name": "國票安和", "role": "follower"},
        ],
    }), encoding="utf-8")
    wl = load_watchlist(p)
    assert wl == Watchlist(name="test", broker_ids=frozenset({"9227", "779Z"}))


def test_broker_id_case_sensitive(tmp_path: Path) -> None:
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"name": "t", "members": [{"broker_id": "779Z", "name": "安和"}]}),
                 encoding="utf-8")
    wl = load_watchlist(p)
    assert "779Z" in wl.broker_ids and "779z" not in wl.broker_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_watchlist.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation + 預設 watchlist 檔**

`copycat/watchlist.py`:

```python
"""可替換分點集合 — 只影響事件標記與報表分組,不進評分邏輯(spec §2)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Watchlist:
    name: str
    broker_ids: frozenset[str]  # 大小寫敏感(779Z ≠ 779z)


def load_watchlist(path: Path) -> Watchlist:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Watchlist(
        name=payload["name"],
        broker_ids=frozenset(m["broker_id"] for m in payload["members"]),
    )
```

`watchlists/four_tigers.json`:

```json
{
  "name": "four_tigers",
  "members": [
    {"broker_id": "9227", "name": "凱基城中", "role": "leader"},
    {"broker_id": "5854", "name": "統一城中", "role": "follower"},
    {"broker_id": "779c", "name": "國票敦北", "role": "follower"},
    {"broker_id": "779Z", "name": "國票安和", "role": "follower"}
  ]
}
```

`watchlists/five_tigers.json`:

```json
{
  "name": "five_tigers",
  "members": [
    {"broker_id": "9227", "name": "凱基城中", "role": "leader"},
    {"broker_id": "5854", "name": "統一城中", "role": "follower"},
    {"broker_id": "779c", "name": "國票敦北", "role": "follower"},
    {"broker_id": "779Z", "name": "國票安和", "role": "follower"},
    {"broker_id": "9600", "name": "富邦總部(訊號稀釋,輔助)", "role": "auxiliary"}
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_watchlist.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/watchlist.py watchlists tests/test_watchlist.py
git commit -m "feat(replay): 可替換 watchlist(四虎/五虎預設檔)"
```

---

### Task 6: 種子資料匯入器 + `import-neigui` CLI

**Files:**
- Create: `copycat/data/import_neigui.py`
- Create: `copycat/cli.py`
- Create: `copycat/__main__.py`
- Test: `tests/data/test_import_neigui.py`

**Interfaces:**
- Consumes: `parse_raw_bar` / `write_bars` / `DailyIndex`(Task 2-4)
- Produces:
  - `run_import(src: Path, events_csv: Path, data_dir: Path) -> dict[str, object]`(回傳 manifest dict,同步寫入 `data_dir/manifest.json`)
  - 產物:`data/1k/…`(k1_bars.jsonl + k1_control.jsonl 全部 stock-day)、`data/daily/prices.csv`(volume→張)、`data/events/limitup_all.csv`、`data/events/events.csv`
  - `data/events/events.csv` 欄位:`stock_id,date,stock_name,limitup_close,t1_date,source,broker_ids`
    - `source`:`tiger_csv`(來自 evidence 五虎 CSV,事件級去重)或 `control`(all_limitup 扣除虎事件 keys)
    - `broker_ids`:該事件的虎 broker_id 以 `|` join(control 為空);cohort 由 replay 時的 watchlist 決定,**不在匯入時定案**
    - `t1_date`:一律由 `DailyIndex.next_date` 推導;虎 CSV 的 t1_date 不一致時 log warning(以推導值為準)
  - manifest keys:`k1_days`(int)、`skipped_bars`(int)、`tiger_events`、`control_events`、`missing_t_1k`(list[str],`"stock_id,date"`)、`missing_t1_1k`(list[str])
- 種子檔案缺失(如 src 路徑錯)直接 raise `FileNotFoundError`,fail loud。

- [ ] **Step 1: Write the failing test**

`tests/data/test_import_neigui.py`:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path

from copycat.data.import_neigui import run_import
from copycat.data.store import read_bars


def _bar_raw(time: str, px: str, vol: str) -> dict[str, str]:
    return {"Time": time, "Open": px, "High": px, "Low": px, "Close": px,
            "Volume": vol, "UpTick": "1", "UpVolume": vol, "DownTick": "0",
            "DownVolume": "0", "UnchVolume": "0"}


def _write_src(src: Path) -> None:
    src.mkdir()
    # 1104:T 日 2025-09-10(虎事件)+ T+1 2025-09-11;2001:control 事件
    recs = [
        {"stock_id": "1104", "date": "2025-09-10",
         "bars": [_bar_raw("10100", "32", "100"), _bar_raw("10200", "32", "50")]},
        {"stock_id": "1104", "date": "2025-09-11",
         "bars": [_bar_raw("10100", "33", "80")]},
    ]
    with (src / "k1_bars.jsonl").open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    with (src / "k1_control.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"stock_id": "2001", "date": "2025-09-10",
                             "bars": [_bar_raw("10100", "50", "10")]}) + "\n")
    prices = [
        {"stock_id": "1104", "date": "2025-09-10", "open": "29.5", "high": "32",
         "low": "29.5", "close": "32", "spread": "2.9", "volume": "150000"},
        {"stock_id": "1104", "date": "2025-09-11", "open": "33.6", "high": "34",
         "low": "31", "close": "31.5", "spread": "-0.5", "volume": "90000"},
        {"stock_id": "2001", "date": "2025-09-10", "open": "48", "high": "50",
         "low": "48", "close": "50", "spread": "4.5", "volume": "20000"},
        {"stock_id": "2001", "date": "2025-09-11", "open": "51", "high": "52",
         "low": "50", "close": "50.5", "spread": "0.5", "volume": "30000"},
    ]
    with (src / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prices[0]))
        w.writeheader()
        w.writerows(prices)
    with (src / "all_limitup_events.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close", "spread", "pct", "volume"])
        w.writeheader()
        w.writerow({"stock_id": "1104", "date": "2025-09-10", "close": "32.00",
                    "spread": "2.90", "pct": "0.0997", "volume": "150000"})
        w.writerow({"stock_id": "2001", "date": "2025-09-10", "close": "50.00",
                    "spread": "4.50", "pct": "0.0991", "volume": "20000"})


def _write_events_csv(path: Path) -> None:
    fields = ["date", "stock_id", "stock_name", "tiger", "broker_id", "buy_lots",
              "limitup_close", "t1_date", "gap", "again"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        # 同事件兩虎 → 應去重為一個事件
        w.writerow({"date": "2025-09-10", "stock_id": "1104", "stock_name": "環泥",
                    "tiger": "國票敦北", "broker_id": "779c", "buy_lots": "100",
                    "limitup_close": "32.0", "t1_date": "2025-09-11",
                    "gap": "0.05", "again": "False"})
        w.writerow({"date": "2025-09-10", "stock_id": "1104", "stock_name": "環泥",
                    "tiger": "國票安和", "broker_id": "779Z", "buy_lots": "50",
                    "limitup_close": "32.0", "t1_date": "2025-09-11",
                    "gap": "0.05", "again": "False"})


def test_run_import(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write_src(src)
    ev_csv = tmp_path / "tigers.csv"
    _write_events_csv(ev_csv)
    data = tmp_path / "data"

    manifest = run_import(src, ev_csv, data)

    # 1K 標準化落地
    bars = read_bars(data, "1104", "2025-09-10")
    assert bars is not None and len(bars) == 2 and bars[0].m == 0
    # 日線 volume 轉張
    with (data / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["volume_lots"] == "150.0"
    # 事件:1 虎事件(去重)+ 1 control
    with (data / "events" / "events.csv").open("r", encoding="utf-8") as fh:
        events = list(csv.DictReader(fh))
    tiger = [e for e in events if e["source"] == "tiger_csv"]
    ctrl = [e for e in events if e["source"] == "control"]
    assert len(tiger) == 1 and tiger[0]["broker_ids"] == "779Z|779c"
    assert tiger[0]["t1_date"] == "2025-09-11"
    assert len(ctrl) == 1 and ctrl[0]["stock_id"] == "2001" and ctrl[0]["broker_ids"] == ""
    # manifest:control 的 T+1 1K 缺(2001/2025-09-11 沒有 1K)
    assert manifest["k1_days"] == 3
    assert manifest["tiger_events"] == 1 and manifest["control_events"] == 1
    assert "2001,2025-09-11" in manifest["missing_t1_1k"]
    assert (data / "manifest.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/data/test_import_neigui.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/data/import_neigui.py`:

```python
"""neigui five-tigers 種子資料 → copycat 標準格式(一次性匯入).

來源唯讀;TC4 原始格式陷阱(UTC 時刻、無前導零、字串數值)全在這層清洗,
引擎只看標準化資料(spec §3)。
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from copycat.data.daily import DailyIndex
from copycat.data.models import parse_raw_bar
from copycat.data.store import read_bars, write_bars

logger = logging.getLogger(__name__)


def _import_k1(src_file: Path, data_dir: Path) -> tuple[int, int]:
    """回傳 (匯入 stock-day 數, 略過的壞 bar 數)。壞 bar = 欄位缺漏/非數字."""
    days = 0
    skipped = 0
    with src_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            bars = []
            for raw in rec["bars"]:
                try:
                    bars.append(parse_raw_bar(raw))
                except ValueError:
                    skipped += 1
            bars.sort(key=lambda b: b.m)
            write_bars(data_dir, rec["stock_id"], rec["date"], bars)
            days += 1
    return days, skipped


def _import_daily(src: Path, data_dir: Path) -> None:
    out = data_dir / "daily" / "prices.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with (src / "prices.csv").open("r", encoding="utf-8") as fin, \
            out.open("w", encoding="utf-8", newline="") as fout:
        w = csv.DictWriter(fout, fieldnames=[
            "stock_id", "date", "open", "high", "low", "close", "volume_lots"])
        w.writeheader()
        for r in csv.DictReader(fin):
            w.writerow({
                "stock_id": r["stock_id"], "date": r["date"], "open": r["open"],
                "high": r["high"], "low": r["low"], "close": r["close"],
                "volume_lots": str(float(r["volume"]) / 1000.0),
            })


def _import_limitup(src: Path, data_dir: Path) -> list[dict[str, str]]:
    out = data_dir / "events" / "limitup_all.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with (src / "all_limitup_events.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({"stock_id": r["stock_id"], "date": r["date"], "close": r["close"]})
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
        w.writerows(rows)
    return rows


def _build_events(events_csv: Path, limitup: list[dict[str, str]],
                  daily: DailyIndex, data_dir: Path) -> tuple[int, int]:
    tiger: dict[tuple[str, str], dict[str, str]] = {}
    with events_csv.open("r", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            key = (r["stock_id"], r["date"])
            ev = tiger.setdefault(key, {
                "stock_id": r["stock_id"], "date": r["date"],
                "stock_name": r["stock_name"], "limitup_close": r["limitup_close"],
                "source": "tiger_csv", "brokers": set(),  # type: ignore[dict-item]
            })
            ev["brokers"].add(r["broker_id"])  # type: ignore[union-attr]
            t1 = daily.next_date(r["stock_id"], r["date"])
            if r.get("t1_date") and t1 and r["t1_date"] != t1:
                logger.warning("t1_date 不一致 %s %s: csv=%s 推導=%s(以推導為準)",
                               r["stock_id"], r["date"], r["t1_date"], t1)

    out_rows: list[dict[str, str]] = []
    for (sid, dt), ev in sorted(tiger.items()):
        out_rows.append({
            "stock_id": sid, "date": dt, "stock_name": ev["stock_name"],
            "limitup_close": ev["limitup_close"],
            "t1_date": daily.next_date(sid, dt) or "",
            "source": "tiger_csv",
            "broker_ids": "|".join(sorted(ev["brokers"])),  # type: ignore[arg-type]
        })
    n_tiger = len(out_rows)
    tiger_keys = set(tiger)
    for r in limitup:
        key = (r["stock_id"], r["date"])
        if key in tiger_keys:
            continue
        out_rows.append({
            "stock_id": r["stock_id"], "date": r["date"], "stock_name": "",
            "limitup_close": r["close"],
            "t1_date": daily.next_date(r["stock_id"], r["date"]) or "",
            "source": "control", "broker_ids": "",
        })
    out = data_dir / "events" / "events.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "stock_id", "date", "stock_name", "limitup_close", "t1_date",
            "source", "broker_ids"])
        w.writeheader()
        w.writerows(out_rows)
    return n_tiger, len(out_rows) - n_tiger


def run_import(src: Path, events_csv: Path, data_dir: Path) -> dict[str, object]:
    for required in ("k1_bars.jsonl", "prices.csv", "all_limitup_events.csv"):
        if not (src / required).exists():
            raise FileNotFoundError(src / required)
    if not events_csv.exists():
        raise FileNotFoundError(events_csv)

    days, skipped = _import_k1(src / "k1_bars.jsonl", data_dir)
    ctrl_file = src / "k1_control.jsonl"
    if ctrl_file.exists():
        d2, s2 = _import_k1(ctrl_file, data_dir)
        days, skipped = days + d2, skipped + s2
    _import_daily(src, data_dir)
    limitup = _import_limitup(src, data_dir)
    daily = DailyIndex.load(data_dir)
    n_tiger, n_ctrl = _build_events(events_csv, limitup, daily, data_dir)

    missing_t: list[str] = []
    missing_t1: list[str] = []
    with (data_dir / "events" / "events.csv").open("r", encoding="utf-8") as fh:
        for ev in csv.DictReader(fh):
            if read_bars(data_dir, ev["stock_id"], ev["date"]) is None:
                missing_t.append(f"{ev['stock_id']},{ev['date']}")
            if ev["t1_date"] and read_bars(data_dir, ev["stock_id"], ev["t1_date"]) is None:
                missing_t1.append(f"{ev['stock_id']},{ev['t1_date']}")

    manifest: dict[str, object] = {
        "k1_days": days, "skipped_bars": skipped,
        "tiger_events": n_tiger, "control_events": n_ctrl,
        "missing_t_1k": missing_t, "missing_t1_1k": missing_t1,
    }
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("import 完成: %s", {k: v for k, v in manifest.items()
                                    if not isinstance(v, list)})
    return manifest
```

`copycat/cli.py`:

```python
"""CLI 入口:import-neigui / replay / validate / compare 逐 task 接上."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from copycat.data.import_neigui import run_import

logger = logging.getLogger(__name__)

_DEFAULT_EVENTS_CSV = Path("docs/evidence/five_tigers_events_2025-06-30_2026-06-26.csv")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="copycat")
    sub = parser.add_subparsers(dest="command", required=True)

    p_imp = sub.add_parser("import-neigui", help="匯入 neigui five-tigers 種子資料")
    p_imp.add_argument("--src", type=Path, required=True)
    p_imp.add_argument("--events-csv", type=Path, default=_DEFAULT_EVENTS_CSV)
    p_imp.add_argument("--data-dir", type=Path, default=Path("data"))

    args = parser.parse_args(argv)
    if args.command == "import-neigui":
        manifest = run_import(args.src, args.events_csv, args.data_dir)
        sys.stdout.write(
            f"匯入完成:1K {manifest['k1_days']} stock-day、"
            f"虎事件 {manifest['tiger_events']}、對照 {manifest['control_events']}、"
            f"缺 T 日 1K {len(manifest['missing_t_1k'])} 筆、"  # type: ignore[arg-type]
            f"缺 T+1 1K {len(manifest['missing_t1_1k'])} 筆\n")  # type: ignore[arg-type]
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`copycat/__main__.py`:

```python
from __future__ import annotations

from copycat.cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/data/test_import_neigui.py -q`
Expected: `1 passed`

- [ ] **Step 5: 真實匯入(全量,一次性)**

Run:
```powershell
.venv\Scripts\python -m copycat import-neigui --src C:\side-project\neigui\backend\data\research\five-tigers
```
Expected: 匯入完成訊息;`k1_days` ≈ 7830(2007 虎 + 5823 對照)、虎事件 ≈ 1029、對照 ≈ 2482、缺漏筆數為小量(對照組 T+1 覆蓋不全屬預期,詳列在 manifest)。把實際數字記下來(Task 14 SC-1 用)。

- [ ] **Step 6: Commit**

```powershell
git add copycat/data/import_neigui.py copycat/cli.py copycat/__main__.py tests/data/test_import_neigui.py
git commit -m "feat(replay): neigui 種子資料匯入器 + import-neigui CLI(1K/日線/事件/manifest)"
```

---

### Task 7: StrategyConfig(版本化策略參數)

**Files:**
- Create: `copycat/strategy_config.py`
- Create: `configs/strategy-v1.json`
- Test: `tests/test_strategy_config.py`

**Interfaces:**
- Produces:
  - `StrategyConfig`(frozen dataclass,含下列全部欄位與預設值 = strategy.md 當前假設)
  - `StrategyConfig.default() -> StrategyConfig`
  - `load_config(path: Path) -> StrategyConfig`(JSON 淺覆寫預設值;未知 key raise `ValueError` — 防打錯參數名靜默沒生效)

- [ ] **Step 1: Write the failing test**

`tests/test_strategy_config.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.strategy_config import StrategyConfig, load_config


def test_default_values() -> None:
    cfg = StrategyConfig.default()
    assert cfg.violent_pull_min_gain == 0.06
    assert cfg.queue_strong_min == 0.40
    assert cfg.t1_limit_mult == 1.095
    assert cfg.gap_buckets == (0.0, 0.01, 0.03, 0.07, 0.095)


def test_load_override(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"violent_pull_min_gain": 0.05}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.violent_pull_min_gain == 0.05
    assert cfg.queue_strong_min == 0.40  # 未覆寫者保留預設


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_strategy_config.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/strategy_config.py`:

```python
"""版本化策略參數 — 全部門檻在此,引擎 code 不出現 magic number(spec §2).

預設值 = docs/strategy.md 當前假設;調策略 = 改 JSON 重跑,不動 code。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    # --- 通用 ---
    limit_eps: float = 1e-6                 # 漲停價比較容差(浮點)
    # --- Phase 2 鎖板品質 ---
    lock_time_buckets: tuple[int, ...] = (4, 59, 179, 239)   # 分鐘索引切點(09:05/10:00/12:00/13:00)
    early_lock_max_idx: int = 59            # tier: 早鎖 = 首鎖 < 10:00
    tail_lock_min_idx: int = 239            # 尾盤鎖 = 13:00+
    violent_pull_window: int = 10           # 暴力拉板觀察窗(bar 數)
    violent_pull_min_gain: float = 0.06     # 窗內推升 ≥6% = 暴力拉板
    queue_strong_min: float = 0.40          # 鎖後排隊消耗 ≥40% 日量 = 真需求
    queue_dead_max: float = 0.15            # <15% = 死鎖無量
    open_count_weak: int = 6                # 打開 ≥6 次 → weak(續鎖 0%)
    open_count_strong_max: int = 1          # strong 允許的最大打開次數
    # --- Phase 3 T+1 ---
    t1_limit_mult: float = 1.095            # T+1 觸停/漲停開閾值 = 前日漲停 ×1.095
    gap_buckets: tuple[float, ...] = (0.0, 0.01, 0.03, 0.07, 0.095)
    auction_buckets: tuple[float, ...] = (0.03, 0.08)   # 競價量占比三桶切點
    inner_window: int = 15                  # 內盤比觀察窗(分鐘)
    pull_high_min: float = 0.02             # t1 路徑分類:拉高出貨的最小拉幅
    pull_high_max_idx: int = 90             # 拉高出貨的高點須在前 90 分鐘內
    adv_window: int = 20                    # 均量窗(DailyIndex.adv20 已固定 20,此值供文件化)

    @classmethod
    def default(cls) -> StrategyConfig:
        return cls()


def load_config(path: Path) -> StrategyConfig:
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(StrategyConfig)}
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"未知策略參數: {sorted(unknown)}")
    for key in ("lock_time_buckets", "gap_buckets", "auction_buckets"):
        if key in payload:
            payload[key] = tuple(payload[key])  # type: ignore[arg-type]
    return StrategyConfig(**payload)  # type: ignore[arg-type]
```

`configs/strategy-v1.json`(空覆寫 = 純預設,當作 baseline 版本的具名檔):

```json
{}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_strategy_config.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/strategy_config.py configs tests/test_strategy_config.py
git commit -m "feat(replay): StrategyConfig — 策略門檻版本化(baseline = strategy.md 假設)"
```

---

### Task 8: 鎖板品質引擎(LockTracker + tier)

**Files:**
- Create: `copycat/engine/__init__.py`
- Create: `copycat/engine/lock_quality.py`
- Test: `tests/engine/test_lock_quality.py`

**Interfaces:**
- Consumes: `Bar1K`、`fmt_min`(Task 2)、`StrategyConfig`(Task 7)
- Produces:
  - `LockQualitySignals`(frozen dataclass):`first_touch_idx: int`、`first_touch_time: str`、`lock_idx: int`、`lock_time: str`、`lock_time_bucket: str`、`n_reopens: int`、`violent_pull: bool`、`prelock10_gain: float | None`、`vol_after_lock_share: float`、`queue_bucket: str`、`day_volume: float`、`tier: str`
  - `LockTracker` class:
    - `__init__(self, config: StrategyConfig, limit: float)`
    - `feed(self, bar: Bar1K) -> None`(m 不遞增 raise `ValueError`)
    - property `first_touch_idx: int | None`、`n_reopens: int`(盤中即時可查,單調不回改)
    - `current_lock_start(self) -> int | None`(當前連續 at_limit 段起點;盤中 provisional)
    - `finalize(self) -> LockQualitySignals | None`(收盤後定稿;全日未觸停或收盤不在漲停 → None,與研究一致)
  - bucket 標籤字串(報表/golden 對照用,固定):鎖板時間 `"<09:05" / "09:05-10:00" / "10:00-12:00" / "12:00-13:00" / "13:00+"`;排隊 `">=40%" / "15-40%" / "<15%"`;tier `"strong" / "neutral" / "weak"`
- **鎖死定義與 neigui `extract_features.py` 一致**:at_limit = close ≥ limit−ε;final lock = 最後一段連續 at_limit 延伸到收盤的起點;n_reopens = first_touch 後「離開 at_limit」段數。
- **violent_pull(1K 近似)**:取 m ∈ [lock_m − 10, lock_m) 的 bars,px0 = 第一根的 open,gain = limit/px0 − 1;gain ≥ 0.06 → True。窗內無 bar(開盤即鎖)→ gain None、False。

- [ ] **Step 1: Write the failing test**

`tests/engine/test_lock_quality.py`:

```python
from __future__ import annotations

import pytest

from copycat.data.models import Bar1K
from copycat.engine.lock_quality import LockTracker
from copycat.strategy_config import StrategyConfig

LIMIT = 11.0
CFG = StrategyConfig.default()


def bar(m: int, close: float, *, high: float | None = None, open_: float | None = None,
        v: float = 100.0) -> Bar1K:
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close)
    return Bar1K(m=m, open=o, high=h, low=min(o, close), close=close,
                 volume=v, up_volume=v, down_volume=0.0, unch_volume=0.0)


def run(bars: list[Bar1K]) -> LockTracker:
    t = LockTracker(CFG, LIMIT)
    for b in bars:
        t.feed(b)
    return t


def test_open_lock_strong() -> None:
    # 開盤第一根就鎖到收盤;鎖後量 500/600 ≥ 40% → strong
    bars = [bar(0, LIMIT, v=100.0)] + [bar(m, LIMIT, v=100.0) for m in range(1, 6)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.lock_idx == 0 and sig.lock_time_bucket == "<09:05"
    assert sig.n_reopens == 0
    assert sig.violent_pull is False and sig.prelock10_gain is None  # 窗內無 bar
    assert sig.vol_after_lock_share == 1.0 and sig.queue_bucket == ">=40%"
    assert sig.tier == "strong"


def test_reopen_then_relock() -> None:
    # 鎖(m2)→打開(m3)→回鎖(m4)到收盤:final lock = m4、n_reopens = 1
    bars = [bar(0, 10.5), bar(1, 10.8), bar(2, LIMIT), bar(3, 10.9, high=LIMIT),
            bar(4, LIMIT), bar(5, LIMIT)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.first_touch_idx == 2 and sig.lock_idx == 4 and sig.n_reopens == 1


def test_violent_pull_weak() -> None:
    # m0-m9 在 10.3,m10 拉到漲停鎖死:prelock 窗 [0,10) px0=10.3 → gain 6.8% ≥ 6%
    bars = [bar(m, 10.3) for m in range(10)] + [bar(m, LIMIT, open_=10.3) for m in (10, 11, 12)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.violent_pull is True
    assert sig.prelock10_gain == pytest.approx(LIMIT / 10.3 - 1)
    assert sig.tier == "weak"


def test_tail_lock_weak() -> None:
    bars = [bar(m, 10.5) for m in range(239)] + [bar(m, LIMIT) for m in range(239, 245)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.lock_time_bucket == "13:00+" and sig.tier == "weak"


def test_dead_lock_weak() -> None:
    # 早鎖非暴力,但鎖後量 <15% 日量(死鎖無量)→ weak
    bars = [bar(0, 10.6, v=500.0), bar(1, LIMIT, open_=10.6, v=440.0)] + \
           [bar(m, LIMIT, v=10.0) for m in range(2, 8)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.lock_idx == 1
    assert sig.vol_after_lock_share < 0.15 + 0.40  # sanity:實際 = 500/1000
    # 鎖後量 = m1 起 = (440+60)/1000 = 0.5 → 不是死鎖;改用嚴格構造:
    # (此 case 見下一個 test,本 test 只確認 share 計法含 final lock bar)
    assert sig.vol_after_lock_share == pytest.approx(0.5)


def test_dead_lock_weak_strict() -> None:
    bars = [bar(0, 10.6, v=900.0), bar(1, LIMIT, open_=10.6, v=50.0)] + \
           [bar(m, LIMIT, v=10.0) for m in range(2, 7)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.queue_bucket == "<15%" and sig.tier == "weak"


def test_never_touch_returns_none() -> None:
    assert run([bar(m, 10.0) for m in range(5)]).finalize() is None


def test_close_not_at_limit_returns_none() -> None:
    # 觸停但收盤掉下來(未鎖收盤)→ 與研究一致回 None
    bars = [bar(0, 10.0), bar(1, LIMIT), bar(2, 10.8, high=LIMIT)]
    assert run(bars).finalize() is None


def test_feed_non_increasing_raises() -> None:
    t = LockTracker(CFG, LIMIT)
    t.feed(bar(5, 10.0))
    with pytest.raises(ValueError):
        t.feed(bar(5, 10.1))


def test_no_lookahead_immutability() -> None:
    # 餵到 t 查詢的 first_touch/n_reopens,繼續餵資料後不得改變(SC-8)
    t = LockTracker(CFG, LIMIT)
    t.feed(bar(0, 10.5))
    t.feed(bar(1, LIMIT))
    ft, nr = t.first_touch_idx, t.n_reopens
    t.feed(bar(2, 10.9, high=LIMIT))   # 打開
    t.feed(bar(3, LIMIT))              # 回鎖
    assert t.first_touch_idx == ft == 1
    assert nr == 0 and t.n_reopens == 1  # 歷史查詢值不變;新值單調前進
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/engine/test_lock_quality.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/engine/__init__.py`:

```python
"""評分引擎 — 逐 bar 餵入的狀態機,零 IO,無 lookahead 為結構保證."""
from __future__ import annotations
```

`copycat/engine/lock_quality.py`:

```python
"""Phase 2 鎖板品質:LockTracker(鎖死定義與 neigui extract_features.py 對齊)."""
from __future__ import annotations

from dataclasses import dataclass

from copycat.data.models import Bar1K, fmt_min
from copycat.strategy_config import StrategyConfig

_LOCK_BUCKET_LABELS = ("<09:05", "09:05-10:00", "10:00-12:00", "12:00-13:00", "13:00+")


@dataclass(frozen=True, slots=True)
class LockQualitySignals:
    first_touch_idx: int
    first_touch_time: str
    lock_idx: int              # final lock 起點 bar 的分鐘索引
    lock_time: str
    lock_time_bucket: str
    n_reopens: int
    violent_pull: bool
    prelock10_gain: float | None
    vol_after_lock_share: float
    queue_bucket: str
    day_volume: float
    tier: str


def _lock_bucket(cfg: StrategyConfig, lock_idx: int) -> str:
    for label, cut in zip(_LOCK_BUCKET_LABELS, cfg.lock_time_buckets):
        if lock_idx < cut:
            return label
    return _LOCK_BUCKET_LABELS[-1]


def _queue_bucket(cfg: StrategyConfig, share: float) -> str:
    if share >= cfg.queue_strong_min:
        return ">=40%"
    if share < cfg.queue_dead_max:
        return "<15%"
    return "15-40%"


def _tier(cfg: StrategyConfig, lock_idx: int, violent: bool, share: float,
          n_reopens: int) -> str:
    if (lock_idx >= cfg.tail_lock_min_idx or violent
            or share < cfg.queue_dead_max or n_reopens >= cfg.open_count_weak):
        return "weak"
    if (lock_idx < cfg.early_lock_max_idx and not violent
            and share >= cfg.queue_strong_min and n_reopens <= cfg.open_count_strong_max):
        return "strong"
    return "neutral"


class LockTracker:
    """逐 bar 餵入;first_touch / n_reopens 盤中可查且不回改;finalize 收盤定稿."""

    def __init__(self, config: StrategyConfig, limit: float) -> None:
        self._cfg = config
        self._limit = limit
        self._bars: list[Bar1K] = []
        self._first_touch: int | None = None   # bars list 內的位置(非分鐘索引)
        self._n_reopens = 0
        self._in_limit = False
        self._run_start: int | None = None     # 當前連續 at_limit 段起點(list 位置)

    def _at_limit(self, b: Bar1K) -> bool:
        return b.close >= self._limit - self._cfg.limit_eps

    def feed(self, bar: Bar1K) -> None:
        if self._bars and bar.m <= self._bars[-1].m:
            raise ValueError(f"bar 時間未遞增: m={bar.m} (last={self._bars[-1].m})")
        self._bars.append(bar)
        i = len(self._bars) - 1
        touched = bar.high >= self._limit - self._cfg.limit_eps
        if self._first_touch is None and touched:
            self._first_touch = i
        if self._at_limit(bar):
            if not self._in_limit:
                self._in_limit = True
                self._run_start = i
        elif self._in_limit:
            self._in_limit = False
            self._run_start = None
            if self._first_touch is not None:
                self._n_reopens += 1

    @property
    def first_touch_idx(self) -> int | None:
        return self._bars[self._first_touch].m if self._first_touch is not None else None

    @property
    def n_reopens(self) -> int:
        return self._n_reopens

    def current_lock_start(self) -> int | None:
        return self._bars[self._run_start].m if self._run_start is not None else None

    def finalize(self) -> LockQualitySignals | None:
        cfg = self._cfg
        if self._first_touch is None or not self._in_limit or self._run_start is None:
            return None  # 全日未觸停,或收盤不在漲停(與研究定義一致)
        day_vol = sum(b.volume for b in self._bars)
        if day_vol <= 0:
            return None
        lock_pos = self._run_start
        lock_m = self._bars[lock_pos].m
        after_share = sum(b.volume for b in self._bars[lock_pos:]) / day_vol
        window = [b for b in self._bars[:lock_pos]
                  if b.m >= lock_m - cfg.violent_pull_window]
        gain = self._limit / window[0].open - 1 if window and window[0].open > 0 else None
        violent = gain is not None and gain >= cfg.violent_pull_min_gain
        return LockQualitySignals(
            first_touch_idx=self._bars[self._first_touch].m,
            first_touch_time=fmt_min(self._bars[self._first_touch].m),
            lock_idx=lock_m,
            lock_time=fmt_min(lock_m),
            lock_time_bucket=_lock_bucket(cfg, lock_m),
            n_reopens=self._n_reopens,
            violent_pull=violent,
            prelock10_gain=gain,
            vol_after_lock_share=after_share,
            queue_bucket=_queue_bucket(cfg, after_share),
            day_volume=day_vol,
            tier=_tier(cfg, lock_m, violent, after_share, self._n_reopens),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/engine/test_lock_quality.py -q`
Expected: `10 passed`

- [ ] **Step 5: 全套件回歸 + lint**

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check copycat tests
```
Expected: 全綠。

- [ ] **Step 6: Commit**

```powershell
git add copycat/engine tests/engine
git commit -m "feat(replay): LockTracker — 鎖板品質訊號與 tier(對齊研究鎖死定義)"
```

---

### Task 9: T+1 開盤引擎(EventContext + T1Tracker)

**Files:**
- Create: `copycat/engine/t1_open.py`
- Test: `tests/engine/test_t1_open.py`

**Interfaces:**
- Consumes: `Bar1K` / `fmt_min`(Task 2)、`StrategyConfig`(Task 7)、`LockQualitySignals`(Task 8)
- Produces:
  - `EventContext`(frozen dataclass):`stock_id: str`、`date: str`、`t1_date: str`、`limit: float`(T 日漲停收盤價)、`adv20_lots: float | None`(截至 T 日)、`one_price: bool | None`(T 日 high==low)、`board_streak: int`(T 日)、`lock: LockQualitySignals | None`
  - `T1OpenSignals`(frozen dataclass):`open_px: float`、`gap: float`、`gap_bucket: str`、`auction_lots: float`、`auction_share_adv20: float | None`、`auction_tell: str`、`auction_share_dayvol: float`(研究版,收盤定稿)、`inner15: float | None`、`high_idx: int`、`high_time: str`、`high_vs_open: float`、`close_vs_open: float`、`touched_limit: bool`、`path: str`
  - `T1Tracker` class:
    - `__init__(self, config: StrategyConfig, ctx: EventContext)`
    - `feed(self, bar: Bar1K) -> None`(m 不遞增 raise)
    - property `gap: float | None`、`auction_tell: str | None`(首根餵入後即可查,之後不變 — 盤中即時訊號)
    - `finalize(self, again: bool) -> T1OpenSignals | None`(無 bar 或日量 0 → None;`again` = T+1 是否收盤再鎖,由呼叫端從漲停集合查)
  - bucket 標籤(固定字串):gap `"<0%" / "0-1%" / "1-3%" / "3-7%" / "7-9.5%" / "漲停開"`;auction `"<3%" / "3-8%" / ">=8%" / "n/a"`;path `"再鎖" / "觸停回落" / "拉高出貨" / "開盤直倒" / "低開反拉" / "陰跌" / "強勢收高"`(與研究 `t1_day_features` 分類邏輯一致)
- **無 lookahead 修正(spec §4c)**:`auction_tell` 用 `auction_lots ÷ adv20_lots`(09:00:06 可知);`auction_share_dayvol` 是研究版對照值,只在 finalize 出現。

- [ ] **Step 1: Write the failing test**

`tests/engine/test_t1_open.py`:

```python
from __future__ import annotations

import pytest

from copycat.data.models import Bar1K
from copycat.engine.t1_open import EventContext, T1Tracker
from copycat.strategy_config import StrategyConfig

CFG = StrategyConfig.default()
LIMIT_T = 100.0  # T 日漲停收盤
T1_LIMIT = LIMIT_T * CFG.t1_limit_mult  # 109.5


def ctx(adv20: float | None = 1000.0) -> EventContext:
    return EventContext(stock_id="1104", date="2025-09-10", t1_date="2025-09-11",
                        limit=LIMIT_T, adv20_lots=adv20, one_price=False,
                        board_streak=1, lock=None)


def bar(m: int, close: float, *, open_: float | None = None, high: float | None = None,
        v: float = 10.0, uv: float | None = None, dv: float | None = None) -> Bar1K:
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close)
    u = uv if uv is not None else v
    d = dv if dv is not None else 0.0
    return Bar1K(m=m, open=o, high=h, low=min(o, close), close=close,
                 volume=v, up_volume=u, down_volume=d, unch_volume=0.0)


def run(bars: list[Bar1K], again: bool = False, adv20: float | None = 1000.0):
    t = T1Tracker(CFG, ctx(adv20))
    for b in bars:
        t.feed(b)
    return t.finalize(again)


def test_gap_buckets() -> None:
    # 開 103 → gap 3% → "3-7%"
    sig = run([bar(0, 103.0, v=100.0), bar(1, 104.0)])
    assert sig is not None
    assert sig.gap == pytest.approx(0.03) and sig.gap_bucket == "3-7%"
    assert run([bar(0, 99.0)]).gap_bucket == "<0%"          # type: ignore[union-attr]
    assert run([bar(0, 100.5)]).gap_bucket == "0-1%"        # type: ignore[union-attr]
    assert run([bar(0, 108.0)]).gap_bucket == "7-9.5%"      # type: ignore[union-attr]
    assert run([bar(0, 110.0)]).gap_bucket == "漲停開"       # type: ignore[union-attr]


def test_auction_tell_uses_adv20() -> None:
    # 首根量 100 張 / adv20 1000 張 = 10% → ">=8%"
    sig = run([bar(0, 103.0, v=100.0), bar(1, 104.0, v=50.0)])
    assert sig is not None
    assert sig.auction_lots == 100.0
    assert sig.auction_share_adv20 == pytest.approx(0.10)
    assert sig.auction_tell == ">=8%"
    assert sig.auction_share_dayvol == pytest.approx(100.0 / 150.0)  # 研究版(收盤定稿)


def test_auction_tell_without_adv20_is_na() -> None:
    sig = run([bar(0, 103.0)], adv20=None)
    assert sig is not None and sig.auction_tell == "n/a" and sig.auction_share_adv20 is None


def test_inner15_window() -> None:
    # 前 15 分鐘:內盤 60 / (40+60) = 60%;m=20 的 bar 不計入
    bars = [bar(0, 103.0, v=100.0, uv=40.0, dv=60.0), bar(20, 104.0, v=50.0, uv=50.0, dv=0.0)]
    sig = run(bars)
    assert sig is not None and sig.inner15 == pytest.approx(0.60)


def test_path_pull_high_dump() -> None:
    # 開 103 → 8 分鐘拉到 106(+2.9% ≥2%)→ 收 101(< 開)→ 拉高出貨
    bars = [bar(0, 103.0), bar(8, 106.0), bar(200, 101.0)]
    sig = run(bars)
    assert sig is not None
    assert sig.path == "拉高出貨" and sig.high_idx == 8 and sig.high_time == "09:09"


def test_path_touched_and_again() -> None:
    bars = [bar(0, 109.5), bar(1, 108.0, high=110.0)]
    sig = run(bars)
    assert sig is not None and sig.touched_limit is True and sig.path == "觸停回落"
    sig2 = run(bars, again=True)
    assert sig2 is not None and sig2.path == "再鎖"


def test_path_low_open_rebound() -> None:
    bars = [bar(0, 98.0), bar(30, 101.0)]
    sig = run(bars)
    assert sig is not None and sig.path == "低開反拉"


def test_intraday_query_immutable() -> None:
    # 首根餵入後 gap / auction_tell 即可查,之後不變(SC-8)
    t = T1Tracker(CFG, ctx())
    t.feed(bar(0, 103.0, v=100.0))
    g, tell = t.gap, t.auction_tell
    t.feed(bar(1, 108.0, v=500.0))
    assert t.gap == g and t.auction_tell == tell


def test_empty_returns_none() -> None:
    t = T1Tracker(CFG, ctx())
    assert t.finalize(False) is None


def test_feed_non_increasing_raises() -> None:
    t = T1Tracker(CFG, ctx())
    t.feed(bar(3, 103.0))
    with pytest.raises(ValueError):
        t.feed(bar(2, 104.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/engine/test_t1_open.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/engine/t1_open.py`:

```python
"""Phase 3 T+1 開盤訊號:T1Tracker(路徑分類與研究 t1_day_features 對齊).

無 lookahead 修正:auction_tell 分母用 adv20(09:00:06 可知),
研究版 ÷全日量 只在 finalize 出現、僅供 golden 對照(spec §4c)。
"""
from __future__ import annotations

from dataclasses import dataclass

from copycat.data.models import Bar1K, fmt_min
from copycat.engine.lock_quality import LockQualitySignals
from copycat.strategy_config import StrategyConfig

_GAP_LABELS = ("<0%", "0-1%", "1-3%", "3-7%", "7-9.5%", "漲停開")


@dataclass(frozen=True, slots=True)
class EventContext:
    stock_id: str
    date: str          # T 日
    t1_date: str
    limit: float       # T 日漲停收盤價
    adv20_lots: float | None   # 截至 T 日的 20 日均量(張)
    one_price: bool | None     # T 日一價到底(日線 high==low)
    board_streak: int          # T 日連板數
    lock: LockQualitySignals | None


@dataclass(frozen=True, slots=True)
class T1OpenSignals:
    open_px: float
    gap: float
    gap_bucket: str
    auction_lots: float
    auction_share_adv20: float | None
    auction_tell: str
    auction_share_dayvol: float   # 研究版(收盤定稿,golden 對照用)
    inner15: float | None
    high_idx: int
    high_time: str
    high_vs_open: float
    close_vs_open: float
    touched_limit: bool
    path: str


def _gap_bucket(cfg: StrategyConfig, gap: float) -> str:
    for label, cut in zip(_GAP_LABELS, cfg.gap_buckets):
        if gap < cut:
            return label
    return _GAP_LABELS[-1]


def _auction_tell(cfg: StrategyConfig, share: float | None) -> str:
    if share is None:
        return "n/a"
    lo, hi = cfg.auction_buckets
    if share < lo:
        return "<3%"
    if share < hi:
        return "3-8%"
    return ">=8%"


class T1Tracker:
    def __init__(self, config: StrategyConfig, ctx: EventContext) -> None:
        self._cfg = config
        self._ctx = ctx
        self._t1_limit = ctx.limit * config.t1_limit_mult
        self._bars: list[Bar1K] = []
        self._high = float("-inf")
        self._high_pos = -1

    def feed(self, bar: Bar1K) -> None:
        if self._bars and bar.m <= self._bars[-1].m:
            raise ValueError(f"bar 時間未遞增: m={bar.m} (last={self._bars[-1].m})")
        self._bars.append(bar)
        if bar.high > self._high:
            self._high = bar.high
            self._high_pos = len(self._bars) - 1

    @property
    def gap(self) -> float | None:
        if not self._bars:
            return None
        return self._bars[0].open / self._ctx.limit - 1

    @property
    def auction_tell(self) -> str | None:
        if not self._bars:
            return None
        return _auction_tell(self._cfg, self._auction_share_adv20())

    def _auction_share_adv20(self) -> float | None:
        adv = self._ctx.adv20_lots
        if adv is None or adv <= 0 or not self._bars:
            return None
        return self._bars[0].volume / adv

    def finalize(self, again: bool) -> T1OpenSignals | None:
        cfg = self._cfg
        bars = self._bars
        if not bars:
            return None
        day_vol = sum(b.volume for b in bars)
        if day_vol <= 0:
            return None
        open_px = bars[0].open
        if open_px <= 0:
            return None
        close_px = bars[-1].close
        high = self._high
        high_m = bars[self._high_pos].m
        w15 = [b for b in bars if b.m < cfg.inner_window]
        up15 = sum(b.up_volume for b in w15)
        dn15 = sum(b.down_volume for b in w15)
        inner15 = dn15 / (up15 + dn15) if up15 + dn15 > 0 else None
        touched = high >= self._t1_limit - cfg.limit_eps
        if again:
            path = "再鎖"
        elif touched:
            path = "觸停回落"
        elif (high >= open_px * (1 + cfg.pull_high_min) and close_px < open_px
              and high_m <= cfg.pull_high_max_idx):
            path = "拉高出貨"
        elif high <= open_px * 1.01 and close_px < open_px:
            path = "開盤直倒"
        elif open_px < self._ctx.limit and close_px > open_px:
            path = "低開反拉"
        elif close_px < open_px:
            path = "陰跌"
        else:
            path = "強勢收高"
        gap = open_px / self._ctx.limit - 1
        return T1OpenSignals(
            open_px=open_px,
            gap=gap,
            gap_bucket=_gap_bucket(cfg, gap),
            auction_lots=bars[0].volume,
            auction_share_adv20=self._auction_share_adv20(),
            auction_tell=_auction_tell(cfg, self._auction_share_adv20()),
            auction_share_dayvol=bars[0].volume / day_vol,
            inner15=inner15,
            high_idx=high_m,
            high_time=fmt_min(high_m),
            high_vs_open=high / open_px - 1,
            close_vs_open=close_px / open_px - 1,
            touched_limit=touched,
            path=path,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/engine/test_t1_open.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/engine/t1_open.py tests/engine/test_t1_open.py
git commit -m "feat(replay): T1Tracker — T+1 開盤訊號(gap/競價 tell/內盤比/路徑分類)"
```

---

### Task 10: Replay runner + `replay` CLI

**Files:**
- Create: `copycat/replay/__init__.py`(docstring + future import,同 engine)
- Create: `copycat/replay/runner.py`
- Modify: `copycat/cli.py`(加 `replay` subcommand)
- Test: `tests/replay/test_runner.py`

**Interfaces:**
- Consumes: `read_bars`(Task 3)、`DailyIndex`(Task 4)、`load_watchlist`(Task 5)、`StrategyConfig/load_config`(Task 7)、`LockTracker`(Task 8)、`EventContext/T1Tracker`(Task 9)
- Produces:
  - `run_replay(data_dir: Path, watchlist_path: Path, out_dir: Path, config_path: Path | None = None) -> Path`(回傳 run 目錄)
  - run 目錄內容:
    - `events.jsonl`:每事件一行 `{"stock_id","date","t1_date","source","cohort","broker_ids","again","lock": {…LockQualitySignals}|null,"t1": {…T1OpenSignals}|null,"skip": [原因…]}`
    - `meta.json`:`{"watchlist","config_path","n_events","n_tiger","n_excluded","n_control","missing_t","missing_t1"}`
  - **cohort 規則**:事件任一 `broker_ids` ∈ watchlist → `"tiger"`;`source=="control"` → `"control"`;source 是 tiger_csv 但無成員命中 → `"excluded"`(換 watchlist 時的差集,報表列數量不列統計)
  - `again` = `daily.is_limitup(stock_id, t1_date)`
  - 缺 T 日 1K → `lock=null` + skip 記 `"missing_t_1k"`;缺 T+1 1K → `t1=null` + skip 記 `"missing_t1_1k"`(不靜默,計數進 meta)

- [ ] **Step 1: Write the failing test**

`tests/replay/test_runner.py`(fixture 沿用 Task 6 的 `_write_src`/`_write_events_csv` 產出的 data 目錄;抽成 `tests/replay/conftest.py` 的 `imported_data` fixture):

`tests/replay/conftest.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.data.import_neigui import run_import
from tests.data.test_import_neigui import _write_events_csv, _write_src


@pytest.fixture()
def imported_data(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    _write_src(src)
    ev_csv = tmp_path / "tigers.csv"
    _write_events_csv(ev_csv)
    data = tmp_path / "data"
    run_import(src, ev_csv, data)
    return data


@pytest.fixture()
def watchlist_four(tmp_path: Path) -> Path:
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"name": "four_tigers", "members": [
        {"broker_id": "779c", "name": "國票敦北"},
        {"broker_id": "779Z", "name": "國票安和"},
    ]}), encoding="utf-8")
    return p
```

`tests/replay/test_runner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.runner import run_replay


def test_run_replay(imported_data: Path, watchlist_four: Path, tmp_path: Path) -> None:
    run_dir = run_replay(imported_data, watchlist_four, tmp_path / "out")
    lines = [json.loads(x) for x in
             (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    by_key = {(e["stock_id"], e["date"]): e for e in lines}

    tiger = by_key[("1104", "2025-09-10")]
    assert tiger["cohort"] == "tiger"
    # fixture 的 1104 T 日兩根 bar 全在漲停(32)→ 開盤鎖
    assert tiger["lock"] is not None and tiger["lock"]["lock_time_bucket"] == "<09:05"
    # T+1 開 33 → gap 3.125% → "3-7%"
    assert tiger["t1"] is not None and tiger["t1"]["gap_bucket"] == "3-7%"
    assert tiger["again"] is False

    ctrl = by_key[("2001", "2025-09-10")]
    assert ctrl["cohort"] == "control"
    assert ctrl["t1"] is None and "missing_t1_1k" in ctrl["skip"]

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["n_tiger"] == 1 and meta["n_control"] == 1 and meta["missing_t1"] == 1


def test_watchlist_excludes(imported_data: Path, tmp_path: Path) -> None:
    # watchlist 只含 9227 → 1104 事件(779c/779Z)變 excluded
    wl = tmp_path / "wl2.json"
    wl.write_text(json.dumps({"name": "kgi_only", "members": [
        {"broker_id": "9227", "name": "凱基城中"}]}), encoding="utf-8")
    run_dir = run_replay(imported_data, wl, tmp_path / "out2")
    lines = [json.loads(x) for x in
             (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    ev = next(e for e in lines if e["stock_id"] == "1104")
    assert ev["cohort"] == "excluded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/replay -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/replay/__init__.py`:

```python
"""Replay 執行器:事件清單 → 引擎 → events.jsonl + 彙總報表."""
from __future__ import annotations
```

`copycat/replay/runner.py`:

```python
"""對事件清單跑引擎(T 日 LockTracker → EventContext → T+1 T1Tracker)."""
from __future__ import annotations

import csv
import dataclasses
import json
import logging
from pathlib import Path

from copycat.data.daily import DailyIndex
from copycat.data.store import read_bars
from copycat.engine.lock_quality import LockTracker
from copycat.engine.t1_open import EventContext, T1Tracker
from copycat.strategy_config import StrategyConfig, load_config
from copycat.watchlist import load_watchlist

logger = logging.getLogger(__name__)


def _cohort(source: str, broker_ids: str, members: frozenset[str]) -> str:
    if source == "control":
        return "control"
    brokers = set(broker_ids.split("|")) if broker_ids else set()
    return "tiger" if brokers & members else "excluded"


def run_replay(data_dir: Path, watchlist_path: Path, out_dir: Path,
               config_path: Path | None = None) -> Path:
    cfg = load_config(config_path) if config_path else StrategyConfig.default()
    wl = load_watchlist(watchlist_path)
    daily = DailyIndex.load(data_dir)
    run_dir = out_dir / wl.name
    run_dir.mkdir(parents=True, exist_ok=True)

    counts = {"tiger": 0, "control": 0, "excluded": 0}
    missing_t = 0
    missing_t1 = 0
    n_events = 0
    with (data_dir / "events" / "events.csv").open("r", encoding="utf-8") as fh, \
            (run_dir / "events.jsonl").open("w", encoding="utf-8") as out:
        for ev in csv.DictReader(fh):
            n_events += 1
            cohort = _cohort(ev["source"], ev["broker_ids"], wl.broker_ids)
            counts[cohort] += 1
            limit = float(ev["limitup_close"])
            skip: list[str] = []

            lock_sig = None
            t_bars = read_bars(data_dir, ev["stock_id"], ev["date"])
            if t_bars is None:
                skip.append("missing_t_1k")
                missing_t += 1
            else:
                tracker = LockTracker(cfg, limit)
                for b in t_bars:
                    tracker.feed(b)
                lock_sig = tracker.finalize()

            t1_sig = None
            again = False
            if not ev["t1_date"]:
                skip.append("no_t1_date")
            else:
                again = daily.is_limitup(ev["stock_id"], ev["t1_date"])
                t1_bars = read_bars(data_dir, ev["stock_id"], ev["t1_date"])
                if t1_bars is None:
                    skip.append("missing_t1_1k")
                    missing_t1 += 1
                else:
                    ctx = EventContext(
                        stock_id=ev["stock_id"], date=ev["date"], t1_date=ev["t1_date"],
                        limit=limit,
                        adv20_lots=daily.adv20(ev["stock_id"], ev["date"]),
                        one_price=daily.one_price(ev["stock_id"], ev["date"]),
                        board_streak=daily.board_streak(ev["stock_id"], ev["date"]),
                        lock=lock_sig,
                    )
                    t1 = T1Tracker(cfg, ctx)
                    for b in t1_bars:
                        t1.feed(b)
                    t1_sig = t1.finalize(again)

            out.write(json.dumps({
                "stock_id": ev["stock_id"], "date": ev["date"], "t1_date": ev["t1_date"],
                "source": ev["source"], "cohort": cohort, "broker_ids": ev["broker_ids"],
                "again": again,
                "lock": dataclasses.asdict(lock_sig) if lock_sig else None,
                "t1": dataclasses.asdict(t1_sig) if t1_sig else None,
                "skip": skip,
            }, ensure_ascii=False) + "\n")

    meta = {
        "watchlist": wl.name, "config_path": str(config_path) if config_path else "(default)",
        "n_events": n_events, "n_tiger": counts["tiger"], "n_control": counts["control"],
        "n_excluded": counts["excluded"], "missing_t": missing_t, "missing_t1": missing_t1,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("replay 完成: %s", meta)
    return run_dir
```

`copycat/cli.py` 加 subcommand(在 `import-neigui` 區塊後加;`main()` 的 dispatch 加分支):

```python
    p_rep = sub.add_parser("replay", help="對事件清單跑評分引擎")
    p_rep.add_argument("--watchlist", type=Path, default=Path("watchlists/four_tigers.json"))
    p_rep.add_argument("--config", type=Path, default=None)
    p_rep.add_argument("--data-dir", type=Path, default=Path("data"))
    p_rep.add_argument("--out", type=Path, default=Path("out"))
```

```python
    if args.command == "replay":
        from copycat.replay.runner import run_replay
        run_dir = run_replay(args.data_dir, args.watchlist, args.out, args.config)
        sys.stdout.write(f"replay 完成 → {run_dir}\n")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/replay -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/replay tests/replay copycat/cli.py
git commit -m "feat(replay): replay runner — 事件迴圈餵引擎輸出 events.jsonl + meta"
```

---

### Task 11: 彙總報表(report.py → summary.md)

**Files:**
- Create: `copycat/replay/report.py`
- Modify: `copycat/replay/runner.py`(`run_replay` 末尾呼叫 `write_summary(run_dir)`)
- Test: `tests/replay/test_report.py`

**Interfaces:**
- Consumes: run 目錄的 `events.jsonl`(Task 10 schema)
- Produces:
  - `load_events(run_dir: Path) -> list[dict]`
  - `med(xs: list[float]) -> float | None`(排序取 `[n//2]`,與研究腳本一致)
  - `agg_lock_buckets(events, cohort) -> list[dict]`:per `lock_time_bucket` → `{bucket, n, med_gap, again_rate}`(僅 lock 非 null 且 t1 非 null 的事件;med_gap 用 `t1.gap`)
  - `agg_violent(events, cohort) -> dict`:`{"violent": {n, med_gap, again_rate}, "natural_early": …}`(natural_early = `lock_idx < 4` 且非 violent_pull,對應「開盤 5 分內自然鎖」)
  - `agg_queue(events, cohort) -> list[dict]`:早盤鎖(lock_idx < 59)× queue_bucket → `{bucket, n, med_gap, again_rate}`
  - `agg_gap_buckets(events, cohort) -> list[dict]`:per `gap_bucket` → `{bucket, n, share, mean_open_to_close, p_win, again_rate, touched_rate}`(mean_open_to_close = `t1.close_vs_open` 平均;p_win = close_vs_open > 0 比例)
  - `agg_auction(events, cohort, basis) -> list[dict]`:basis `"dayvol"`(研究版,`auction_share_dayvol` 以 3%/8% 分桶)或 `"adv20"`(盤中版,用 `auction_tell` 現成標籤)→ `{bucket, n, med_gap}`
  - `write_summary(run_dir: Path) -> Path`:把上述表(tiger 與 control 各一組)寫成 `summary.md`(markdown 表格,標題含 cohort 與 n;excluded 只列數量)
- 百分比欄輸出格式 `+X.X%` / `X.X%`;n=0 的桶照列(n=0,其餘欄 `—`),不靜默消失。

- [ ] **Step 1: Write the failing test**

`tests/replay/test_report.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.report import agg_gap_buckets, agg_lock_buckets, med, write_summary


def _event(gap_bucket: str, gap: float, close_vs_open: float, again: bool,
           lock_bucket: str = "<09:05", lock_idx: int = 0) -> dict:
    return {
        "stock_id": "1104", "date": "2025-09-10", "cohort": "tiger", "again": again,
        "skip": [],
        "lock": {"lock_time_bucket": lock_bucket, "lock_idx": lock_idx,
                 "violent_pull": False, "queue_bucket": ">=40%", "n_reopens": 0},
        "t1": {"gap": gap, "gap_bucket": gap_bucket, "close_vs_open": close_vs_open,
               "touched_limit": False, "auction_share_dayvol": 0.05,
               "auction_tell": "3-8%"},
    }


def test_med_matches_research_convention() -> None:
    assert med([1.0, 2.0, 4.0, 8.0]) == 4.0  # sorted[n//2],非平均中位


def test_agg_lock_buckets() -> None:
    events = [_event("3-7%", 0.05, 0.01, again=True),
              _event("3-7%", 0.03, -0.02, again=False)]
    rows = agg_lock_buckets(events, "tiger")
    b = next(r for r in rows if r["bucket"] == "<09:05")
    assert b["n"] == 2 and b["med_gap"] == 0.05 and b["again_rate"] == 0.5


def test_agg_gap_buckets_share_and_pwin() -> None:
    events = [_event("3-7%", 0.05, 0.01, True), _event("1-3%", 0.02, -0.02, False)]
    rows = agg_gap_buckets(events, "tiger")
    r37 = next(r for r in rows if r["bucket"] == "3-7%")
    assert r37["n"] == 1 and r37["share"] == 0.5 and r37["p_win"] == 1.0


def test_write_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_event("3-7%", 0.05, 0.01, True), ensure_ascii=False) + "\n")
    out = write_summary(run_dir)
    text = out.read_text(encoding="utf-8")
    assert "鎖板時間" in text and "gap 分桶" in text and "cohort=tiger" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/replay/test_report.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/replay/report.py`:

```python
"""events.jsonl → summary.md 彙總表(對照 evidence golden 的表格式)."""
from __future__ import annotations

import json
from pathlib import Path

_LOCK_BUCKETS = ("<09:05", "09:05-10:00", "10:00-12:00", "12:00-13:00", "13:00+")
_GAP_BUCKETS = ("<0%", "0-1%", "1-3%", "3-7%", "7-9.5%", "漲停開")
_QUEUE_BUCKETS = (">=40%", "15-40%", "<15%")
_AUCTION_BUCKETS = ("<3%", "3-8%", ">=8%")


def load_events(run_dir: Path) -> list[dict]:
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines]


def med(xs: list[float]) -> float | None:
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def _full(events: list[dict], cohort: str) -> list[dict]:
    """lock 與 t1 都齊的事件(golden 表同樣以有 T 日 1K 且鎖住者統計)."""
    return [e for e in events
            if e["cohort"] == cohort and e.get("lock") and e.get("t1")]


def _rate(sel: list[dict], pred) -> float | None:
    return sum(1 for e in sel if pred(e)) / len(sel) if sel else None


def agg_lock_buckets(events: list[dict], cohort: str) -> list[dict]:
    full = _full(events, cohort)
    rows = []
    for bucket in _LOCK_BUCKETS:
        sel = [e for e in full if e["lock"]["lock_time_bucket"] == bucket]
        rows.append({
            "bucket": bucket, "n": len(sel),
            "med_gap": med([e["t1"]["gap"] for e in sel]),
            "again_rate": _rate(sel, lambda e: e["again"]),
        })
    return rows


def agg_violent(events: list[dict], cohort: str) -> dict[str, dict]:
    full = _full(events, cohort)
    violent = [e for e in full if e["lock"]["violent_pull"]]
    natural = [e for e in full
               if e["lock"]["lock_idx"] < 4 and not e["lock"]["violent_pull"]]
    def stats(sel: list[dict]) -> dict:
        return {"n": len(sel), "med_gap": med([e["t1"]["gap"] for e in sel]),
                "again_rate": _rate(sel, lambda e: e["again"])}
    return {"violent": stats(violent), "natural_early": stats(natural)}


def agg_queue(events: list[dict], cohort: str) -> list[dict]:
    full = [e for e in _full(events, cohort) if e["lock"]["lock_idx"] < 59]  # 早盤鎖
    rows = []
    for bucket in _QUEUE_BUCKETS:
        sel = [e for e in full if e["lock"]["queue_bucket"] == bucket]
        rows.append({"bucket": bucket, "n": len(sel),
                     "med_gap": med([e["t1"]["gap"] for e in sel]),
                     "again_rate": _rate(sel, lambda e: e["again"])})
    return rows


def agg_gap_buckets(events: list[dict], cohort: str) -> list[dict]:
    sel_all = [e for e in events if e["cohort"] == cohort and e.get("t1")]
    rows = []
    for bucket in _GAP_BUCKETS:
        sel = [e for e in sel_all if e["t1"]["gap_bucket"] == bucket]
        oc = [e["t1"]["close_vs_open"] for e in sel]
        rows.append({
            "bucket": bucket, "n": len(sel),
            "share": len(sel) / len(sel_all) if sel_all else None,
            "mean_open_to_close": sum(oc) / len(oc) if oc else None,
            "p_win": _rate(sel, lambda e: e["t1"]["close_vs_open"] > 0),
            "again_rate": _rate(sel, lambda e: e["again"]),
            "touched_rate": _rate(sel, lambda e: e["t1"]["touched_limit"]),
        })
    return rows


def agg_auction(events: list[dict], cohort: str, basis: str) -> list[dict]:
    sel_all = [e for e in events if e["cohort"] == cohort and e.get("t1")]
    rows = []
    for bucket in _AUCTION_BUCKETS:
        if basis == "dayvol":
            def in_bucket(e: dict, b: str = bucket) -> bool:
                s = e["t1"]["auction_share_dayvol"]
                return {"<3%": s < 0.03, "3-8%": 0.03 <= s < 0.08, ">=8%": s >= 0.08}[b]
            sel = [e for e in sel_all if in_bucket(e)]
        else:  # adv20(盤中版,用引擎現成標籤)
            sel = [e for e in sel_all if e["t1"]["auction_tell"] == bucket]
        rows.append({"bucket": bucket, "n": len(sel),
                     "med_gap": med([e["t1"]["gap"] for e in sel])})
    return rows


def _pct(x: float | None, signed: bool = True) -> str:
    if x is None:
        return "—"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def write_summary(run_dir: Path) -> Path:
    events = load_events(run_dir)
    parts: list[str] = ["# Replay 彙總\n"]
    n_excluded = sum(1 for e in events if e["cohort"] == "excluded")
    n_skip = sum(1 for e in events if e["skip"])
    parts.append(f"- 事件總數 {len(events)};excluded(watchlist 未命中){n_excluded};"
                 f"有缺漏(skip 非空){n_skip}\n")
    for cohort in ("tiger", "control"):
        n = sum(1 for e in events if e["cohort"] == cohort)
        parts.append(f"\n## cohort={cohort}(n={n})\n")
        parts.append("\n### 鎖板時間 × T+1\n")
        parts.append(_table(
            ["bucket", "n", "med gap", "續鎖率"],
            [[r["bucket"], str(r["n"]), _pct(r["med_gap"]), _pct(r["again_rate"], False)]
             for r in agg_lock_buckets(events, cohort)]))
        v = agg_violent(events, cohort)
        parts.append("\n\n### 暴力拉板 vs 開盤自然鎖\n")
        parts.append(_table(
            ["type", "n", "med gap", "續鎖率"],
            [[k, str(s["n"]), _pct(s["med_gap"]), _pct(s["again_rate"], False)]
             for k, s in v.items()]))
        parts.append("\n\n### 早盤鎖 × 鎖後排隊消耗\n")
        parts.append(_table(
            ["bucket", "n", "med gap", "續鎖率"],
            [[r["bucket"], str(r["n"]), _pct(r["med_gap"]), _pct(r["again_rate"], False)]
             for r in agg_queue(events, cohort)]))
        parts.append("\n\n### T+1 gap 分桶\n")
        parts.append(_table(
            ["bucket", "n", "占比", "E[開→收]", "P(win)", "續鎖率", "觸停率"],
            [[r["bucket"], str(r["n"]), _pct(r["share"], False),
              _pct(r["mean_open_to_close"]), _pct(r["p_win"], False),
              _pct(r["again_rate"], False), _pct(r["touched_rate"], False)]
             for r in agg_gap_buckets(events, cohort)]))
        parts.append("\n\n### 競價量 tell(研究版 ÷全日量)\n")
        parts.append(_table(
            ["bucket", "n", "med gap"],
            [[r["bucket"], str(r["n"]), _pct(r["med_gap"])]
             for r in agg_auction(events, cohort, "dayvol")]))
        parts.append("\n\n### 競價量 tell(盤中版 ÷20日均量,無 lookahead)\n")
        parts.append(_table(
            ["bucket", "n", "med gap"],
            [[r["bucket"], str(r["n"]), _pct(r["med_gap"])]
             for r in agg_auction(events, cohort, "adv20")]))
        parts.append("\n")
    out = run_dir / "summary.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
```

`runner.py` 末尾(`return run_dir` 前)加:

```python
    from copycat.replay.report import write_summary
    write_summary(run_dir)
```

(import 移到檔頭 `from copycat.replay.report import write_summary`,circular import 不存在 — report 不 import runner。)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/replay -q`
Expected: 全 passed(runner 兩測 + report 四測)。

- [ ] **Step 5: Commit**

```powershell
git add copycat/replay/report.py copycat/replay/runner.py tests/replay/test_report.py
git commit -m "feat(replay): summary.md 彙總報表(golden 對照表格式,雙 cohort)"
```

---

### Task 12: Golden 驗證(validate)

**Files:**
- Create: `copycat/replay/validate.py`
- Modify: `copycat/cli.py`(加 `validate` subcommand)
- Test: `tests/replay/test_validate.py`

**Interfaces:**
- Consumes: `load_events` / `agg_*`(Task 11)
- Produces:
  - `run_validate(run_five: Path, run_four: Path) -> list[dict]`:每筆 `{"sc","name","golden","actual","tol","ok"}`
  - `format_validate(checks: list[dict]) -> str`(markdown;PASS/FAIL 每行)
  - CLI `validate --run-five PATH --run-four PATH [--out PATH]`:印結果,任一 FAIL → exit code 1
- **Golden 常數(硬編,出處 docs/evidence)**:
  - SC-2 鎖板時間五桶(five_tigers run,tiger cohort;golden n=1023):`("<09:05",175,+7.4%,18.3%) / ("09:05-10:00",322,+3.5%,5.6%) / ("10:00-12:00",311,+2.4%,6.8%) / ("12:00-13:00",125,+1.5%,11.2%) / ("13:00+",90,+0.6%,4.4%)`
  - SC-3(five_tigers):violent `med gap +6.2% / 續鎖 3.3%`;natural_early `續鎖 18.3%`
  - SC-4(five_tigers,早盤鎖):`>=40% → med gap +6.0% / 續鎖 13.2%`;`<15% → 續鎖 0%`
  - SC-5 gap 六桶(four_tigers run,golden n=542):n `92/63/96/170/45/76`;E[開→收] `+0.72%/+0.26%/−1.60%/−1.64%/−3.47%/−1.26%`;續鎖 `2.2%/4.8%/0%/9.4%/6.7%/26.3%`
  - SC-6 競價 tell 研究版(five_tigers):`<3% → med gap +1.8% / 3-8% → +2.7% / >=8% → +9.0%`
- **容忍度(spec §6)**:n 差 ≤5%(相對);med gap 與 E[開→收] 差 ≤0.5pp;續鎖率差 ≤1pp;SC-3 續鎖率差 ≤3pp 且方向(natural ≫ violent)必須成立。

- [ ] **Step 1: Write the failing test**

`tests/replay/test_validate.py`:

```python
from __future__ import annotations

from copycat.replay.validate import _within_pp, _within_rel, format_validate


def test_within_rel() -> None:
    assert _within_rel(actual=100, golden=104, tol=0.05) is True
    assert _within_rel(actual=100, golden=111, tol=0.05) is False


def test_within_pp() -> None:
    assert _within_pp(actual=0.074, golden=0.070, tol=0.005) is True
    assert _within_pp(actual=0.074, golden=0.060, tol=0.005) is False
    assert _within_pp(actual=None, golden=0.06, tol=0.005) is False  # 缺值 = FAIL


def test_format_validate_marks_fail() -> None:
    checks = [{"sc": "SC-2", "name": "x", "golden": "175", "actual": "170",
               "tol": "±5%", "ok": True},
              {"sc": "SC-5", "name": "y", "golden": "+0.72%", "actual": "+2.0%",
               "tol": "±0.5pp", "ok": False}]
    text = format_validate(checks)
    assert "PASS" in text and "FAIL" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/replay/test_validate.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/replay/validate.py`:

```python
"""Characterization gate:replay 彙總 vs docs/evidence golden(spec §6 SC-2~SC-6)."""
from __future__ import annotations

from pathlib import Path

from copycat.replay.report import (agg_auction, agg_gap_buckets, agg_lock_buckets,
                                   agg_queue, agg_violent, load_events)

# golden 出處:intraday_playbook §2d / open_gap_definition §2-3 / strategy.md §5
_G_LOCK = [("<09:05", 175, 0.074, 0.183), ("09:05-10:00", 322, 0.035, 0.056),
           ("10:00-12:00", 311, 0.024, 0.068), ("12:00-13:00", 125, 0.015, 0.112),
           ("13:00+", 90, 0.006, 0.044)]
_G_GAP = [("<0%", 92, 0.0072, 0.022), ("0-1%", 63, 0.0026, 0.048),
          ("1-3%", 96, -0.0160, 0.000), ("3-7%", 170, -0.0164, 0.094),
          ("7-9.5%", 45, -0.0347, 0.067), ("漲停開", 76, -0.0126, 0.263)]
_G_AUCTION = [("<3%", 0.018), ("3-8%", 0.027), (">=8%", 0.090)]

_TOL_N = 0.05       # n 相對差
_TOL_GAP = 0.005    # med gap / E 差(0.5pp)
_TOL_AGAIN = 0.01   # 續鎖率差(1pp)
_TOL_SC3 = 0.03     # SC-3 續鎖率差(3pp,violent_pull 為 1K 近似)


def _within_rel(actual: float | None, golden: float, tol: float) -> bool:
    return actual is not None and golden > 0 and abs(actual - golden) / golden <= tol


def _within_pp(actual: float | None, golden: float, tol: float) -> bool:
    return actual is not None and abs(actual - golden) <= tol


def _pct(x: float | None) -> str:
    return f"{x:+.2%}" if x is not None else "—"


def _check(sc: str, name: str, golden_s: str, actual_s: str, tol_s: str,
           ok: bool) -> dict:
    return {"sc": sc, "name": name, "golden": golden_s, "actual": actual_s,
            "tol": tol_s, "ok": ok}


def run_validate(run_five: Path, run_four: Path) -> list[dict]:
    ev5 = load_events(run_five)
    ev4 = load_events(run_four)
    checks: list[dict] = []

    lock = {r["bucket"]: r for r in agg_lock_buckets(ev5, "tiger")}
    for bucket, g_n, g_gap, g_again in _G_LOCK:
        r = lock[bucket]
        checks.append(_check("SC-2", f"鎖板 {bucket} n", str(g_n), str(r["n"]), "±5%",
                             _within_rel(r["n"], g_n, _TOL_N)))
        checks.append(_check("SC-2", f"鎖板 {bucket} med gap", _pct(g_gap),
                             _pct(r["med_gap"]), "±0.5pp",
                             _within_pp(r["med_gap"], g_gap, _TOL_GAP)))
        checks.append(_check("SC-2", f"鎖板 {bucket} 續鎖", _pct(g_again),
                             _pct(r["again_rate"]), "±1pp",
                             _within_pp(r["again_rate"], g_again, _TOL_AGAIN)))

    v = agg_violent(ev5, "tiger")
    vio, nat = v["violent"], v["natural_early"]
    direction = (nat["again_rate"] or 0) > (vio["again_rate"] or 1)
    checks.append(_check("SC-3", "violent med gap", "+6.20%", _pct(vio["med_gap"]),
                         "±3pp", _within_pp(vio["med_gap"], 0.062, _TOL_SC3)))
    checks.append(_check("SC-3", "violent 續鎖", "+3.30%", _pct(vio["again_rate"]),
                         "±3pp", _within_pp(vio["again_rate"], 0.033, _TOL_SC3)))
    checks.append(_check("SC-3", "natural_early 續鎖", "+18.30%",
                         _pct(nat["again_rate"]), "±3pp,且 natural≫violent",
                         _within_pp(nat["again_rate"], 0.183, _TOL_SC3) and direction))

    queue = {r["bucket"]: r for r in agg_queue(ev5, "tiger")}
    checks.append(_check("SC-4", "早盤鎖 >=40% med gap", "+6.00%",
                         _pct(queue[">=40%"]["med_gap"]), "±0.5pp",
                         _within_pp(queue[">=40%"]["med_gap"], 0.060, _TOL_GAP)))
    checks.append(_check("SC-4", "早盤鎖 >=40% 續鎖", "+13.20%",
                         _pct(queue[">=40%"]["again_rate"]), "±1pp",
                         _within_pp(queue[">=40%"]["again_rate"], 0.132, _TOL_AGAIN)))
    checks.append(_check("SC-4", "早盤鎖 <15% 續鎖", "+0.00%",
                         _pct(queue["<15%"]["again_rate"]), "±1pp",
                         _within_pp(queue["<15%"]["again_rate"], 0.0, _TOL_AGAIN)))

    gap = {r["bucket"]: r for r in agg_gap_buckets(ev4, "tiger")}
    for bucket, g_n, g_e, g_again in _G_GAP:
        r = gap[bucket]
        checks.append(_check("SC-5", f"gap {bucket} n", str(g_n), str(r["n"]), "±5%",
                             _within_rel(r["n"], g_n, _TOL_N)))
        checks.append(_check("SC-5", f"gap {bucket} E[開→收]", _pct(g_e),
                             _pct(r["mean_open_to_close"]), "±0.5pp",
                             _within_pp(r["mean_open_to_close"], g_e, _TOL_GAP)))
        checks.append(_check("SC-5", f"gap {bucket} 續鎖", _pct(g_again),
                             _pct(r["again_rate"]), "±1pp",
                             _within_pp(r["again_rate"], g_again, _TOL_AGAIN)))

    auction = {r["bucket"]: r for r in agg_auction(ev5, "tiger", "dayvol")}
    for bucket, g_gap in _G_AUCTION:
        checks.append(_check("SC-6", f"競價 {bucket} med gap", _pct(g_gap),
                             _pct(auction[bucket]["med_gap"]), "±0.5pp",
                             _within_pp(auction[bucket]["med_gap"], g_gap, _TOL_GAP)))
    return checks


def format_validate(checks: list[dict]) -> str:
    lines = ["| SC | 項目 | golden | actual | 容忍 | 結果 |", "|---|---|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['sc']} | {c['name']} | {c['golden']} | {c['actual']} "
                     f"| {c['tol']} | {'PASS' if c['ok'] else '**FAIL**'} |")
    n_fail = sum(1 for c in checks if not c["ok"])
    lines.append(f"\n{len(checks) - n_fail}/{len(checks)} PASS")
    return "\n".join(lines)
```

`cli.py` 加:

```python
    p_val = sub.add_parser("validate", help="replay 彙總 vs evidence golden")
    p_val.add_argument("--run-five", type=Path, default=Path("out/five_tigers"))
    p_val.add_argument("--run-four", type=Path, default=Path("out/four_tigers"))
    p_val.add_argument("--out", type=Path, default=None)
```

```python
    if args.command == "validate":
        from copycat.replay.validate import format_validate, run_validate
        checks = run_validate(args.run_five, args.run_four)
        text = format_validate(checks)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        sys.stdout.write(text + "\n")
        return 0 if all(c["ok"] for c in checks) else 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/replay/test_validate.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/replay/validate.py copycat/cli.py tests/replay/test_validate.py
git commit -m "feat(replay): validate — evidence golden characterization gate(SC-2~SC-6)"
```

---

### Task 13: 兩份 run 並排(compare)

**Files:**
- Create: `copycat/replay/compare.py`
- Modify: `copycat/cli.py`(加 `compare` subcommand)
- Test: `tests/replay/test_compare.py`

**Interfaces:**
- Consumes: `load_events` / `agg_lock_buckets` / `agg_gap_buckets`(Task 11)
- Produces:
  - `write_compare(run_a: Path, run_b: Path, out: Path) -> Path`:tiger cohort 的鎖板時間表與 gap 分桶表並排(A / B / Δ 欄;Δ = B − A,med gap 與續鎖率),寫 markdown
  - CLI `compare RUN_A RUN_B [--out PATH]`(預設 `out/compare.md`)
- 用途:調 strategy config 前後對照(spec §1「比較與實驗是一級功能」)。

- [ ] **Step 1: Write the failing test**

`tests/replay/test_compare.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.compare import write_compare
from tests.replay.test_report import _event


def _mk_run(path: Path, gap: float) -> Path:
    path.mkdir(parents=True)
    with (path / "events.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_event("3-7%", gap, 0.01, True), ensure_ascii=False) + "\n")
    return path


def test_write_compare(tmp_path: Path) -> None:
    a = _mk_run(tmp_path / "a", 0.05)
    b = _mk_run(tmp_path / "b", 0.03)
    out = write_compare(a, b, tmp_path / "cmp.md")
    text = out.read_text(encoding="utf-8")
    assert "Δ" in text and "a" in text and "b" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/replay/test_compare.py -q`
Expected: FAIL(module 不存在)

- [ ] **Step 3: Write implementation**

`copycat/replay/compare.py`:

```python
"""兩份 replay run 並排對照(調 config 前後的實驗工具)."""
from __future__ import annotations

from pathlib import Path

from copycat.replay.report import agg_gap_buckets, agg_lock_buckets, load_events


def _pct(x: float | None) -> str:
    return f"{x:+.2%}" if x is not None else "—"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "—"
    return f"{b - a:+.2%}"


def _side_by_side(name: str, rows_a: list[dict], rows_b: list[dict],
                  value_keys: list[tuple[str, str]]) -> list[str]:
    lines = [f"\n## {name}\n"]
    headers = ["bucket", "n(A)", "n(B)"]
    for _, label in value_keys:
        headers += [f"{label}(A)", f"{label}(B)", f"Δ{label}"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    b_map = {r["bucket"]: r for r in rows_b}
    for ra in rows_a:
        rb = b_map.get(ra["bucket"], {})
        cells = [ra["bucket"], str(ra["n"]), str(rb.get("n", "—"))]
        for key, _ in value_keys:
            cells += [_pct(ra.get(key)), _pct(rb.get(key)), _delta(ra.get(key), rb.get(key))]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_compare(run_a: Path, run_b: Path, out: Path) -> Path:
    ev_a, ev_b = load_events(run_a), load_events(run_b)
    lines = [f"# Compare: A={run_a.name} vs B={run_b.name}\n"]
    lines += _side_by_side("鎖板時間 × T+1(tiger)",
                           agg_lock_buckets(ev_a, "tiger"), agg_lock_buckets(ev_b, "tiger"),
                           [("med_gap", "med gap"), ("again_rate", "續鎖")])
    lines += _side_by_side("T+1 gap 分桶(tiger)",
                           agg_gap_buckets(ev_a, "tiger"), agg_gap_buckets(ev_b, "tiger"),
                           [("mean_open_to_close", "E[開→收]"), ("again_rate", "續鎖")])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
```

`cli.py` 加:

```python
    p_cmp = sub.add_parser("compare", help="兩份 replay run 並排對照")
    p_cmp.add_argument("run_a", type=Path)
    p_cmp.add_argument("run_b", type=Path)
    p_cmp.add_argument("--out", type=Path, default=Path("out/compare.md"))
```

```python
    if args.command == "compare":
        from copycat.replay.compare import write_compare
        out = write_compare(args.run_a, args.run_b, args.out)
        sys.stdout.write(f"對照表 → {out}\n")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/replay/test_compare.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```powershell
git add copycat/replay/compare.py copycat/cli.py tests/replay/test_compare.py
git commit -m "feat(replay): compare — 兩份 run 並排對照(config 實驗工具)"
```

---

### Task 14: 全量 characterization run + SC 核對 + 文件收尾

**Files:**
- Modify: `CLAUDE.md`(§1 啟動&驗證表、§0 目錄結構)
- Create: `docs/evidence/replay-validation-<執行日期>.md`(validate 輸出存證)

前置:Task 6 Step 5 的全量匯入已完成(`data/` 就緒)。

- [ ] **Step 1: 全量 replay(兩份 watchlist)**

```powershell
.venv\Scripts\python -m copycat replay --watchlist watchlists/four_tigers.json
.venv\Scripts\python -m copycat replay --watchlist watchlists/five_tigers.json
```
Expected: `out/four_tigers/` 與 `out/five_tigers/` 各含 events.jsonl + meta.json + summary.md。檢查 meta:five_tigers 的 n_tiger ≈ 1029、four_tigers ≈ 850-1029 間(9600-only 事件變 excluded)、missing 數與 manifest 一致。

- [ ] **Step 2: 跑 validate(SC-1~SC-6 核對)**

```powershell
.venv\Scripts\python -m copycat validate --out docs/evidence/replay-validation-2026-07-07.md
```
Expected: 全 PASS(exit 0)。

**SC-1 核對(同步做)**:讀 `out/five_tigers/meta.json`,`(n_tiger − missing_t) / n_tiger ≥ 99%`(已知 12 個停牌 stock-day 為預期缺漏),且 `data/manifest.json` 的 `missing_t_1k` 清單與 meta 數字一致。缺漏清單附進存證檔。

**若有 FAIL:走 systematic-debugging,依序查這些已知定義差異(不是放寬容忍度):**
1. **事件集差異**:golden n=1023 = 「有 T 日 1K 且收盤鎖住」的五虎關聯事件;若 n 差超標,先對 `intraday_features.csv`(neigui 種子目錄)diff 事件 keys,找出哪些事件被多算/漏算。
2. **gap 來源**:golden 的 gap 來自事件 CSV(日線 open);引擎用 1K 首根 open。若 med gap 系統性偏移,抽 10 個事件比對兩者差值。
3. **again 定義**:golden `t1_again_limitup` vs 我們的 limitup_all set membership — 同源(寬鬆 ≥9.95%),理論上一致;不一致代表 events.csv t1_date 推導有誤。
4. **SC-3(violent_pull)**:1K 近似 vs tick 定義,容忍度已放 3pp;若方向都不對(natural ≯ violent),檢查 violent 窗的 px0 取法(研究 tick 版取窗內第一筆成交價,我們取窗內第一根 open)。
5. 修不過 3 次 → 停,回報(全域鐵則 F)。

- [ ] **Step 3: 全套件回歸 + 型別 + lint**

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check copycat tests
.venv\Scripts\python -m pyright
```
Expected: 全綠 / 0 errors。

- [ ] **Step 4: 更新 CLAUDE.md**

§1 表格填入:

```markdown
| 用途 | 指令 | 工作目錄 |
|------|------|---------|
| 測試 | `.venv\Scripts\python -m pytest -q` | repo root |
| Lint / 型別 | `.venv\Scripts\python -m ruff check copycat tests` + `.venv\Scripts\python -m pyright` | repo root |
| 種子匯入(一次性) | `.venv\Scripts\python -m copycat import-neigui --src C:\side-project\neigui\backend\data\research\five-tigers` | repo root |
| Replay | `.venv\Scripts\python -m copycat replay --watchlist watchlists/four_tigers.json` | repo root |
| Golden 驗證 gate | `.venv\Scripts\python -m copycat validate` | repo root |
```

並註明:完成前 gate = pytest + ruff + pyright + `copycat validate` 全 PASS。§0 目錄結構 `(待補)` 區塊填入 File Structure 的實際樹(copycat/ package 一層即可)。

- [ ] **Step 5: 存證 + 最終 commit**

```powershell
git add CLAUDE.md docs/evidence/replay-validation-2026-07-07.md
git commit -m "chore(replay): 全量 characterization 驗證存證 + CLAUDE.md gate 表"
```

Expected: validate 存證檔含全部 PASS 表格(對應全域鐵則 D:完成必附證據)。

---

## 已知風險與對策(執行者必讀)

- **Golden 對數是本計畫最大不確定性**(Task 14 Step 2)。容忍度是 spec 定的,不是建議值;不達標 = 查根因,已列五個優先嫌疑。修 3 次不過就停下回報。
- **全量匯入吃記憶體/時間**:k1_control.jsonl 271MB 逐行處理(streaming),不要整檔 `json.load`;實測若 import 超過 10 分鐘,檢查是不是把 JSONL 整個讀進記憶體。
- **`tests/replay/conftest.py` import 了 `tests/data/test_import_neigui` 的 fixture helpers**:pytest 需要 `tests/` 各層有 `__init__.py` 才能跨檔 import,或改用 `pythonpath = ["."]`(pyproject `[tool.pytest.ini_options]` 加 `pythonpath = ["."]`,建議後者)。
- **Windows 編碼**:所有檔案 IO 一律顯式 `encoding="utf-8"`(計畫內 code 已照做);PowerShell 輸出中文若亂碼不影響檔案內容。
- **明確不在本計畫的 spec 項目**(後續迭代加,不是遺漏):融資券/當沖比等日線輔助特徵匯入(`margin.csv` / `daytrading.csv`,策略迭代需要時在 EventContext 加欄)、tick 匯入與 tick 級訊號、Phase 1 縮池、決策樹輸出、盤中 live 餵食器。






