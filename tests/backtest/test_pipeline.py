"""管線 end-to-end(SC-6 determinism 錨點):合成小宇宙 → features → search → 報告."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from copycat.backtest.config import BacktestConfig
from copycat.backtest.pipeline import run_features, run_search
from copycat.data.models import Bar1K
from copycat.data.store import write_bars

_PRICE_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]


def _dates(n: int) -> list[str]:
    out = []
    m, d = 1, 1
    for _ in range(n):
        out.append(f"2026-{m:02d}-{d:02d}")
        d += 1
        if d > 28:
            m, d = m + 1, 1
    return out


def _bar(m: int, o: float, h: float, lo: float, c: float, v: float = 10.0) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=v,
        up_volume=v / 2,
        down_volume=v / 2,
        unch_volume=0.0,
    )


_DS = _dates(70)
_EVENT_IDX = (45, 60)  # train(2026-02)、test(2026-03)


def _write_universe(tmp_path: Path) -> tuple[Path, Path, Path]:
    data = tmp_path / "data"
    (data / "daily").mkdir(parents=True)
    (data / "events").mkdir(parents=True)
    rows = []
    for sid, ev_close, ev_spread in (("1001", 110.0, 10.0), ("3001", 105.0, 5.0)):
        for i, d in enumerate(_DS):
            close, spread = (ev_close, ev_spread) if i in _EVENT_IDX else (100.0, 0.0)
            o = 112.0 if i - 1 in _EVENT_IDX else 100.0  # T+1 open = 112(E1 出場價)
            rows.append(
                dict(
                    zip(
                        _PRICE_FIELDS,
                        [sid, d, str(o), str(close), "99", str(close), str(spread), "100"],
                    )
                )
            )
    with (data / "daily" / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PRICE_FIELDS)
        w.writeheader()
        w.writerows(rows)
    with (data / "events" / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
        for i in _EVENT_IDX:
            w.writerow({"stock_id": "1001", "date": _DS[i], "close": "110.0"})
    with (data / "events" / "events.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "stock_id",
                "date",
                "stock_name",
                "limitup_close",
                "t1_date",
                "source",
                "broker_ids",
            ],
        )
        w.writeheader()
        for i in _EVENT_IDX:
            w.writerow(
                {
                    "stock_id": "1001",
                    "date": _DS[i],
                    "stock_name": "",
                    "limitup_close": "110.0",
                    "t1_date": _DS[i + 1],
                    "source": "control",
                    "broker_ids": "",
                }
            )
    with (data / "events" / "near_miss.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date"])
        w.writeheader()
        for i in _EVENT_IDX:
            w.writerow({"stock_id": "3001", "date": _DS[i]})
    # 1K:1001 觸發後鎖死;3001 觸發後回落
    for i in _EVENT_IDX:
        write_bars(
            data,
            "1001",
            _DS[i],
            [_bar(10, 106.0, 108.2, 104.0, 108.0)]
            + [_bar(11 + j, 110.0, 110.0, 110.0, 110.0) for j in range(4)],
        )
        write_bars(
            data,
            "3001",
            _DS[i],
            [
                _bar(10, 106.0, 108.2, 104.0, 108.0),
                _bar(11, 108.0, 108.0, 106.5, 107.0),
                _bar(12, 107.0, 107.2, 106.0, 106.5),
            ],
        )
    core = tmp_path / "core.json"
    aux = tmp_path / "aux.json"
    core.write_text(
        json.dumps({"name": "core", "members": [{"broker_id": "779c"}]}), encoding="utf-8"
    )
    aux.write_text(
        json.dumps({"name": "aux", "members": [{"broker_id": "9600"}]}), encoding="utf-8"
    )
    return data, core, aux


def _cfg(**kw: object) -> BacktestConfig:
    base: dict[str, object] = {
        "theta_grid": (0.08, 0.081),
        "anchor_thetas": (0.08,),
        "s1_stall_bars": (2,),
        "s1_outer_max": (-1.0,),
        "s2_swing_lookback": (5,),
        "s2_buffer": (0.0,),
        "s3_trail": (0.02,),
        "s4_fixed": (0.03,),
        "ga_pop": 8,
        "ga_generations": 2,
        "ga_seeds": (1,),
        "ga_max_conditions": 2,
        "quantile_probs": (0.5,),
        "support_weighted_min": 1.0,
        "support_raw_min": 1,
        "split_date": "2026-03-01",
    }
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def test_pipeline_end_to_end_and_determinism(tmp_path: Path) -> None:
    data, core, aux = _write_universe(tmp_path)
    out = tmp_path / "out"
    cfg = _cfg()

    run_features(data, out, cfg, core, aux)
    feats = out / "features_theta0.080.csv"
    assert feats.exists() and (out / "features_theta0.081.csv").exists()
    with feats.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4  # 兩檔 × 兩日全數觸發
    for col in (
        "stock_id",
        "date",
        "group",
        "weight",
        "prev_close",
        "limit_price",
        "t1_date",
        "t1_open",
        "trig_idx",
        "gap_open",
        "dist_ma20",
    ):
        assert col in rows[0], f"features CSV 缺欄: {col}"
    assert (out / "universe_counts.json").exists()

    report = run_search(data, out, cfg, "2026-07-07")
    assert report.name == "tday_join_ga_backtest_2026-07-07.md"
    rules_path = out / "rules_final.json"
    assert rules_path.exists() and (out / "outcomes_theta0.080.json").exists()

    # determinism:重跑 → rules 與報告 byte-identical(SC-6)
    first_rules = rules_path.read_bytes()
    first_report = report.read_bytes()
    report2 = run_search(data, out, cfg, "2026-07-07")
    assert rules_path.read_bytes() == first_rules
    assert report2.read_bytes() == first_report


def test_outcome_cache_invalidation(tmp_path: Path) -> None:
    data, core, aux = _write_universe(tmp_path)
    out = tmp_path / "out"
    cfg = _cfg()
    run_features(data, out, cfg, core, aux)
    run_search(data, out, cfg, "2026-07-07")
    cache = json.loads((out / "outcomes_theta0.080.json").read_text(encoding="utf-8"))
    h1 = cache["sim_hash"]
    # 改模擬相關參數 → hash 不符 → 重算(cache 檔更新為新 hash)
    cfg2 = _cfg(intraday_tax=0.003)
    run_search(data, out, cfg2, "2026-07-07")
    cache2 = json.loads((out / "outcomes_theta0.080.json").read_text(encoding="utf-8"))
    assert cache2["sim_hash"] != h1
