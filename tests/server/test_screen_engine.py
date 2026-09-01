"""screen engine 的跨模組常數 parity(review B1)。

引擎行為(排程 / 補跑 / 落檔 / 寫群組)依 #173 議定 seam 不另測 —— 演算法測試在
`tests/test_screening.py`、群組寫入在 `tests/server/test_watchlist_service.py`。
"""

from __future__ import annotations

from copycat.server import breadth_engine, screen_engine


def test_daily_min_rows_parity_with_breadth() -> None:
    """單日全市場列數守門與 breadth 同值:兩邊守的是同一個上游(TaiwanStockPrice 分頁
    截斷),漂開的症狀是一邊當髒資料重試、另一邊照收 → 篩選候選無聲少一截。"""
    assert screen_engine._DAILY_MIN_ROWS == breadth_engine._DAILY_MIN_ROWS
