"""0-6 `/api/capital/positions` route 的序列化成本(n 列 → dict 列表),`asdict` vs 直讀欄位。

直接 await route coroutine(`capital_positions` / `capital_orders` / `capital_fills`),
request 以 SimpleNamespace 替身餵 `app.state.capital.store.*()`;每次 await 量 µs。
用法:python bench_06_asdict.py [--repo <root>] [--n 400] [--iters 300]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from types import SimpleNamespace


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--iters", type=int, default=300)
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from copycat.capital.models import FillRecord, OrderRecord, Position
    from copycat.server import capital_api

    positions = [
        Position(
            market="sec",
            stock_no=str(2330 + i),
            qty=3,
            name="台積電",
            avg_price=1085.5,
            kind="cash",
            pnl_base=1234.5,
            pnl_base_price=1090.0,
            pnl_cost=325650.0,
            avg_source="broker",
            today_qty=1,
        )
        for i in range(a.n)
    ]
    orders = [
        OrderRecord(
            seq_no=f"{i:013d}",
            stock_no=str(2330 + i),
            name="台積電",
            market="TS",
            buy_sell="B",
            flag_label="現股",
            book_no="X",
            status_raw="N",
            status_label="委託成功",
            price=1085.0,
            avg_fill_price=None,
            order_qty=1,
            filled_qty=0,
            unit="張",
        )
        for i in range(a.n)
    ]
    fill_fields = {f.name for f in FillRecord.__dataclass_fields__.values()}
    fill_kw = {
        "seq_no": "0",
        "stock_no": "2330",
        "buy_sell": "B",
        "flag_label": "現股",
        "price": 1085.0,
        "qty": 1,
    }
    for name in fill_fields - set(fill_kw):
        fill_kw[name] = None
    fills = []
    for i in range(a.n):
        kw = dict(fill_kw)
        kw["seq_no"] = f"{i:013d}"
        try:
            fills.append(FillRecord(**kw))
        except TypeError:
            fills = []
            break

    store = SimpleNamespace(
        positions=lambda: positions, orders=lambda: orders, fills=lambda: fills
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(capital=SimpleNamespace(store=store))))

    async def bench(fn) -> dict:
        xs: list[float] = []
        for _ in range(a.iters):
            t0 = time.perf_counter_ns()
            await fn(request)
            xs.append((time.perf_counter_ns() - t0) / 1000)
        return {"p50": round(pct(xs, 0.5), 1), "p90": round(pct(xs, 0.9), 1)}

    async def run() -> dict:
        out = {
            "positions_us": await bench(capital_api.capital_positions),
            "orders_us": await bench(capital_api.capital_orders),
        }
        if fills:
            out["fills_us"] = await bench(capital_api.capital_fills)
        return out

    res = asyncio.run(run())
    print(json.dumps({"repo": a.repo, "n": a.n, "iters": a.iters, **res}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
