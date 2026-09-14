"""1-1 江波圖 snapshot 的 wire 位元組:int 分鐘鍵改 str(m) 前後,starlette send_json 輸出必須逐位元相同。

同一組 push / apply_backfill 餵進 RiverState,以 starlette `send_json` 同款 `json.dumps` 參數
(ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"))序列化 snapshot 與 delta,
印 sha256 + 內部鍵型別;before(主樹)與 after(worktree)各跑一次,sha 相等 = wire 不變。
用法:python check_11_river_wire.py [--repo <root>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys


def dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from copycat.live.river_state import RiverState

    keys = ["TXF", "ES", "NQ"]
    s = RiverState(keys, base="TXF")
    day = ("20260915", "day")
    s.push("TXF", 8 * 60 + 46, 45_600_000, day)  # 08:46 終點標記 = 日盤首分
    s.push("TXF", 8 * 60 + 47, 45_610_000, day)
    s.push("ES", 8 * 60 + 46, 7_600_000, day)
    s.push("ES", 9 * 60 + 30, 7_610_000, day)
    s.apply_backfill("NQ", [(8 * 60 + 50, 29_200_000), (9 * 60 + 0, 29_210_000)], day)
    s.push("TXF", 13 * 60 + 45, 45_700_000, day)
    labels = {"TXF": "台指", "ES": "標普", "NQ": "納指"}
    snap = s.snapshot(labels, 42)
    delta = s.delta(43)
    snap_txt = dumps(snap)
    delta_txt = dumps(delta)
    key_types = sorted({type(k).__name__ for leg in snap["legs"].values() for k in leg["minutes"]})
    memory_types = sorted({type(k).__name__ for m in s._minutes.values() for k in m})
    print(
        json.dumps(
            {
                "repo": a.repo,
                "snapshot_sha256": hashlib.sha256(snap_txt.encode()).hexdigest(),
                "delta_sha256": hashlib.sha256(delta_txt.encode()).hexdigest(),
                "snapshot_minute_key_types": key_types,
                "in_memory_minute_key_types": memory_types,
                "snapshot_legs_TXF": snap["legs"]["TXF"],
                "snapshot_len": len(snap_txt),
            },
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
