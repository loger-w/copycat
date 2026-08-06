"""C-1/C-2 真實環境驗證側車 server(零 TC4 / 零 ZMQ / 零真憑證 — CLAUDE.md §8 紀律)。

- FakeQuoteSource + FakeCom CapitalClient(治具同 tests/server/test_capital_api.py)
- stkfut 對映表用 repo 版控真檔(copycat/stkfut_map.json,CDF/QFF 真實條目)
- /debug/seed-fut-order 以 OnNewData 治具種一筆 CDFI6 活單進 store
- /debug/com-sent 曝露 FakeCom 收到的呼叫(含 is_option flag)供 curl 端斷言 C-1
- port 8899(非 canonical),audit 落 scratchpad
"""

import sys
from pathlib import Path

WORKTREE = Path(r"C:\side-project\copycat\.claude\worktrees\feat-discord-watchlist")
sys.path.insert(0, str(WORKTREE))

from copycat.server.verify import neutralize_external_env

neutralize_external_env()  # 獨立起的 server 不經 tests/conftest,必須顯式中和(2026-08-06 紀律)

import tempfile

import uvicorn

import copycat.capital.factory as factory_mod
from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.app import create_app
from tests.capital.fake_com import FakeCom

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"

C23000 = OptionContract(symbol="TC.O.TWF.TXO.202607.C.23000", cp="C", strike_millipts=23_000_000)
SERIES = SeriesInfo(series_id="TXO.202607", name="TXO 202607", expiry="202607", contracts=(C23000,))


class FakeQuoteSource:
    # 形狀對照 tests/server/test_capital_api.py::FakeQuoteSource(該類定義在測試檔內,無法 import)
    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series, on_tick) -> None:
        return None

    def unsubscribe(self, series) -> None:
        return None

    def close(self) -> None:
        return None


def _fut_evt_raw(seq: str, contract: str = "CDFI6", qty: str = "2", price: str = "1175") -> str:
    # 欄位對照 tests/server/test_capital_api.py::_fut_evt_raw(市場別 TF)
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TF", "N", "N"
    arr[6], arr[8], arr[11], arr[20] = "BNR20", contract, price, qty
    return ",".join(arr)


audit_dir = Path(tempfile.mkdtemp(prefix="capital-side-audit-"))
com = FakeCom()
cap = CapitalClient(
    com,
    user_id="u",
    password="p",
    full_account="1234567890A",
    env="test",
    safety=SafetyConfig(order_enabled=True, max_qty=None, max_amount=None),
    audit_base=audit_dir,
)
factory_mod._client = cap
app = create_app(FakeQuoteSource(), throttle_secs=0.01)


@app.post("/debug/seed-fut-order")
def seed_fut_order(seq: str, contract: str = "CDFI6") -> dict:
    assert com.on_reply is not None
    com.on_reply(_fut_evt_raw(seq, contract=contract))
    return {"seeded": seq, "contract": contract}


@app.get("/debug/com-sent")
def com_sent() -> dict:
    return {"sent": [repr(t) for t in com.sent]}


print(f"audit_dir={audit_dir}", flush=True)
uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
