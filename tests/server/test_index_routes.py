"""index routes 測試 — index-board SC-4 接線 + index-overlay SC-5."""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import copycat.server.ws as ws_mod
from copycat.server.app import create_app
from copycat.server.mis import OtcSnap
from copycat.server.overlay import compute_cdp
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeIndexSource, FakeStockSource, dbar
from tests.helpers.fake_txo import FakeTxoSource

#: `/ws/index` 在 quote 生效前最多容忍幾則 `p` None 的 loop 拍。**只防無界等待,不是契約**:
#: 撥 `_dirty` 的點不只回補完成 / MIS poll(watchdog / 分時自癒 / txf 價變 / 換日也會),常態 0–2 則;
#: 超過這個數仍是 None = 推播鏈真的壞了,不是順序問題
_WS_PRE_QUOTE_MAX = 5
#: 等「含 `p` 那則」的牆鐘預算(pr-135 F-01):`_WS_PRE_QUOTE_MAX` 只計 index 則,ping 不計 ——
#: 推播鏈迴歸(quote 進來但不撥 dirty)時迴圈只會一直拿到 ping,沒有這道預算就是 hang 不是紅。
#: `receive_json` 阻塞,預算靠 ping 喚醒才檢查得到(測試內把心跳調快);ping 也停 = relay 死,
#: 那是 test_ws_disconnect 的範圍。
_WS_QUOTE_DEADLINE_SECS = 3.0

#: 本檔的當日回補固定給一根分鐘 —— `/api/index/state` 與 `/ws/index` 都靠它斷言接線
_DAY_MINUTES = {"0901": 43_000_000}

#: overlay 用的日 K 治具:22 根(≥21)遞增收盤,`dbar` 的 h/l 各 ±1000。
#: 固定過去日期 —— 相對「今天」算的話,MA 的期望值會隨執行日漂掉。
_OVERLAY_DAILY = [
    dbar(f"2026-07-{d:02d}", 23_000_000 + i * 10_000) for i, d in enumerate(range(1, 23))
]
_LAST_CLOSE = 23_210_000  # = _OVERLAY_DAILY[-1]["c"]


def _mis() -> OtcSnap | None:
    return OtcSnap(p=359_800, ref=378_090, open=373_420, high=373_420, low=358_430, time="101610")


def make_client(index_source: FakeIndexSource | None) -> tuple[TestClient, FakeIndexSource | None]:
    app = create_app(
        FakeTxoSource(),
        index_source=index_source,
        index_mis_fetch=_mis,
        throttle_secs=0.01,
    )
    return BootedClient(app, raise_server_exceptions=False), index_source


class TestIndexState:
    def test_state_shape_200(self) -> None:
        client, fake = make_client(FakeIndexSource(day_minutes=_DAY_MINUTES))
        with client:
            r = client.get("/api/index/state")
            assert r.status_code == 200
            body = r.json()
            assert set(body) == {"trade_date", "twse", "otc", "txf"}
            assert body["twse"]["minutes"] == {"0901": 43_000_000}
            assert body["txf"] is None  # TXO runtime 無現貨 tick → None
        assert fake is not None and fake.closed is True  # lifespan finally close(IR6)

    def test_engine_absent_503(self) -> None:
        client, _ = make_client(None)
        with client:
            r = client.get("/api/index/state")
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "NOT_READY"

    def test_ws_rejects_handshake_when_engine_absent(self) -> None:
        # R4 N036:引擎缺席 → 握手前就拒(進場即拋);原本 accept 後才 close 且無測試
        client, _ = make_client(None)
        with client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/index"):
                    raise AssertionError("index 引擎缺席時握手不該成功")

    def test_ws_streams_index_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """連上後推一則 quote,WS 要收到 `twse.p` 已更新的 payload。

        `/ws/index` **沒有 seed 快照**(`index.stream()` 無 seed;relay 也不補),首則是
        `_broadcast_loop` 下一個 dirty 拍的 payload —— 但 client queue 註冊到 quote 被
        `_handle_quote` 處理之間,回補完成 / MIS poll 撥 dirty 的那一拍也會先發一則
        (`p` None)。首則就斷 `p` 是順序型 flake(08-27 全量 1/3135 紅);改成收到含 `p`
        的那則為止,quote 保證撥 dirty,所以有界迴圈必收得到。
        """
        monkeypatch.setattr(ws_mod, "WS_HEARTBEAT_SECS", 0.2)  # ping 只負責把 receive 叫醒
        client, fake = make_client(FakeIndexSource(day_minutes=_DAY_MINUTES))
        with client:
            assert fake is not None and fake.on_message is not None
            with client.websocket_connect("/ws/index") as ws:
                fake.on_message(
                    {
                        "Security": "IX0001",
                        "TradingPrice": "42039.92",
                        "ReferencePrice": "43634.19",
                        "HighPrice": "43221.93",
                        "LowPrice": "41815.78",
                        "FilledTime": "13015",
                    }
                )
                seen: list[int | None] = []
                deadline = time.monotonic() + _WS_QUOTE_DEADLINE_SECS
                while len(seen) <= _WS_PRE_QUOTE_MAX:
                    assert time.monotonic() < deadline, (
                        f"{_WS_QUOTE_DEADLINE_SECS} s 內沒等到含 p 的 index payload;已收 {seen}"
                    )
                    msg = ws.receive_json()
                    if msg["type"] == "ping":  # 心跳直送不經 queue,不算一則
                        continue
                    assert msg["type"] == "index"
                    seen.append(msg["twse"]["p"])
                    if seen[-1] is not None:
                        break
                assert seen and seen[-1] == 42_039_920, f"前 {len(seen)} 則 twse.p = {seen}"


class TestIndexOverlay:
    """`GET /api/index/overlay`(index-overlay SC-5)。

    形狀同 `/api/stock/overlay/{code}`,但日 K 走 index engine session 的
    `build_period`(鍵 `IX0001|L`)—— 與 market bars 日 K 同槽、與 stock session 的
    裸 `IX0001` 槽隔離(W-12 / W-14)。
    """

    def test_happy_returns_cdp_and_mas(self) -> None:
        client, fake = make_client(FakeIndexSource(daily_bars=_OVERLAY_DAILY))
        with client:
            r = client.get("/api/index/overlay")
            assert r.status_code == 200
            body = r.json()
            assert set(body) == {"cdp", "ma5", "ma20", "date"}
            # 口徑對 overlay.compute_cdp(重抄一份算式 = 兩邊各自漂移時測試照綠)
            assert body["cdp"] == compute_cdp(_LAST_CLOSE + 1000, _LAST_CLOSE - 1000, _LAST_CLOSE)
            assert body["ma5"] == 23_190_000
            assert body["ma20"] == 23_115_000
            assert body["date"] == "2026-07-22"
        assert fake is not None
        assert [c[1] for c in fake.calls] == ["D"], "日 K 必須向 index engine 問(W-7)"

    def test_tc4_down_returns_all_null_200(self) -> None:
        """bars 空(TC4 不可用)→ 200 全 null,不 5xx(edge case 1)。"""
        client, _ = make_client(FakeIndexSource(daily_bars=[], tag="unavailable"))
        with client:
            r = client.get("/api/index/overlay")
            assert r.status_code == 200
            assert r.json() == {"cdp": None, "ma5": None, "ma20": None, "date": None}

    def test_today_partial_bar_excluded(self) -> None:
        """盤中今日 partial 日 K 不得入計算(edge case 7)。"""
        today = f"{_dt.date.today():%Y-%m-%d}"
        client, _ = make_client(
            FakeIndexSource(daily_bars=[*_OVERLAY_DAILY, dbar(today, 99_000_000)])
        )
        with client:
            body = client.get("/api/index/overlay").json()
            assert body["date"] == "2026-07-22", "date 取最後一根**已完成** bar"
            assert body["ma5"] == 23_190_000, "今日 partial 混進 MA 會把值整個拉走"

    def test_second_call_hits_cache(self) -> None:
        """同日第二次呼叫不再打 bars_range(決策 3:日 bar 已在 bars_cache)。"""
        client, fake = make_client(FakeIndexSource(daily_bars=_OVERLAY_DAILY))
        with client:
            first = client.get("/api/index/overlay").json()
            assert fake is not None
            assert len(fake.calls) == 1
            second = client.get("/api/index/overlay").json()
            assert second == first
            assert len(fake.calls) == 1, "第二發應命中 bars_cache"

    def test_engine_absent_503(self) -> None:
        client, _ = make_client(None)
        with client:
            r = client.get("/api/index/overlay")
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "NOT_READY"

    def test_shares_daily_slot_with_market_bars(self) -> None:
        """R2-P0-1 的核心決策機驗:overlay 與 `/api/market/bars/TWSE?tf=D` **真共用**
        `IX0001|L` 槽 —— 同日兩端點只發一次 DK 取數。

        單看 overlay 自己那幾條,退化成「overlay 開了自己的獨立槽」照樣全綠(各抓各的、
        各自命中);只有跨端點的取數計數看得出來。順帶斷 market bars 拿到的是 overlay
        抓進來的那份(bars 非空 + tag 沿用),否則共用可能是「共用了一格空的」。
        """
        client, fake = make_client(FakeIndexSource(daily_bars=_OVERLAY_DAILY))
        with client:
            assert client.get("/api/index/overlay").status_code == 200
            assert fake is not None
            assert len(fake.calls) == 1
            r = client.get("/api/market/bars/TWSE?tf=D")
            assert r.status_code == 200
            body = r.json()
            assert body["bars"], "共用槽該回 overlay 已抓進來的日 K,不是空手"
            assert body["meta"]["source"] == "tc4_dk", "tag 也存在同一格(daily_tag_put)"
        assert len(fake.calls) == 1, "同日兩端點共用 IX0001|L → DK 取數只發一次"

    def test_does_not_pollute_stock_session_slot(self, tmp_path: Path) -> None:
        """W-12 / W-14:overlay 寫的是 `IX0001|L`,不得碰 stock session 的裸 `IX0001`。

        機驗方式 = 打完 overlay 後從 `/api/stock/bars/IX0001?tf=D`(走 `build_daily`
        的裸鍵)要日 K:若 overlay 汙染了那格,stock source 就一次都不會被問到,
        畫面上是「個股 K 線悄悄拿到了大盤 session 的資料」,零錯誤訊號。
        """
        stock = FakeStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=stock,
            index_source=FakeIndexSource(daily_bars=_OVERLAY_DAILY),
            index_mis_fetch=_mis,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        client = BootedClient(app, raise_server_exceptions=False)
        with client:
            assert client.get("/api/index/overlay").status_code == 200
            r = client.get("/api/stock/bars/IX0001?tf=D")
            assert r.status_code == 200
        assert [c[:2] for c in stock.bars_calls] == [("IX0001", "D")], (
            "stock session 的裸 IX0001 槽必須仍是空的(overlay 不得寫它)"
        )
