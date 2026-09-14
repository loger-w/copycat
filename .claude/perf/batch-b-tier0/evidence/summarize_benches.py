"""把 out_{before,after}_*.json 壓成一張 before / after 對照表(verification.md 用)。"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def main() -> None:
    b, a = load("out_before_01.json"), load("out_after_01.json")
    for key in ("tc4_collect_history_ms", "river_collect_1k_ms"):
        print(
            f"01 {key}: p50 {b[key]['p50']} -> {a[key]['p50']} | p90 {b[key]['p90']} -> {a[key]['p90']}"
            f" | mean {b[key]['mean']} -> {a[key]['mean']} (ready_dist={a['ready_dist']}, timer_1ms={a['timer_1ms']})"
        )
    b, a = load("out_before_02.json"), load("out_after_02.json")
    for rb, ra in zip(b["rows"], a["rows"]):
        print(
            f"02 window {rb['window_len']}: p50 {rb['per_tick_us']['p50']} -> {ra['per_tick_us']['p50']} us"
        )
    b, a = load("out_before_04.json"), load("out_after_04.json")
    print(
        f"04 push+corr p50 {b['per_second_total_ms_p50']} -> {a['per_second_total_ms_p50']} ms"
        f" (push {a['push_ms']['p50']}, corr {a['correlations_ms']['p50']}, corr p90 {a['correlations_ms']['p90']});"
        f" drift {a['drift']}"
    )
    b, a = load("out_before_05.json"), load("out_after_05.json")
    print(
        f"05 append p50 {b['append_us']['p50']} -> {a['append_us']['p50']} us | p90 {b['append_us']['p90']} -> {a['append_us']['p90']}"
    )
    b, a = load("out_before_06.json"), load("out_after_06.json")
    for key in ("positions_us", "orders_us", "fills_us"):
        print(f"06 {key}: p50 {b[key]['p50']} -> {a[key]['p50']}")
    b, a = load("out_before_09.json"), load("out_after_09.json")
    print(f"09 no_latch p50 {b['no_latch_us']['p50']} -> {a['no_latch_us']['p50']} us")
    b, a = load("out_before_11.json"), load("out_after_11.json")
    print(
        f"11 snapshot sha same={b['snapshot_sha256'] == a['snapshot_sha256']} delta same={b['delta_sha256'] == a['delta_sha256']}"
        f" snapshot key types {b['snapshot_minute_key_types']} -> {a['snapshot_minute_key_types']}"
        f" | in-memory {b['in_memory_minute_key_types']} -> {a['in_memory_minute_key_types']}"
    )
    for name in sorted(HERE.glob("out_bench_03_*.json")):
        d = load(name.name)
        print(
            f"03/07 {name.stem[13:]}: switch={d['switchinterval']} thr={d['cpu_threads']}"
            f" all p50 {d['all']['p50']} p90 {d['all']['p90']} p99 {d['all']['p99']} | after3s p50 {d['after_3s']['p50']}"
            f" | per10s {d['per_10s_p50']} | worker {d.get('worker_units_per_s')}"
        )


if __name__ == "__main__":
    main()
