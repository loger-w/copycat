"""screen engine 的跨模組常數 parity(review B1)+ compute() 資料完整性閘(review S3)。

排程 / 補跑 / 落檔 / 寫群組依 #173 議定 seam 不另測 —— 演算法測試在
`tests/test_screening.py`、群組寫入在 `tests/server/test_watchlist_service.py`。
`compute()` 的三道取數守門(日 K 回聲 / 空當沖名單 / 當沖回聲)是收修批新增的行為
分歧點,以 fake fetcher 釘住(零 IO;不屬排程豁免範圍)。
"""

from __future__ import annotations

import datetime as _dt
import re

import pytest

from copycat.server import breadth_engine, screen_engine
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.screen_engine import SCREEN_GROUP, ScreenEngine
from copycat.trading_calendar import WEEKEND_ONLY
from tests.helpers.frontend_source import read_frontend_source


def test_daily_min_rows_parity_with_breadth() -> None:
    """單日全市場列數守門與 breadth 同值:兩邊守的是同一個上游(TaiwanStockPrice 分頁
    截斷),漂開的症狀是一邊當髒資料重試、另一邊照收 → 篩選候選無聲少一截。"""
    assert screen_engine._DAILY_MIN_ROWS == breadth_engine._DAILY_MIN_ROWS


def test_screen_group_name_parity_with_frontend() -> None:
    """跨語言契約(CLAUDE.md §4「盤前篩選群組名」;mod/group-grid-ticks T5 #181):後端
    `SCREEN_GROUP` 是產生點(nightly 寫進自選的群組名),前端 `lib/constants.ts::SCREEN_GROUP_NAME`
    是群組檢視 pill 的**過濾鍵**。後端改名而前端沒跟 → 圖牆又列出 ~60 張卡,兩側各自的測試全綠,
    零錯誤訊號。同 `test_avg_source_parity_with_frontend` 姿態:直讀前端原始碼字面。"""
    text = read_frontend_source("lib/constants.ts")
    m = re.search(r'export const SCREEN_GROUP_NAME = "([^"]+)";', text)
    assert m, 'constants.ts 找不到 `export const SCREEN_GROUP_NAME = "...";` 字面'
    assert m.group(1) == SCREEN_GROUP


# ---------------------------------------------------------------------------
# compute() 資料完整性閘(review S3)—— fake fetcher、零 IO
# ---------------------------------------------------------------------------

_DAY = _dt.date(2026, 9, 1)  # 週二(交易日)


def _daily_rows(day: _dt.date, n: int = 5) -> list[dict]:
    return [
        {"stock_id": f"{1000 + i}", "date": day.isoformat(), "close": 100.0, "spread": 0.0}
        for i in range(n)
    ]


def _engine(
    daily: object,
    day_trading: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> ScreenEngine:
    monkeypatch.setattr(screen_engine, "_REQ_GAP_SECS", 0.0)
    # 列數守門降到 fixture 量級 —— 本組測的是回聲/空集合閘,不是列數閘(它有 parity 測試)
    monkeypatch.setattr(screen_engine, "_DAILY_MIN_ROWS", 1)
    return ScreenEngine(
        token="tok",
        calendar=WEEKEND_ONLY,
        daily_fetch=daily,  # type: ignore[arg-type]
        day_trading_fetch=day_trading,  # type: ignore[arg-type]
        disposition_fetch=lambda token, day: [],
        data_dir=tmp_path_factory.mktemp("screen"),
    )


async def test_daily_date_echo_mismatch_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """日 K 回聲不符(上游回錯日)必須炸成可重試錯誤 —— 靜默收下會把單日漲幅複利
    20 次算出全假名單(review F-07 的閘,S3 補錨)。"""
    wrong = _DAY - _dt.timedelta(days=30)
    eng = _engine(
        lambda token, day: _daily_rows(wrong),
        lambda token, day: [{"stock_id": "1234", "date": _DAY.isoformat()}],
        monkeypatch,
        tmp_path_factory,
    )
    with pytest.raises(BreadthFetchError, match="回聲不符"):
        await eng.compute(_DAY)


async def test_empty_day_trading_rows_raise_instead_of_wiping_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """當沖名單空 = 取數失敗重試,**不是**「全部候選非當沖」—— 後者會把群組清空還
    零訊號(review F-02 的空回應閘,S3 補錨)。"""
    eng = _engine(
        lambda token, day: _daily_rows(day),
        lambda token, day: [],
        monkeypatch,
        tmp_path_factory,
    )
    with pytest.raises(BreadthFetchError, match="當沖名單尚無資料"):
        await eng.compute(_DAY)


async def test_day_trading_date_echo_mismatch_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    wrong = (_DAY - _dt.timedelta(days=30)).isoformat()
    eng = _engine(
        lambda token, day: _daily_rows(day),
        lambda token, day: [{"stock_id": "1234", "date": wrong}],
        monkeypatch,
        tmp_path_factory,
    )
    with pytest.raises(BreadthFetchError, match="當沖名單資料日回聲不符"):
        await eng.compute(_DAY)
