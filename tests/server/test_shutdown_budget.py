"""關機預算三方同源(mod/shutdown-budget,review A1)。

`run.ps1` 的 graceful 窗、uvicorn 的 WS drain 上限、lifespan 反序 close 的最壞耗時,
三者過去各寫各的數字(run.ps1 寫死 15 s,只算一條 TC4 session 的一發 REQ);TC4 半死時
五條 session 的 close 加起來遠超過 15 s,`Stop-Tree` 硬殺落在退訂中途 —— 健康的 session
也被還原成殭屍(下一台開頭 ~60 s 零推播,正是 #105 要修的病)。

這裡釘的是**不等式**,不是某個數字:改任一邊的常數,別的邊沒跟上就紅。
"""

from __future__ import annotations

import queue
import re
import threading
from pathlib import Path
from typing import cast

import copycat.live.tc4 as tc4_mod
from copycat.capital.client import COM_JOIN_TIMEOUT_SECS, CapitalClient
from copycat.live.tc4 import DEFAULT_LOCK_TIMEOUT_SECS, TC4QuoteSource, close_worst_secs
from copycat.server import shutdown_budget as sb

_RUN_PS1 = Path(__file__).resolve().parents[2] / "run.ps1"


class TestSingleSessionBound:
    """`tc4.close_worst_secs()`:單條 session `close()` 可計段的上界 = 等 `_api_lock`(在途
    `Connect()` 吃滿一個 REQ timeout)+ max(REQ 路徑 send+recv 各撞一次 timeout, 毒鎖路徑
    `_req` 等鎖 + `_dispose` 再等鎖)。兩條路互斥(review round-1 SP1 修正:首版漏了
    `_req` 進門那把 `api.lock`)。"""

    def test_close_worst_covers_the_req_path(self) -> None:
        req = tc4_mod._REQ_TIMEOUT_MS / 1000
        assert close_worst_secs() >= req + 2 * req

    def test_close_worst_covers_the_poisoned_lock_path(self) -> None:
        req = tc4_mod._REQ_TIMEOUT_MS / 1000
        assert close_worst_secs() >= req + 2 * DEFAULT_LOCK_TIMEOUT_SECS

    def test_default_lock_timeout_is_the_budget_input(self) -> None:
        """建構子預設值必須就是預算吃的那個常數 —— 兩處各寫一個 12.0 就會靜默漂開。"""
        src = TC4QuoteSource(port="0", api=object(), session="sess-1")
        assert src._lock_timeout == DEFAULT_LOCK_TIMEOUT_SECS


class TestLifespanBound:
    def test_lane_depth_is_the_corr_then_futures_chain(self) -> None:
        """關機路徑上最深的 lane = corr → futures 串鏈(corr 讀 futures.state(),
        app.py 的既有不變式);其餘 lane(index / stock / txo)各一條 session。"""
        assert sb.TC4_LANE_DEPTH == 2

    def test_lifespan_bound_covers_the_deepest_lane_and_the_com_join(self) -> None:
        assert sb.lifespan_close_worst_secs() >= (
            sb.TC4_LANE_DEPTH * close_worst_secs() + COM_JOIN_TIMEOUT_SECS
        )

    def test_run_grace_covers_ws_drain_and_lifespan(self) -> None:
        """run.ps1 拿到的數字必須蓋住 uvicorn 先等 WS 收攤那一段(review Spec 2 後半)。"""
        grace = sb.run_grace_secs()
        assert isinstance(grace, int), "PowerShell 端以 [int] 解析,不給小數"
        assert grace >= sb.WS_DRAIN_SECS + sb.lifespan_close_worst_secs()


class TestRunPs1Parity:
    """run.ps1 無自動化測試(PowerShell)—— 這裡只釘「數字從哪裡來」這件事。"""

    def test_run_ps1_reads_the_budget_from_python(self) -> None:
        text = _RUN_PS1.read_text(encoding="utf-8-sig")
        assert "from copycat.server.shutdown_budget import run_grace_secs" in text
        assert re.search(r"TimeoutSecs\s*=\s*\d", text) is None, (
            "run.ps1 仍寫死 graceful 上限(該從 shutdown_budget 讀)"
        )

    def test_run_ps1_keeps_the_utf8_bom(self) -> None:
        """檔頭註解的硬要求:Windows PowerShell 5.1 讀無 BOM 的 .ps1 會當 CP950,中文
        變亂碼且可能生出假引號讓整份 parse error(踩過)。任何工具改檔都可能吃掉 BOM。"""
        assert _RUN_PS1.read_bytes()[:3] == b"\xef\xbb\xbf"


class TestCapitalJoinTimeout:
    def test_close_joins_the_com_thread_with_the_budget_constant(self) -> None:
        joined: list[float | None] = []

        class _Thread:
            def join(self, timeout: float | None = None) -> None:
                joined.append(timeout)

        client = CapitalClient.__new__(CapitalClient)
        client._cmd_q = queue.Queue()
        client._thread = cast(threading.Thread, _Thread())
        client.close()
        assert joined == [COM_JOIN_TIMEOUT_SECS]
