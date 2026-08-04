from __future__ import annotations

import json
import random
from pathlib import Path

from copycat.live.aggregate import ChainAggregator
from copycat.live.models import (
    OptionContract,
    SeriesInfo,
    parse_history_tick,
    parse_option_symbol,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "txo_golden"


def test_replay_golden_snapshot_locked() -> None:
    """SC-5:spike 真實 tick 錄檔(2026-07-17 TX4 鏈 ATM±5)→ 引擎 → snapshot 與 golden 全等。

    釘住聚合鏈全路徑(parse → ingest_backfill → payoff → snapshot),防未來重構漂移。
    """
    rows = [json.loads(line) for line in (FIXTURE_DIR / "ticks.jsonl").open(encoding="utf-8")]
    symbols = sorted({r["symbol"] for r in rows})
    contracts: list[OptionContract] = []
    for s in symbols:
        parsed = parse_option_symbol(s)
        assert parsed is not None, s
        _prod, _expiry, cp, strike = parsed
        contracts.append(OptionContract(symbol=s, cp=cp, strike_millipts=strike * 1000))
    series = SeriesInfo(
        series_id="TX4.202607",
        name="TX4 202607 golden",
        expiry="202607",
        contracts=tuple(contracts),
    )

    agg = ChainAggregator(contracts)
    ticks = [t for r in rows if (t := parse_history_tick(r["symbol"], r["row"])) is not None]
    assert len(ticks) == len(rows)  # 錄檔全數可 parse
    agg.ingest_backfill(ticks)
    snap = agg.snapshot(series=series, status="replay", accumulated_from="08:45:00")

    expected = json.loads((FIXTURE_DIR / "expected_snapshot.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(snap)) == expected


def test_last_price_matches_ticks_jsonl() -> None:
    """SC-1 的獨立驗證力:**不吃 golden**,直接從 ticks.jsonl 重算每檔時序最後成交價。

    `regen.py` 的自檢是把兩側 contracts 整段 pop 掉再比對 → contracts 區塊無條件覆寫,
    重生後的 golden 對 last_price 的**值**零約束(self-fulfilling)。這條測試從原始錄檔
    獨立算答案,golden 被覆寫後仍然成立。

    兩側刻意**異構**(review S-3 / T-1):
    - expected 側只用 `QryIndex` 單鍵排序,不複製 aggregator 的 (precise_time, seq) 雙鍵
      —— 同構的話兩邊一起錯會互相印證。單鍵成立的依據:QryIndex 於單一 symbol 內唯一
      遞增(1679 列實查零例外)。
    - actual 側輸入先 **shuffle**(固定種子)再 `ingest_backfill`,把「錄檔本身大致有序」
      這個免費答案拿掉 —— 否則排序鍵寫錯(例如漏掉第二鍵 seq)兩側會同時退化成檔序而
      一起綠。實測:拿掉 seq 第二鍵的 mutation 會 deterministic 紅在 C.45500。

    依賴的資料前提(1679 列全查,零例外;未來換錄檔要重驗):
    1. `PreciseTime` = `FilledTime` × 10⁶ + µs → 兩個時間欄同序,排序鍵擇一皆可。
    2. 回補窗是**單一盤別、單一 UTC 日** → 「數值最大 = 時序最後」成立。
       ⚠ 若未來放寬成跨盤別回補(日盤 + 夜盤同批),HHMMSS 會繞回,
       last_price 會**靜默**取到舊盤別的價 —— 那時這條測試的前提要一併重審。
    """
    rows = [json.loads(line) for line in (FIXTURE_DIR / "ticks.jsonl").open(encoding="utf-8")]
    # 獨立算法:全域按 QryIndex 升冪掃,每 symbol 最後寫入者即該檔時序最後一筆
    expected_last: dict[str, float] = {}
    for r in sorted(rows, key=lambda x: int(x["row"]["QryIndex"])):
        expected_last[r["symbol"]] = float(r["row"]["TradingPrice"])
    assert len(expected_last) == 15  # 錄檔涵蓋 15 檔(全部有成交 → 全部會出現在 contracts)

    contracts: list[OptionContract] = []
    for s in sorted(expected_last):
        parsed = parse_option_symbol(s)
        assert parsed is not None, s
        _prod, _expiry, cp, strike = parsed
        contracts.append(OptionContract(symbol=s, cp=cp, strike_millipts=strike * 1000))
    series = SeriesInfo(
        series_id="TX4.202607",
        name="TX4 202607 golden",
        expiry="202607",
        contracts=tuple(contracts),
    )
    agg = ChainAggregator(contracts)
    ticks = [t for r in rows if (t := parse_history_tick(r["symbol"], r["row"])) is not None]
    random.Random(0).shuffle(ticks)  # 排序責任全歸 ingest_backfill(固定種子 → 可重現)
    agg.ingest_backfill(ticks)
    snap = agg.snapshot(series=series, status="replay", accumulated_from="08:45:00")

    assert {row["symbol"]: row["last_price"] for row in snap["contracts"]} == expected_last
