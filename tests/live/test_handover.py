from __future__ import annotations

from copycat.live.aggregate import ChainAggregator
from copycat.live.handover import HandoverBuffer, run_handover
from copycat.live.models import OptionContract, SeriesInfo, Tick

C44000 = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44000", cp="C", strike_millipts=44_000_000)
SERIES = SeriesInfo(series_id="TX4.202607", name="TX4 202607", expiry="202607", contracts=(C44000,))


def tick(*, price: int, qty: int, cum: int | None = None, t: int = 1) -> Tick:
    return Tick(
        symbol=C44000.symbol,
        precise_time=t,
        price_millipts=price,
        qty=qty,
        bid_millipts=price - 1_000,
        ask_millipts=price,
        cum_volume=cum,
    )


def totals(agg: ChainAggregator) -> dict:
    return agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")["totals"]


class TestHandoverBuffer:
    def test_append_within_cap(self) -> None:
        buf = HandoverBuffer(cap=2)
        assert buf.append(tick(price=100_000, qty=1, cum=1)) is True
        assert buf.append(tick(price=100_000, qty=1, cum=2)) is True

    def test_append_overflow_returns_false(self) -> None:
        buf = HandoverBuffer(cap=1)
        assert buf.append(tick(price=100_000, qty=1, cum=1)) is True
        assert buf.append(tick(price=100_000, qty=1, cum=2)) is False


class TestRunHandover:
    def test_live_first_then_backfill_no_false_drop(self) -> None:
        """訂閱先行:buffer 已有 live tick,回補灌入後 flush 不誤刪新資料。"""
        agg = ChainAggregator([C44000])
        buf = HandoverBuffer()
        # live 先到:cum 5(與回補重疊)與 cum 6(回補後新成交)
        buf.append(tick(price=100_000, qty=5, cum=5, t=10))
        buf.append(tick(price=100_000, qty=1, cum=6, t=11))
        backfill = [
            tick(price=100_000, qty=3, t=1),
            tick(price=100_000, qty=2, t=2),
        ]  # 重建 cum = 5
        run_handover(agg, backfill, buf)
        t = totals(agg)
        # 回補 5 口(外盤)+ flush 只放行 cum 6 那筆 1 口;cum 5 重疊被丟
        assert t["call_net_qty"] == 6
        assert t["ticks"] == 3

    def test_flush_respects_rebuilt_cum_per_symbol(self) -> None:
        agg = ChainAggregator([C44000])
        buf = HandoverBuffer()
        buf.append(tick(price=100_000, qty=5, cum=4, t=10))  # ≤ 重建值 5 → 丟
        run_handover(agg, [tick(price=100_000, qty=5, t=1)], buf)
        assert totals(agg)["call_net_qty"] == 5

    def test_empty_backfill_flushes_all(self) -> None:
        agg = ChainAggregator([C44000])
        buf = HandoverBuffer()
        buf.append(tick(price=100_000, qty=2, cum=2, t=10))
        run_handover(agg, [], buf)
        assert totals(agg)["call_net_qty"] == 2
