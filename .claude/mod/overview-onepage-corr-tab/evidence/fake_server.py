"""overview-onepage-corr-tab real-env 取證側車(零 TC4 / 零 ZMQ — ops-discipline)。port 8721(prod 未跑,vite proxy 寫死 8721)。

改自 `.claude/mod/index-overlay/evidence/fake_server.py`(fake 指數源 + 加速 MIS)+
`.claude/mod/overview-subtabs-breadth-colors/evidence/sidecar_server.py`(真 FinMind 四元組)。
用途:SC-1(corr tab)/ SC-3(1920/1536 一頁不捲 + 內捲 + sticky)/ SC-4(圖高隨容器)/
SC-5(家數帶實心)/ SC-6(騰落線紅綠)/ SC-7(斷點)截圖。

治具:
- 加權分時 fake(index-overlay 同款)+ 櫃買 MIS 加速灌入 → 兩張圖有線。
- 家數帶 / 漲跌停列表 = **真 FinMind**(閉包綁真 token;盤外拿到最近交易日全市場 rows,
  列表夠長才驗得到內捲與 sticky)。
- 騰落線:預先寫 `breadth-<today>.json`(engine 啟動 restore)—— 合成 270 分鐘、net 由正轉負
  再轉正,讓 SC-6 兩色都出現(真 08-14 序列全日同號驗不到綠段)。
- neutralize_external_env() 必在 create_app import 前;落檔隔離 data/market-sidecar-onepage/。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat")

import datetime as _dt
import json
import math
import pathlib
import threading
import time as _time

import uvicorn

# ⚠ 必須在 create_app 使用之前(ops-discipline:漏了會拿 .env 真憑證)
from copycat.server.verify import neutralize_external_env

neutralize_external_env()

from copycat.server import breadth_fetch  # noqa: E402
from copycat.server.app import create_app  # noqa: E402
from copycat.server.mis import OtcSnap  # noqa: E402
from tests.helpers.fake_sources import (  # noqa: E402
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"

env = pathlib.Path(r"C:\side-project\copycat\.env").read_text(encoding="utf-8-sig")
TOKEN = [ln.split("=", 1)[1].strip() for ln in env.splitlines() if ln.startswith("FINMIND_TOKEN")][0]

DATA_DIR = pathlib.Path(r"C:\side-project\copycat\data\market-sidecar-onepage")
DATA_DIR.mkdir(parents=True, exist_ok=True)

REF = 24_300_000
TODAY = _dt.date.today()


def _weekdays_back(n: int) -> list[_dt.date]:
    out: list[_dt.date] = []
    d = TODAY - _dt.timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= _dt.timedelta(days=1)
    return list(reversed(out))


def _daily_bars() -> list[dict]:
    days = _weekdays_back(25)
    bars: list[dict] = []
    for i, d in enumerate(days):
        c = 23_600_000 + int((24_300_000 - 23_600_000) * i / (len(days) - 1))
        bars.append({"t": f"{d:%Y-%m-%d}", "o": c, "h": c + 60_000, "l": c - 60_000, "c": c, "v": 10})
    bars[-1] = {"t": bars[-1]["t"], "o": 24_250_000, "h": 24_350_000, "l": 24_050_000, "c": 24_300_000, "v": 10}
    return bars


def _twse_minutes() -> dict[str, int]:
    out: dict[str, int] = {}
    start, end = 9 * 60, 13 * 60 + 30
    span = end - start
    for m in range(start + 1, end + 1):
        prog = (m - start) / span
        p = REF + int(60_000 * prog + 80_000 * math.sin(prog * math.pi * 1.3) + 12_000 * math.sin(m / 5.0))
        p = max(24_240_000, min(24_440_000, p))
        out[f"{m // 60:02d}{m % 60:02d}"] = p
    return out


TWSE_MIN = _twse_minutes()
TWSE_LAST = TWSE_MIN[max(TWSE_MIN)]

OTC_REF = 240_000
_otc_steps: list[OtcSnap] = []
_hi, _lo = OTC_REF, OTC_REF
for m in range(9 * 60, 13 * 60 + 31):
    prog = (m - 9 * 60) / (4.5 * 60)
    p = OTC_REF + int(3_000 * math.sin(prog * math.pi * 1.7) + 1_500 * prog + 600 * math.sin(m / 3.0))
    _hi, _lo = max(_hi, p), min(_lo, p)
    _otc_steps.append(
        OtcSnap(p=p, ref=OTC_REF, open=_otc_steps[0]["p"] if _otc_steps else p, high=_hi, low=_lo,
                time=f"{m // 60:02d}{m % 60:02d}30")
    )
_otc_lock = threading.Lock()
_otc_i = 0


def fake_mis_fetch() -> OtcSnap | None:
    global _otc_i
    with _otc_lock:
        snap = _otc_steps[min(_otc_i, len(_otc_steps) - 1)]
        _otc_i += 1
        return snap


index_src = FakeIndexSource(day_minutes=TWSE_MIN, tag="tc4_dk", daily_bars=_daily_bars())


def _push_loop() -> None:
    while True:
        _time.sleep(1.0)
        cb = index_src.on_message
        if cb is None:
            continue
        now_utc = _dt.datetime.now(_dt.timezone.utc)
        try:
            cb({
                "Security": "IX0001",
                "TradingPrice": f"{TWSE_LAST / 1000:.2f}",
                "ReferencePrice": f"{REF / 1000:.2f}",
                "HighPrice": "24440.00",
                "LowPrice": "24240.00",
                "FilledTime": f"{now_utc:%H%M%S}",
            })
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=_push_loop, daemon=True).start()


# ---- 騰落線合成序列(SC-6:net 由正 → 負 → 正)----
def _seed_breadth_series() -> None:
    series = []
    for m in range(9 * 60 + 1, 13 * 60 + 31):
        prog = (m - 9 * 60 - 1) / (4.5 * 60 - 1)
        net = int(260 * math.sin(prog * math.pi * 2.2) - 40)  # 正 → 負 → 正
        up = 900 + net // 2
        down = 900 - net // 2
        lu = 8 + int(6 * prog)
        ld = 3
        series.append({"t": f"{m // 60:02d}{m % 60:02d}", "twse": [lu, up, 130, down, ld], "tpex": [6, up // 2, 100, down // 2, 2]})
    payload = {"_version": 1, "trade_date": TODAY.isoformat(), "series": series}
    (DATA_DIR / f"breadth-{TODAY.isoformat()}.json").write_text(json.dumps(payload), encoding="utf-8")


# 檔案版本以 engine 常數為準
from copycat.server import breadth_engine as _be  # noqa: E402

_seed_breadth_series()
_p = DATA_DIR / f"breadth-{TODAY.isoformat()}.json"
_d = json.loads(_p.read_text(encoding="utf-8"))
_d["_version"] = _be._FILE_VERSION  # noqa: SLF001
_p.write_text(json.dumps(_d), encoding="utf-8")


def _snapshot(_token: str) -> list[dict]:
    return breadth_fetch.fetch_snapshot(TOKEN)


def _stock_info(_token: str) -> list[dict]:
    return breadth_fetch.fetch_stock_info(TOKEN)


def _disposition(_token: str, today: _dt.date) -> list[dict]:
    return breadth_fetch.fetch_disposition(TOKEN, today)


def _daily(_token: str, day: _dt.date) -> list[dict]:
    return breadth_fetch.fetch_daily_prices(TOKEN, day)


wl_path = DATA_DIR / "stock_watchlist.json"
if not wl_path.exists():
    wl_path.write_text(json.dumps({"codes": [], "groups": []}, ensure_ascii=False), encoding="utf-8")

app = create_app(
    stock_source=FakeStockSource(),
    index_source=index_src,
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    breadth_fetchers=(_snapshot, _stock_info, _disposition, _daily),
    breadth_data_dir=DATA_DIR,
    index_mis_fetch=fake_mis_fetch,
    stock_watchlist_path=wl_path,
)


def _accelerate_mis() -> None:
    while getattr(app.state, "index", None) is None:
        _time.sleep(0.2)
    app.state.index._poll = 0.02  # noqa: SLF001
    while _otc_i < len(_otc_steps):
        _time.sleep(0.5)
    app.state.index._poll = 5.0
    print("OTC minutes seeded", flush=True)


threading.Thread(target=_accelerate_mis, daemon=True).start()

uvicorn.run(app, host="127.0.0.1", port=8721, log_level="warning")
