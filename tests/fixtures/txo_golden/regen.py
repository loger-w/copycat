"""Golden snapshot 重生腳本(design.md §2.3 DR-4;可重現的向下相容證據)。

讀同一份 ticks.jsonl 重跑 parse → ingest_backfill → snapshot(與 test_replay_golden.py
同一組建構常數),先驗「舊 key 子集 diff = 0」(移除 contracts 後與現行 golden 全等)
才覆寫 expected_snapshot.json;diff 非零 → 列出並 exit 1,不覆寫。

跑法(repo root):.venv\\Scripts\\python tests/fixtures/txo_golden/regen.py
報告走 logging(stdout handler;專案 §2 禁 print)。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from copycat.live.aggregate import ChainAggregator
from copycat.live.models import (
    OptionContract,
    SeriesInfo,
    parse_history_tick,
    parse_option_symbol,
)

FIXTURE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def build_snapshot() -> dict:
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
    assert len(ticks) == len(rows), "錄檔全數可 parse"
    agg.ingest_backfill(ticks)
    return agg.snapshot(series=series, status="replay", accumulated_from="08:45:00")


def main() -> int:
    # IR-3:JSON round-trip 正規化(tuple → list),同 golden 測試比對法
    snap: dict = json.loads(json.dumps(build_snapshot()))
    golden_path = FIXTURE_DIR / "expected_snapshot.json"
    old = json.loads(golden_path.read_text(encoding="utf-8"))

    # 兩側皆移除 contracts 再比對:golden 遷移後(已含 contracts)重跑仍 idempotent
    stripped = dict(snap)
    stripped.pop("contracts", None)
    old_stripped = dict(old)
    old_stripped.pop("contracts", None)
    if stripped != old_stripped:
        logger.error("old-keys diff: FOUND — 不覆寫,逐 key 列出:")
        for key in sorted(set(stripped) | set(old_stripped)):
            if stripped.get(key) != old_stripped.get(key):
                logger.error("  %s: old=%r new=%r", key, old_stripped.get(key), stripped.get(key))
        return 1

    logger.info("old-keys diff: NONE(移除 contracts 後與現行 golden 全等)")
    golden_path.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    logger.info("golden 已覆寫:%s", golden_path)
    logger.info("contracts 筆數:%d", len(snap["contracts"]))
    for row in snap["contracts"][:3]:
        logger.info("  抽核樣本:%s", row)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    sys.exit(main())
