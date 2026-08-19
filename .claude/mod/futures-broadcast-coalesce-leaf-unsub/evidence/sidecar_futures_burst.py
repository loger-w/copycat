"""SC-8 降級驗證用 sidecar(零 TC4 / 零 ZMQ — ops-discipline):fake futures source 高頻叢發推 quote。

用法:`.venv\\Scripts\\python .claude/mod/futures-broadcast-coalesce-leaf-unsub/evidence/sidecar_futures_burst.py [port=8723]`
再以 `evidence/sc8_measure.py <port>` 量:(1) 同 product 相鄰兩則 WS 訊息最小間隔 ≥ 95 ms(2) seq 連續(3) shape 不變。
fake 每 20 ms 對 TXF/MXF/TMF 各推一則(= 150 則/s 進引擎;before 語意下 WS 也會 150 則/s)。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat")

import datetime as _dt
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

# ⚠ 必須在 create_app 之前(ops-discipline:漏了會拿 .env 真憑證登入群益正式環境)
from copycat.server.verify import FakeTxoSource, neutralize_external_env

neutralize_external_env()

from copycat.capital import factory as capital_factory
from copycat.server.app import create_app
from tests.helpers.fake_sources import FakeFuturesSource


class _FakeCapital:
    def __init__(self) -> None:
        self.broadcast = None

    def set_broadcast(self, cb) -> None:
        self.broadcast = cb

    def start(self, loop) -> None:
        return None

    def close(self) -> None:
        return None


capital_factory.get_capital = lambda: _FakeCapital()  # type: ignore[assignment]


class BurstFuturesSource(FakeFuturesSource):
    """每 20 ms 對三檔各推一則(叢發),逼出 coalesce 指紋。"""

    _PX = {"TXF": 23_500, "MXF": 23_500, "TMF": 23_500}

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._n = 0

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        super().set_on_message(cb)
        if self._thread is None:
            self._thread = threading.Thread(target=self._push_loop, daemon=True)
            self._thread.start()

    def _push_loop(self) -> None:
        while not self._stop.wait(0.02):
            cb = self.on_message
            if cb is None:
                continue
            self._n += 1
            now_utc = _dt.datetime.now(_dt.timezone.utc)
            for prod in list(self.subscribed):
                px = self._PX.get(prod, 23_500) + (self._n % 5) - 2
                try:
                    cb(
                        {
                            "Symbol": f"TC.F.TWF.{prod}.HOT",
                            "SecurityName": "臺股期貨",
                            "EndDate": "20260916",
                            "TradingPrice": str(px),
                            "TradeQuantity": "2",
                            "TradeVolume": str(1000 + self._n),
                            "TradeDate": f"{now_utc:%Y%m%d}",
                            "PreciseTime": f"{now_utc:%H%M%S}000000",
                            "Bid": str(px - 1),
                            "BidVolume": "10",
                            "Ask": str(px),
                            "AskVolume": "12",
                            "ReferencePrice": "23400",
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass

    def close(self) -> None:
        self._stop.set()


tmp = Path(tempfile.mkdtemp(prefix="futures-coalesce-sidecar-"))
app = create_app(
    FakeTxoSource(),
    futures_source=BurstFuturesSource(),
    stock_watchlist_path=tmp / "watchlist.json",
)
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8723
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
