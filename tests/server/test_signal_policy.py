"""政策層(spec #192 T3)主 seam:接線層 on_tick 端到端。

沿 `test_signal_hub` 的 harness(fake publish / daily_bars / Discord sender / tmp 資料目錄)
再加 fake `peers_fn`(行情快照)與 `groups_fn`(自選群組);餵一段掃單簇 tick 序列,
看吐出來的 WS 訊息、jsonl 列與 Discord 文字。不 mock 內部協作者、不測私有方法。

價位帶 50.0 元(檔距 0.1):`_fire` 先餵 10:00:00.000 的回看基準 50_000,再兩個同毫秒群
(10:01:10.100 / 10:01:30.500)→ 掃單簇事件落在 10:01:30.500、成交價 50_400、60 s 漲幅 +0.8%。
自己的較前收由 `_state(ref=…)` 控:ref 50_000 → +0.8%;48_500 → +3.917…%;47_000 → +7.23…%。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from copycat.live.stock_state import StockDayState
from copycat.server.signal_hub import (
    format_policy_group_text,
    format_signal_group_text,
    format_signal_text,
)
from copycat.stock_watchlist import Group
from tests.server.test_signal_hub import (
    _DATE,
    _SIGNAL_KEYS,
    _Clock,
    _Harness,
    _Watch,
    _rule,
    _state,
    _sweep_group,
    _tick,
    _write_rules,
)

_POLICY_KEYS = _SIGNAL_KEYS | {
    "policy",
    "first_of_day",
    "late",
    "tod",
    "sweep",
    "self",
    "groups",
    "screen_member",
    "peers",
    "peers_up",
    "peer_max",
    "leader",
    "peer_touched",
    "t1_open",
    "t1_date",
    "t2_open",
    "t2_date",
    # 事件日收盤 / 最高(2026-09-07 整體 review F-31 拍板:回填 worker 順手補,對帳算「放到尾盤」
    # 與鎖死不必另抓日 K);初值 null,與 t1/t2 同一趟補
    "d_close",
    "d_high",
}
_SWEEP_RULE_ID = "r-1-000"
# 治具宣告成 `Group`(review F-37):`Group` 加必填鍵時治具跟著紅,呼叫點也不必壓 type: ignore
_MEM: Group = {"name": "記憶體", "codes": ["2330", "2344", "2408"]}
_SCREEN: Group = {"name": "盤前篩選", "codes": ["2330", "6715"]}
_ALL_IN: Group = {"name": "ALL IN", "codes": ["2330", "2317"]}


def _peer(
    name: str,
    chg: float | None,
    *,
    touched: bool | None = False,
    locked: bool | None = False,
) -> dict[str, Any]:
    """引擎 `policy_quotes()` 一檔的形狀(hub 只讀 name / chg_pct / touched_upper / locked_up)。"""
    return {
        "name": name,
        "price": None,
        "ref": None,
        "upper": None,
        "chg_pct": chg,
        "high": None,
        "touched_upper": touched,
        "locked_up": locked,
    }


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


async def _boot(
    tmp_path: Path,
    clock: _Clock,
    *,
    groups: list[Group] | None = None,
    peers: dict[str, dict[str, Any]] | None = None,
    codes: list[str] | None = None,
    sweep_notify: bool = False,
    **cfg: Any,
) -> tuple[_Harness, _Watch]:
    _write_rules(
        tmp_path,
        [
            _rule(
                "sweep_cluster",
                _SWEEP_RULE_ID,
                name="掃單簇",
                notify_discord=sweep_notify,
                cooldown_secs=60,
            )
        ],
    )
    wl = _Watch(groups=groups or [], peers=peers or {})
    h = _Harness(tmp_path, clock, wl=wl, **cfg)
    h.attach_bot()
    await h.hub.start()
    h.hub.on_watchlist(codes or ["2330", "2344", "2408", "2317", "6715"])
    await h.settle()
    return h, wl


def _fire(
    h: _Harness,
    st: StockDayState,
    *,
    code: str = "2330",
    base: str = "10:00:00.000",
    t1: str = "10:01:10.100",
    t2: str = "10:01:30.500",
) -> None:
    """一顆掃單簇事件:回看基準 + 兩個同毫秒群(第二群第三筆發訊,價 50_400)。"""
    h.hub.on_tick(code, _tick(50_000, code=code, time=base, ask=50_000), st)
    _sweep_group(h, st, t1, [50_000, 50_100, 50_200], ask=50_000, code=code)
    _sweep_group(h, st, t2, [50_200, 50_300, 50_400], ask=50_200, code=code, qty=2)


def _fmt(secs: float) -> str:
    """秒數 → `HH:MM:SS.fff`(毫秒整數 divmod,review F-36:`ss:06.3f` 在 59.9995 進位會印 `60.000`)。"""
    ms = round(secs * 1000)
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"


def _policies(h: _Harness) -> list[str]:
    return [m["policy"] for m in h.published if m["kind"] == "policy"]


class TestPolicyHits:
    async def test_p_hit_full_row_schema(self, tmp_path: Path, clock: _Clock) -> None:
        """P:同伴 ≥3% 為 0、自己 <6%、族群沒人鎖過 → 一列 kind=policy,全部欄位齊。"""
        h, wl = await _boot(
            tmp_path,
            clock,
            groups=[_MEM],
            peers={"2344": _peer("華邦電", 1.0), "2408": _peer("南亞科", -0.5)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert [m["kind"] for m in h.published] == ["sweep_cluster", "policy"]
            raw, msg = h.published
            assert set(msg) == _POLICY_KEYS
            assert msg["type"] == "signal"
            assert msg["kind"] == "policy" and msg["policy"] == "P"
            assert msg["id"] == f"{_DATE}-{_SWEEP_RULE_ID}-2330-policy-P-10:01:30.500"
            assert msg["id"] != raw["id"]
            assert msg["rule_id"] == _SWEEP_RULE_ID and msg["rule_name"] == "掃單簇"
            assert msg["code"] == "2330" and msg["name"] == "台積電"
            assert msg["price"] == 50_400 and msg["time"] == "10:01:30"
            assert msg["levels"] == [] and msg["direction"] is None
            assert msg["pct"] == pytest.approx(0.8)
            assert msg["touch_count"] == 1
            assert msg["notify"] is True
            assert msg["first_of_day"] is True and msg["late"] is False
            assert msg["tod"] == "0930"
            assert msg["sweep"] == {"n30": 2, "levels": 2, "qty": 6, "up_pct": pytest.approx(0.8)}
            assert msg["self"] == {
                "chg_pct": pytest.approx(0.8),
                "to_limit_pct": pytest.approx((55_000 - 50_400) / 50_400 * 100),
                "touched_upper": False,
                "locked_up": False,
            }
            assert msg["groups"] == ["記憶體"]
            assert msg["screen_member"] is False
            assert msg["peers"] == [
                {
                    "code": "2344",
                    "name": "華邦電",
                    "chg_pct": 1.0,
                    "touched_upper": False,
                    "locked_up": False,
                },
                {
                    "code": "2408",
                    "name": "南亞科",
                    "chg_pct": -0.5,
                    "touched_upper": False,
                    "locked_up": False,
                },
            ]
            assert msg["peers_up"] == 0
            assert msg["peer_max"] == {"code": "2344", "name": "華邦電", "chg_pct": 1.0}
            assert msg["leader"] is False  # 0.8 < 1.0
            assert msg["peer_touched"] is False
            assert [msg[k] for k in ("t1_open", "t1_date", "t2_open", "t2_date")] == [None] * 4
            # jsonl 同形 + trade_date;raw 掃單簇列另一列(quiet)
            rows = h.rows()
            assert [r["kind"] for r in rows] == ["sweep_cluster", "policy"]
            assert set(rows[1]) == _POLICY_KEYS | {"trade_date"}
            assert rows[1]["trade_date"] == _DATE
            assert rows[0]["notify"] is False and rows[1]["notify"] is True
            # 政策評估零 IO:peers_fn 只在掃單簇事件時被叫(一次)
            assert wl.peers_calls == 1
        finally:
            await h.hub.close()

    async def test_peers_fn_not_called_for_other_kinds(self, tmp_path: Path, clock: _Clock) -> None:
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000")])
        wl = _Watch(groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        h = _Harness(tmp_path, clock, wl=wl)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2344"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert [m["kind"] for m in h.published] == ["cdp_cross"]
            assert wl.peers_calls == 0
        finally:
            await h.hub.close()

    async def test_b_a_and_b_b_when_leader_and_peer_up(self, tmp_path: Path, clock: _Clock) -> None:
        """自己最強(+3.92% ≥ 同伴最大 3.0)、同伴 ≥3% 有一檔、<6%、沒人鎖過 → B-a 與 B-b 各一列。"""
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM],
            peers={"2344": _peer("華邦電", 3.0), "2408": _peer("南亞科", 0.2)},
        )
        try:
            _fire(h, _state(ref=48_500, upper=55_000))
            await h.settle()
            assert _policies(h) == ["B-a", "B-b"]
            by = {m["policy"]: m for m in h.published if m["kind"] == "policy"}
            assert by["B-a"]["leader"] is True and by["B-a"]["peers_up"] == 1
            assert by["B-a"]["id"].endswith("-policy-B-a-10:01:30.500")
            assert by["B-b"]["id"].endswith("-policy-B-b-10:01:30.500")
            assert len({m["id"] for m in h.published}) == 3
        finally:
            await h.hub.close()

    async def test_self_at_or_above_max_chg_only_b_b(self, tmp_path: Path, clock: _Clock) -> None:
        """自己 ≥6% → P / B-a / S 不評,B-b 仍評(它不看 <6%)。"""
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM, _SCREEN],
            peers={"2344": _peer("華邦電", 3.0)},
        )
        try:
            _fire(h, _state(ref=47_000, upper=55_000))  # +7.23%
            await h.settle()
            assert _policies(h) == ["B-b"]
        finally:
            await h.hub.close()

    async def test_not_leader_no_p_or_b(self, tmp_path: Path, clock: _Clock) -> None:
        """同伴已動(5.0 ≥ 3)且自己非最強 → P(同伴 ≥3% ≠ 0)與 B(非最強)都不命中。"""
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 5.0)})
        try:
            _fire(h, _state(ref=48_500, upper=55_000))
            await h.settle()
            assert _policies(h) == []
            assert [m["kind"] for m in h.published] == ["sweep_cluster"]  # raw 列照記
        finally:
            await h.hub.close()

    async def test_peer_touched_upper_blocks_p_and_b(self, tmp_path: Path, clock: _Clock) -> None:
        """族群今天有人鎖過 → P / B 都不評;S 不看族群,照命中。"""
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM, _SCREEN],
            peers={"2344": _peer("華邦電", 0.5, touched=True)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert _policies(h) == ["S"]
            s = next(m for m in h.published if m["kind"] == "policy")
            assert s["peer_touched"] is True and s["groups"] == ["記憶體"]
        finally:
            await h.hub.close()

    async def test_ungrouped_code_evaluates_only_s(self, tmp_path: Path, clock: _Clock) -> None:
        """零組(未分組 / 只在 ALL IN)→ 沒有同伴 → P / B 不評;是盤前篩選成員 → S。"""
        h, wl = await _boot(
            tmp_path,
            clock,
            groups=[_ALL_IN, _SCREEN],
            peers={"2317": _peer("鴻海", 4.0), "6715": _peer("嘉基", 9.0, touched=True)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert _policies(h) == ["S"]
            s = next(m for m in h.published if m["kind"] == "policy")
            assert s["groups"] == [] and s["screen_member"] is True
            assert s["peers"] == [] and s["peers_up"] == 0 and s["peer_max"] is None
            assert s["leader"] is False and s["peer_touched"] is False
            # 盤前篩選群組恆不算族群:6715 鎖過也不影響 S
        finally:
            await h.hub.close()

    async def test_screen_member_with_group_hits_s_and_p_independently(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM, _SCREEN],
            peers={"2344": _peer("華邦電", 1.0)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert _policies(h) == ["P", "S"]
            by = {m["policy"]: m for m in h.published if m["kind"] == "policy"}
            assert by["S"]["screen_member"] is True and by["S"]["groups"] == ["記憶體"]
            assert by["P"]["screen_member"] is True
        finally:
            await h.hub.close()

    async def test_no_peer_quotes_means_no_p_or_b(self, tmp_path: Path, clock: _Clock) -> None:
        """同伴都無報價(盤前 / 未訂閱)→ peers_quoted = 0 → P / B 不評;快照列仍記同伴。"""
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM, _SCREEN],
            peers={"2344": _peer("", None, touched=None, locked=None)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert _policies(h) == ["S"]
            s = next(m for m in h.published if m["kind"] == "policy")
            assert s["peers"] == [
                {
                    "code": "2344",
                    "name": "",
                    "chg_pct": None,
                    "touched_upper": None,
                    "locked_up": None,
                },
                {
                    "code": "2408",
                    "name": "",
                    "chg_pct": None,
                    "touched_upper": None,
                    "locked_up": None,
                },
            ]
            assert s["peer_max"] is None
        finally:
            await h.hub.close()

    async def test_missing_ref_evaluates_nothing_raw_row_still_recorded(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h, wl = await _boot(
            tmp_path, clock, groups=[_MEM, _SCREEN], peers={"2344": _peer("華邦電", 1.0)}
        )
        try:
            _fire(h, _state(ref=None, upper=None))
            await h.settle()
            assert [m["kind"] for m in h.published] == ["sweep_cluster"]
            assert [r["kind"] for r in h.rows()] == ["sweep_cluster"]
            assert wl.peers_calls == 0  # 參考價缺 → 連快照都不必取
        finally:
            await h.hub.close()

    async def test_self_touched_and_locked_flags(self, tmp_path: Path, clock: _Clock) -> None:
        """自己鎖過(當日高 ≥ 漲停)/ 當下鎖死(價 = 漲停且限價賣側空)進 `self`;
        自己 = 漲停時 to_limit = 0。P 不看自己鎖過(只看同伴)。"""
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            st = _state(ref=50_000, upper=50_400, locked_up=True)
            # harness 不經 engine `ingest`(hub 直吃 tick),當日高手動對齊「已觸及漲停價」
            st.high_milli = 50_400
            _fire(h, st)
            await h.settle()
            p = next(m for m in h.published if m["kind"] == "policy")
            assert p["policy"] == "P"
            assert p["self"] == {
                "chg_pct": pytest.approx(0.8),
                "to_limit_pct": pytest.approx(0.0),
                "touched_upper": True,
                "locked_up": True,
            }
        finally:
            await h.hub.close()


class TestGroupResolution:
    async def test_multi_group_union_dedup_and_one_warning(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        groups: list[Group] = [
            {"name": "記憶體", "codes": ["2330", "2344", "2408"]},
            {"name": "半導體", "codes": ["2317", "2330", "2344"]},
        ]
        peers = {
            "2344": _peer("華邦電", 1.0),
            "2408": _peer("南亞科", 0.5),
            "2317": _peer("鴻海", 0.1),
        }
        h, _ = await _boot(tmp_path, clock, groups=groups, peers=peers)
        try:
            with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
                _fire(h, _state(ref=50_000, upper=55_000))
                await h.settle()
                clock.advance(61)
                _fire(
                    h,
                    _state(ref=50_000, upper=55_000),
                    base="10:03:00.000",
                    t1="10:04:10.100",
                    t2="10:04:30.500",
                )
                await h.settle()
            ps = [m for m in h.published if m["kind"] == "policy"]
            assert len(ps) == 2
            assert ps[0]["groups"] == ["記憶體", "半導體"]
            assert [p["code"] for p in ps[0]["peers"]] == ["2344", "2408", "2317"]  # 聯集保序去重
            assert caplog.text.count("多個族群組") == 1  # 同檔同日只警告一次
            assert "2330" in caplog.text
        finally:
            await h.hub.close()

    async def test_exclude_groups_from_config(self, tmp_path: Path, clock: _Clock) -> None:
        """`policy_exclude_groups` 走設定:ALL IN(預設)與「觀察」都不算族群。"""
        groups: list[Group] = [
            {"name": "ALL IN", "codes": ["2330", "2317"]},
            {"name": "觀察", "codes": ["2330", "2408"]},
            {"name": "記憶體", "codes": ["2330", "2344"]},
        ]
        peers = {
            "2317": _peer("鴻海", 9.0, touched=True),
            "2408": _peer("南亞科", 9.0, touched=True),
            "2344": _peer("華邦電", 1.0),
        }
        h, _ = await _boot(
            tmp_path, clock, groups=groups, peers=peers, policy_exclude_groups=("ALL IN", "觀察")
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert _policies(h) == ["P"]
            p = h.published[-1]
            assert p["groups"] == ["記憶體"]
            assert [x["code"] for x in p["peers"]] == ["2344"]
        finally:
            await h.hub.close()

    async def test_default_exclude_is_all_in_only(self, tmp_path: Path, clock: _Clock) -> None:
        groups: list[Group] = [
            {"name": "ALL IN", "codes": ["2330", "2317"]},
            {"name": "觀察", "codes": ["2330", "2408"]},
        ]
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=groups,
            peers={"2317": _peer("鴻海", 9.0), "2408": _peer("南亞科", 1.0)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert _policies(h) == ["P"]
            assert h.published[-1]["groups"] == ["觀察"]
        finally:
            await h.hub.close()


class TestDailyCounting:
    async def test_second_hit_same_day_is_recorded_but_quiet(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            st = _state(ref=50_000, upper=55_000)
            _fire(h, st)
            await h.settle()
            clock.advance(61)
            _fire(h, st, base="10:03:00.000", t1="10:04:10.100", t2="10:04:30.500")
            await h.settle()
            ps = [m for m in h.published if m["kind"] == "policy"]
            assert [(p["touch_count"], p["first_of_day"], p["notify"]) for p in ps] == [
                (1, True, True),
                (2, False, False),
            ]
            rows = [r for r in h.rows() if r["kind"] == "policy"]
            assert len(rows) == 2 and rows[1]["notify"] is False
            assert len(h.bot) == 1  # 只推首筆
        finally:
            await h.hub.close()

    async def test_late_after_push_end_recorded_not_notified(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            _fire(
                h,
                _state(ref=50_000, upper=55_000),
                base="12:30:00.000",
                t1="12:31:10.100",
                t2="12:31:30.500",
            )
            await h.settle()
            p = h.published[-1]
            assert p["kind"] == "policy" and p["policy"] == "P"
            assert p["late"] is True and p["first_of_day"] is True and p["notify"] is False
            assert p["tod"] == "1200"
            assert h.bot == [] and [r["kind"] for r in h.rows()] == ["sweep_cluster", "policy"]
        finally:
            await h.hub.close()

    @pytest.mark.parametrize(
        ("t2", "tod", "late"),
        [
            ("09:05:30.500", "0900", False),
            ("09:10:00.000", "0910", False),
            ("09:29:59.999", "0910", False),
            ("09:30:00.000", "0930", False),
            ("10:29:59.999", "0930", False),
            ("10:30:00.000", "1030", False),
            ("11:59:59.999", "1030", False),
            ("12:00:00.000", "1200", False),
            ("12:30:00.000", "1200", False),  # 等於推播窗右界:不算 late
            ("12:30:00.001", "1200", True),
        ],
    )
    async def test_tod_buckets_and_late_boundary(
        self, tmp_path: Path, clock: _Clock, t2: str, tod: str, late: bool
    ) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            hh, mm, rest = t2.split(":")
            secs = int(hh) * 3600 + int(mm) * 60 + float(rest)
            t1 = _fmt(secs - 20)
            base = _fmt(secs - 90)
            _fire(h, _state(ref=50_000, upper=55_000), base=base, t1=t1, t2=t2)
            await h.settle()
            p = h.published[-1]
            assert p["kind"] == "policy"  # 壞掉時是可讀的失敗,不是 KeyError(review F-36)
            assert (p["tod"], p["late"]) == (tod, late)
        finally:
            await h.hub.close()

    async def test_rollover_resets_first_of_day(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            # 換日(stage2):政策每日計數歸零、偵測器 reset_day —— 日別不換,讓同一組 tick
            # 可以原樣重播(換了日別 tick 會被 detector 的舊日 snapshot gate 擋掉,那是另一條契約)
            h.hub.on_rollover()
            await h.settle()
            clock.advance(61)
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            ps = [m for m in h.published if m["kind"] == "policy"]
            assert [(p["touch_count"], p["first_of_day"]) for p in ps] == [(1, True), (1, True)]
            assert len(h.bot) == 2  # 換日後首筆**再度推播**(review F-38)
        finally:
            await h.hub.close()

    async def test_drop_code_resets_count(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            h.hub.on_watchlist(["2344", "2408"])  # 2330 移出
            h.hub.on_watchlist(["2330", "2344", "2408"])  # 再加回
            await h.settle()
            clock.advance(61)
            _fire(
                h,
                _state(ref=50_000, upper=55_000),
                base="10:03:00.000",
                t1="10:04:10.100",
                t2="10:04:30.500",
            )
            await h.settle()
            ps = [m for m in h.published if m["kind"] == "policy"]
            assert [(p["touch_count"], p["first_of_day"]) for p in ps] == [(1, True), (1, True)]
            assert len(h.bot) == 2  # 移出再加回後首筆**再度推播**(review F-38)
        finally:
            await h.hub.close()


class TestPolicyDiscord:
    async def test_single_policy_four_line_card(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM],
            peers={"2344": _peer("華邦電", 1.0), "2408": _peer("南亞科", -0.5)},
        )
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert h.bot == [
                "🔔 **【P】** 台積電 2330｜50.40｜10:01:30\n"
                "掃單簇 2 掃・2 層・6 張・+0.80%\n"
                "族群 記憶體:同伴≥3% 0・最強 2344華邦電 +1.0%・鎖過 無\n"
                "較前收 +0.80%・距漲停 9.13%"
            ]
        finally:
            await h.hub.close()

    async def test_two_policies_same_tick_one_message(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(
            tmp_path,
            clock,
            groups=[_MEM],
            peers={"2344": _peer("華邦電", 3.0), "2408": _peer("南亞科", 0.2)},
        )
        try:
            _fire(h, _state(ref=48_500, upper=55_000))
            await h.settle()
            assert len(h.bot) == 1
            lines = h.bot[0].split("\n")
            assert len(lines) == 4
            assert lines[0] == "🔔 **【B-a・B-b】** 台積電 2330｜50.40｜10:01:30"
            assert lines[1] == "掃單簇 2 掃・2 層・6 張・+0.80%"
            assert lines[2] == "族群 記憶體:同伴≥3% 1・最強 2344華邦電 +3.0%・鎖過 無"
            assert lines[3] == "較前收 +3.92%(族群最強)・距漲停 9.13%"
        finally:
            await h.hub.close()

    async def test_s_without_group_third_line(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_SCREEN], peers={})
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert h.bot[0].split("\n")[0] == "🔔 **【S】** 台積電 2330｜50.40｜10:01:30"
            assert h.bot[0].split("\n")[2] == "盤前篩選名單・無族群濾網"
        finally:
            await h.hub.close()

    async def test_other_kind_same_tick_appended_to_first_line_no_group_suffix(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """同 tick 另有爆拉(規則通知開)→ 首行尾接既有文案;政策批次**不掛**同群摘要。"""
        _write_rules(
            tmp_path,
            [
                _rule(
                    "sweep_cluster",
                    _SWEEP_RULE_ID,
                    name="掃單簇",
                    notify_discord=False,
                    cooldown_secs=60,
                ),
                _rule(
                    "surge_crash", "r-1-001", name="爆拉", params={"pct": 0.5, "window_secs": 300}
                ),
            ],
        )
        wl = _Watch(
            groups=[_MEM],
            quotes={"2344": ("華邦電", 1.0), "2408": ("南亞科", -0.5)},
            peers={"2344": _peer("華邦電", 1.0), "2408": _peer("南亞科", -0.5)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2344", "2408"])
            await h.settle()
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            kinds = [m["kind"] for m in h.published]
            assert kinds.count("surge") == 1 and kinds.count("policy") == 1
            assert len(h.bot) == 1
            lines = h.bot[0].split("\n")
            # 爆拉在第二群第二筆(50_300,+0.6%)就達標,與政策列同一秒 → 合併進首行尾
            assert lines[0] == "🔔 **【P】** 台積電 2330｜50.40｜10:01:30｜爆拉 +0.60%"
            assert "同群" not in h.bot[0]
            assert len(lines) == 4
        finally:
            await h.hub.close()

    async def test_to_limit_dash_when_upper_missing(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        try:
            _fire(h, _state(ref=50_000, upper=None))
            await h.settle()
            p = h.published[-1]
            assert p["self"]["to_limit_pct"] is None and p["self"]["touched_upper"] is False
            assert h.bot[0].split("\n")[3] == "較前收 +0.80%・距漲停 -"
        finally:
            await h.hub.close()

    async def test_webhook_fallback_gets_same_card(self, tmp_path: Path, clock: _Clock) -> None:
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 1.0)})
        h.bot_ready = False
        try:
            _fire(h, _state(ref=50_000, upper=55_000))
            await h.settle()
            assert len(h.fallback) == 1 and h.fallback[0].startswith("🔔 **【P】**")
        finally:
            await h.hub.close()


class TestPolicyText:
    def test_kind_text_for_policy_row(self) -> None:
        """一般 kind 文案表也認得政策列:「政策 P」,與前端 `kindLabel` 逐字對齊。"""
        row = {
            "kind": "policy",
            "policy": "B-a",
            "code": "2330",
            "name": "台積電",
            "price": 50_400,
            "time": "10:01:30",
        }
        assert format_signal_text(row) == "🔔 政策 B-a｜台積電 2330｜50.40｜10:01:30"

    def test_policy_group_text_without_policy_rows_falls_back_to_plain_format(self) -> None:
        """對外函式自守「至少一列政策列」(review F-10):零政策列不炸 IndexError,退回一般批次文案。"""
        rows = [
            {
                "kind": "surge",
                "code": "2330",
                "name": "台積電",
                "price": 50_400,
                "time": "10:01:30",
                "pct": 0.6,
            }
        ]
        assert format_policy_group_text(rows, peer_up_pct=3.0) == format_signal_group_text(rows)


class TestPeersFnFailure:
    async def test_peers_fn_error_degrades_to_s_only_logs_once_and_resets_on_rollover(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """快照失敗(review F-33 補洞):同伴視為無報價 → P / B 不評、S 照評、raw 列照記;
        traceback 當日只印一次(同步熱路徑,逐 tick 印會自己變瓶頸),換日後再印一次。"""
        h, wl = await _boot(
            tmp_path, clock, groups=[_MEM, _SCREEN], peers={"2344": _peer("華邦電", 1.0)}
        )
        wl.peers_error = True
        try:
            with caplog.at_level(logging.ERROR, logger="copycat.server.signal_hub"):
                _fire(h, _state(ref=50_000, upper=55_000))
                await h.settle()
                assert _policies(h) == ["S"]  # 同伴健康時是 ["P", "S"]
                assert [r["kind"] for r in h.rows()] == ["sweep_cluster", "policy"]
                assert wl.peers_calls == 1
                clock.advance(61)
                _fire(
                    h,
                    _state(ref=50_000, upper=55_000),
                    base="10:03:00.000",
                    t1="10:04:10.100",
                    t2="10:04:30.500",
                )
                await h.settle()
                assert wl.peers_calls == 2  # 每顆事件照樣試讀(失敗不熔斷),只是不再印
                assert caplog.text.count("政策行情快照讀取失敗") == 1  # 當日一次
                h.hub.on_rollover()
                await h.settle()
                clock.advance(61)
                _fire(h, _state(ref=50_000, upper=55_000))
                await h.settle()
                assert caplog.text.count("政策行情快照讀取失敗") == 2  # 換日復位
            first = next(r for r in caplog.records if "政策行情快照" in r.getMessage())
            assert first.exc_info is not None  # 帶 traceback
        finally:
            await h.hub.close()


class TestReviewFollowups:
    """2026-09-07 整體 review(PR #199 + #200)收修:政策謂詞的三個界 + 守門 + 兩則 WARNING。

    三個界的補案數字(V2 實算):ref=47_547 → chg 6.000379 → round 6.0(恰等界);
    ref=48_932 → 3.000082 → 3.0(與同伴 3.0 平手);ref=48_933 → 2.997977 → round 後 3.0、
    不 round 是 2.998(round 兩把尺)。
    """

    async def test_chg_exactly_at_max_does_not_hit(self, tmp_path: Path, clock: _Clock) -> None:
        """`chg < max_chg_pct` 是嚴格小於:恰等於 6.00 → P / B-a / S 都不命中(review F-07)。"""
        h, _ = await _boot(
            tmp_path, clock, groups=[_MEM, _SCREEN], peers={"2344": _peer("華邦電", 1.0)}
        )
        try:
            _fire(h, _state(ref=47_547, upper=55_000))  # 50_400 / 47_547 → 6.0
            await h.settle()
            assert _policies(h) == []
        finally:
            await h.hub.close()

    async def test_leader_tie_counts_as_leader(self, tmp_path: Path, clock: _Clock) -> None:
        """自己 chg 與同伴最大 chg **平手**仍是族群最強(研究 `_leader = self_chg >= mx`;review F-08)。"""
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 3.0)})
        try:
            _fire(h, _state(ref=48_932, upper=55_000))  # chg 恰 3.0
            await h.settle()
            assert _policies(h) == ["B-a", "B-b"]
        finally:
            await h.hub.close()

    async def test_self_chg_rounded_to_two_places_same_ruler_as_peers(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """自己的 chg 先 round 2 再比(round-1 std F-01 的修正;review F-06 零回歸保護):
        2.997977 → 3.0 ≥ 同伴 3.0 → 最強;不 round 是 2.998 < 3.0 → 靜默少兩列。"""
        h, _ = await _boot(tmp_path, clock, groups=[_MEM], peers={"2344": _peer("華邦電", 3.0)})
        try:
            _fire(h, _state(ref=48_933, upper=55_000))
            await h.settle()
            assert _policies(h) == ["B-a", "B-b"]
            assert [m["self"]["chg_pct"] for m in h.published if m["kind"] == "policy"] == [3.0, 3.0]
        finally:
            await h.hub.close()

    async def test_zero_ref_evaluates_nothing_without_error_log(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """參考價 0(`to_milli_units("0")` 回 0 不是 None)→ 不評、raw 列照記、**零 ERROR**(review F-44:
        守門拿掉的失效樣態是 ZeroDivisionError 被 `_fanout` 傘吞,只斷零政策列殺不掉)。"""
        h, wl = await _boot(
            tmp_path, clock, groups=[_MEM, _SCREEN], peers={"2344": _peer("華邦電", 1.0)}
        )
        try:
            with caplog.at_level(logging.ERROR, logger="copycat.server.signal_hub"):
                _fire(h, _state(ref=0, upper=55_000))
                await h.settle()
            assert _policies(h) == []
            assert [m["kind"] for m in h.published] == ["sweep_cluster"]
            assert wl.peers_calls == 0
            assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
        finally:
            await h.hub.close()

    async def test_multi_group_warning_repeats_after_rollover(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """「一檔一天一次」的一天 = 換日復位(review F-45;與 `TestPeersFnFailure` 同形)。"""
        groups: list[Group] = [
            {"name": "記憶體", "codes": ["2330", "2344"]},
            {"name": "半導體", "codes": ["2330", "2408"]},
        ]
        peers = {"2344": _peer("華邦電", 1.0), "2408": _peer("南亞科", 0.5)}
        h, _ = await _boot(tmp_path, clock, groups=groups, peers=peers)
        try:
            with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
                _fire(h, _state(ref=50_000, upper=55_000))
                await h.settle()
                assert caplog.text.count("多個族群組") == 1
                h.hub.on_rollover()
                await h.settle()
                clock.advance(61)
                _fire(h, _state(ref=50_000, upper=55_000))
                await h.settle()
                assert caplog.text.count("多個族群組") == 2
        finally:
            await h.hub.close()

    async def test_exclude_group_name_without_match_warns_once(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """排除組名對不上任何自選群組 → 載入群組時 WARNING 一次(review F-03):user 把「ALL IN」
        改名而沒同步設定檔時,那組會靜默變族群(研究 §8.2:ALL IN 當族群 −1,471/筆)。同一組
        缺名重複載入不重複警告;組名補回來後再缺才再警告。"""
        _write_rules(tmp_path, [])
        wl = _Watch(groups=[_MEM])  # 沒有「ALL IN」這一組
        h = _Harness(tmp_path, clock, wl=wl)
        await h.hub.start()
        try:
            with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
                h.hub.on_watchlist(["2330", "2344", "2408"])
                await h.settle()
                hits = [r for r in caplog.records if "排除組名" in r.getMessage()]
                assert len(hits) == 1 and "ALL IN" in hits[0].getMessage()
                h.hub.on_watchlist(["2330", "2344", "2408", "2317"])  # 再載入一次,同一組缺名
                await h.settle()
                assert caplog.text.count("排除組名") == 1
                wl.groups = [_MEM, _ALL_IN]  # 組名補回來 → 不再缺
                h.hub.on_watchlist(["2330", "2344", "2408", "2317"])
                await h.settle()
                wl.groups = [_MEM]  # 又不見了 → 再警告一次
                h.hub.on_watchlist(["2330", "2344", "2408", "2317"])
                await h.settle()
                assert caplog.text.count("排除組名") == 2
        finally:
            await h.hub.close()

    async def test_peers_fn_failure_count_summarised_on_rollover(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """快照失敗第二次起不再印 traceback(F-09),但**換日時彙總當日失敗顆數**(review F-25):
        對帳時「P 沒發」是條件不成立還是快照壞掉,要看得出那天壞了幾顆。"""
        h, wl = await _boot(
            tmp_path, clock, groups=[_MEM, _SCREEN], peers={"2344": _peer("華邦電", 1.0)}
        )
        wl.peers_error = True
        try:
            with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
                _fire(h, _state(ref=50_000, upper=55_000))
                await h.settle()
                clock.advance(61)
                _fire(
                    h,
                    _state(ref=50_000, upper=55_000),
                    base="10:03:00.000",
                    t1="10:04:10.100",
                    t2="10:04:30.500",
                )
                await h.settle()
                assert wl.peers_calls == 2
                h.hub.on_rollover()
                await h.settle()
            summary = [r for r in caplog.records if "快照失敗共" in r.getMessage()]
            assert len(summary) == 1 and summary[0].levelname == "WARNING"
            assert "2 顆" in summary[0].getMessage()
        finally:
            await h.hub.close()
