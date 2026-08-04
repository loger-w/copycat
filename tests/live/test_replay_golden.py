from __future__ import annotations

import json
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
    """
    rows = [json.loads(line) for line in (FIXTURE_DIR / "ticks.jsonl").open(encoding="utf-8")]
    # 獨立算法:全域按 (PreciseTime, QryIndex) 升冪掃,每 symbol 最後寫入者即時序最後一筆
    expected_last: dict[str, float] = {}
    for r in sorted(rows, key=lambda x: (int(x["row"]["PreciseTime"]), int(x["row"]["QryIndex"]))):
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
    agg.ingest_backfill(
        [t for r in rows if (t := parse_history_tick(r["symbol"], r["row"])) is not None]
    )
    snap = agg.snapshot(series=series, status="replay", accumulated_from="08:45:00")

    assert {row["symbol"]: row["last_price"] for row in snap["contracts"]} == expected_last
