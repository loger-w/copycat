"""個股即時訊號偵測狀態機(零 IO;design §3 — SC-1/2/3/4/6)。

四類訊號:CDP 五線穿越 / 爆拉跌 / 爆量 / 鎖漲跌停與打開。設計要點:

- **零 IO、時鐘可注入**:窗判定、elapsed、cooldown、rearm 全部讀 `now_fn()`
  (台北牆鐘,恆單調);`SignalEvent.time` 只放 tick 時刻,純顯示用。兩條時間軸
  混用會讓「盤後補推的舊 snapshot」把 cooldown 推到未來,故單一化(design R11)。
- **狀態推進與事件產出分離**(design R2):過 gate 後 `_prev` / `_window` /
  `_limit_latch` 無條件推進,`enabled` 只決定該 kind 是否「產出事件 + 寫
  cooldown/touch_count/suppressed」。關掉爆拉不影響共用同一個窗的爆量;停用期間
  鎖上→打開的 latch 照常轉移,重開後不會補發一則過期的打開。
- **接線層(SignalHub)持有所有 IO 與 membership gate**,本模組不認得自選清單。

呼叫順序契約(換日,design §4.1 stage2):**先 `reset_day()` 再
`swap_staged_basis()`** —— `reset_day` 會清空 `_basis`(當日基準不可跨日沿用),
反過來呼叫會把剛 swap 進來的當日基準洗掉,失效樣態是「CDP 整天靜默不發」。
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from copycat.live.stock_models import StockTick
from copycat.market import tick_size_milli
from copycat.signals_config import SignalsConfig

logger = logging.getLogger(__name__)

__all__ = [
    "KIND_SWITCH",
    "SWITCH_KEYS",
    "SignalDetector",
    "SignalEvent",
    "TickContext",
]

_SESSION_START = _dt.time(9, 0)
_SESSION_END = _dt.time(13, 30)  # end-exclusive:13:30 起是收盤撮合
_EPOCH = _dt.datetime(1970, 1, 1)

#: 事件 kind → enabled 開關鍵(四鍵制,design §4.4)。
KIND_SWITCH: dict[str, str] = {
    "cdp_cross": "cdp_cross",
    "surge": "surge_crash",
    "crash": "surge_crash",
    "vol_burst": "vol_burst",
    "limit_lock": "limit_lock",
    "limit_open": "limit_lock",
}
SWITCH_KEYS: tuple[str, ...] = ("cdp_cross", "surge_crash", "vol_burst", "limit_lock")


@dataclass(frozen=True)
class SignalEvent:
    kind: str  # cdp_cross | surge | crash | vol_burst | limit_lock | limit_open
    code: str
    price_milli: int
    time: str  # 台北 HH:MM:SS(= time_key[:8];顯示用)
    time_key: str  # 台北 HH:MM:SS.fff;tick 路 = tick.time、簿路 = now_fn 毫秒時刻
    levels: tuple[str, ...]  # cdp_cross:同 tick 穿越的全部線(固定序);其他 kind 空
    direction: str | None  # cdp_cross:from_below|from_above;limit_*:up|down
    pct: float | None  # surge/crash 實際漲跌幅(%);vol_burst 實際倍率
    touch_count: int  # 當日計數;合併事件取 levels[0] 的計數


@dataclass(frozen=True)
class TickContext:
    """由 SignalHub 從 `StockDayState` 組出的簿面快照(消費端已過濾市價 0 檔位)。"""

    trade_date: str  # engine 當前交易日(舊日 snapshot gate)
    upper_milli: int | None
    lower_milli: int | None
    ask_limit_available: bool  # asks 過濾 price>0 後非空
    bid_limit_available: bool
    bids0_is_market: bool  # bids[0] 存在且 price == 0(鎖漲停市價佇列簽名)
    asks0_is_market: bool  # 對稱(鎖跌停用)
    best_bid_limit_milli: int | None
    best_ask_limit_milli: int | None
    day_volume: int  # = 當筆 tick.cum_vol;簿路無 tick → 0(簿路只評估鎖板 kind)


def _mono(now: _dt.datetime) -> float:
    """牆鐘 → 秒數純量。差值才有意義,固定 epoch 相減避開 naive datetime 的時區假設。"""
    return (now - _EPOCH).total_seconds()


def _clock_key(now: _dt.datetime) -> str:
    return f"{now:%H:%M:%S}.{now.microsecond // 1000:03d}"


class SignalDetector:
    def __init__(
        self,
        cfg: SignalsConfig,
        *,
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    ) -> None:
        self._cfg = cfg
        self._now_fn = now_fn
        self._basis: dict[str, dict[str, int] | None] = {}
        self._staged: dict[str, dict[str, int] | None] = {}
        self._staged_date: str | None = None  # 暫存區的基準日(MFS-2:跨日殘渣的唯一辨識)
        self._prev: dict[str, int] = {}
        self._window: dict[str, deque[tuple[float, int, int]]] = {}
        self._suppressed: set[tuple[str, str]] = set()
        self._cooldown: dict[tuple[str, str, str], float] = {}
        self._touch: dict[tuple[str, str, str], int] = {}
        self._latch: dict[tuple[str, str], bool] = {}

    # ---- 基準(CDP)----

    def set_basis(self, code: str, cdp: dict[str, int] | None) -> None:
        """None = 該檔基準不可得(抓取失敗),CDP 跳過、其他 kind 照常。"""
        self._basis[code] = dict(cdp) if cdp else None

    def stage_basis(self, code: str, cdp: dict[str, int] | None, basis_date: str) -> None:
        """換日 stage1 預抓:寫暫存區,`swap_staged_basis` 才生效(design R2-4)。

        `basis_date` 是這份暫存的**基準日**;換一個日別即整批作廢(暫存區只服務一個
        換日,混著兩天的內容沒有正確語意)。
        """
        if basis_date != self._staged_date:
            self._staged = {}
            self._staged_date = basis_date
        self._staged[code] = dict(cdp) if cdp else None

    def clear_staged(self) -> None:
        """丟掉暫存區(stage1 開始前呼叫:上一輪的殘渣不得參與這一輪)。"""
        self._staged = {}
        self._staged_date = None

    def swap_staged_basis(self, expected_date: str) -> bool:
        """暫存區整批換上;空或**日別不符** → False 並清空,讓 hub 走「重抓」fallback。

        日別檢查是 MFS-2 的核心:上一輪換日的殘渣沿用起來沒有任何錯誤訊號,只是整天
        用昨天的 CDP 基準。清空是必要的 —— 留著下一輪又會撞上同一份。
        """
        if not self._staged or self._staged_date != expected_date:
            self.clear_staged()
            return False
        self._basis = self._staged
        self._staged = {}
        self._staged_date = None
        return True

    def clear_all_basis(self) -> None:
        self._basis.clear()

    # ---- 生命週期 ----

    def reset_day(self) -> None:
        """換日重置(呼叫順序契約見模組 docstring:先 reset_day 再 swap)。"""
        self._basis.clear()
        self._prev.clear()
        self._window.clear()
        self._suppressed.clear()
        self._cooldown.clear()
        self._touch.clear()
        self._latch.clear()

    def drop_code(self, code: str) -> None:
        self._basis.pop(code, None)
        self._staged.pop(code, None)
        self._prev.pop(code, None)
        self._window.pop(code, None)
        self._suppressed = {k for k in self._suppressed if k[0] != code}
        self._cooldown = {k: v for k, v in self._cooldown.items() if k[0] != code}
        self._touch = {k: v for k, v in self._touch.items() if k[0] != code}
        self._latch = {k: v for k, v in self._latch.items() if k[0] != code}

    # ---- 主入口 ----

    def evaluate(
        self,
        code: str,
        tick: StockTick,
        ctx: TickContext,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        """一筆成交 tick → 事件清單。三道 gate 任一不過:回 [] 且**不推進任何狀態**。"""
        now = self._now_fn()
        if not self._in_session(now):
            return []
        if tick.trade_date != ctx.trade_date:  # 盤中新增自選的 fresh subscribe 舊日 snapshot
            return []
        mono = _mono(now)
        price = tick.price_milli
        if code not in self._prev:  # 首 tick 只初始化(無前值可比,任何判定都是猜)
            self._prev[code] = price
            self._window[code] = deque([(mono, price, tick.qty)])
            return []

        prev = self._prev[code]
        window = self._window.setdefault(code, deque())
        window.append((mono, price, tick.qty))
        cutoff = mono - self._cfg.surge_window_secs
        while window and window[0][0] < cutoff:
            window.popleft()
        self._prev[code] = price

        events: list[SignalEvent] = []
        key = tick.time or _clock_key(now)
        events.extend(self._eval_cdp(code, prev, price, key, mono, enabled))
        events.extend(self._eval_surge(code, price, key, window, mono, enabled))
        events.extend(self._eval_volume(code, ctx, key, window, now, mono, enabled))
        events.extend(self._eval_limit_tick(code, price, ctx, key, mono, enabled))
        return events

    def evaluate_book(
        self,
        code: str,
        ctx: TickContext,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        """純簿更新 → 只評估「鎖停打開」(尾盤解鎖無成交也抓得到,design §3.5b)。

        日別防護不在這裡:換日 pending 期間 engine 不呼叫本方法(design §4.1 R2-2)。
        """
        now = self._now_fn()
        if not self._in_session(now):
            return []
        mono = _mono(now)
        key = _clock_key(now)  # 簿路無成交 → 事件時刻是伺服器時刻(design §9)
        events: list[SignalEvent] = []
        for direction, limit_milli, reopened in (
            ("up", ctx.upper_milli, ctx.ask_limit_available),
            ("down", ctx.lower_milli, ctx.bid_limit_available),
        ):
            if limit_milli is None or not reopened:
                continue
            if not self._latch.get((code, direction), False):
                continue
            self._latch[(code, direction)] = False  # latch 轉移無條件
            ev = self._limit_event(code, "limit_open", direction, limit_milli, key, mono, enabled)
            if ev is not None:
                events.append(ev)
        return events

    # ---- gate / 共用 ----

    def _in_session(self, now: _dt.datetime) -> bool:
        return _SESSION_START <= now.time() < _SESSION_END

    def _cooling(self, key: tuple[str, str, str], mono: float) -> bool:
        return self._cooldown.get(key, 0.0) > mono

    def _arm(self, key: tuple[str, str, str], mono: float, secs: float) -> None:
        self._cooldown[key] = mono + secs

    def _bump(self, key: tuple[str, str, str]) -> int:
        count = self._touch.get(key, 0) + 1
        self._touch[key] = count
        return count

    # ---- CDP 穿越(SC-1)----

    def _eval_cdp(
        self,
        code: str,
        prev: int,
        price: int,
        key: str,
        mono: float,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        basis = self._basis.get(code)
        if not basis:
            return []
        # rearm 解除是無條件檢查(停用期間也照解,重開後語意才對)
        gap = self._cfg.cdp_rearm_ticks * tick_size_milli(price)
        for name, value in basis.items():
            if (code, name) in self._suppressed and abs(price - value) >= gap:
                self._suppressed.discard((code, name))
        if "cdp_cross" not in enabled:
            return []

        crossed: list[tuple[int, str]] = []
        direction: str | None = None
        for name, value in basis.items():
            if prev < value <= price:
                direction = "from_below"
                crossed.append((value, name))
            elif prev > value >= price:
                direction = "from_above"
                crossed.append((value, name))
        if not crossed or direction is None:
            return []
        # 固定序(id 決定性的前提):from_below 線價低→高、from_above 高→低
        crossed.sort(key=lambda item: (item[0], item[1]), reverse=direction == "from_above")

        levels = tuple(
            name
            for _value, name in crossed
            if (code, name) not in self._suppressed
            and not self._cooling((code, "cdp_cross", name), mono)
        )
        if not levels:
            return []
        counts: dict[str, int] = {}
        for name in levels:
            self._suppressed.add((code, name))
            self._arm((code, "cdp_cross", name), mono, self._cfg.cdp_cooldown_secs)
            counts[name] = self._bump((code, "cdp_cross", name))
        return [
            SignalEvent(
                kind="cdp_cross",
                code=code,
                price_milli=price,
                time=key[:8],
                time_key=key,
                levels=levels,
                direction=direction,
                pct=None,
                touch_count=counts[levels[0]],  # 合併事件取 levels[0] 的計數
            )
        ]

    # ---- 爆拉 / 爆跌(SC-2)----

    def _eval_surge(
        self,
        code: str,
        price: int,
        key: str,
        window: deque[tuple[float, int, int]],
        mono: float,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        if "surge_crash" not in enabled or len(window) < 2:
            return []
        oldest = window[0][1]
        if oldest <= 0:
            return []
        pct = (price - oldest) / oldest * 100
        if pct >= self._cfg.surge_pct:
            kind = "surge"
        elif pct <= -self._cfg.surge_pct:
            kind = "crash"
        else:
            return []
        if self._cooling((code, kind, ""), mono):
            return []
        self._arm((code, kind, ""), mono, self._cfg.surge_cooldown_secs)
        return [
            SignalEvent(
                kind=kind,
                code=code,
                price_milli=price,
                time=key[:8],
                time_key=key,
                levels=(),
                direction=None,
                pct=pct,
                touch_count=self._bump((code, kind, "")),
            )
        ]

    # ---- 爆量(SC-3)----

    def _eval_volume(
        self,
        code: str,
        ctx: TickContext,
        key: str,
        window: deque[tuple[float, int, int]],
        now: _dt.datetime,
        mono: float,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        if "vol_burst" not in enabled:
            return []
        open_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
        elapsed_min = (mono - _mono(open_dt)) / 60
        if elapsed_min < self._cfg.vol_min_elapsed_min:  # 開盤初段均量不穩
            return []
        day_volume = ctx.day_volume
        avg_per_min = day_volume / elapsed_min
        if avg_per_min <= 0:
            return []
        window_min = self._cfg.surge_window_secs / 60
        window_vol = sum(qty for _ts, _price, qty in window)
        ratio = window_vol / (avg_per_min * window_min)
        if (
            ratio < self._cfg.vol_ratio
            or window_vol < self._cfg.vol_min_window_lots
            or day_volume < self._cfg.vol_min_day_lots
        ):
            return []
        if self._cooling((code, "vol_burst", ""), mono):
            return []
        self._arm((code, "vol_burst", ""), mono, self._cfg.vol_cooldown_secs)
        price = window[-1][1]
        return [
            SignalEvent(
                kind="vol_burst",
                code=code,
                price_milli=price,
                time=key[:8],
                time_key=key,
                levels=(),
                direction=None,
                pct=ratio,
                touch_count=self._bump((code, "vol_burst", "")),
            )
        ]

    # ---- 鎖漲跌停 / 打開(SC-4)----

    def _eval_limit_tick(
        self,
        code: str,
        price: int,
        ctx: TickContext,
        key: str,
        mono: float,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        events: list[SignalEvent] = []
        up, low = ctx.upper_milli, ctx.lower_milli
        for direction, limit_milli, locked, opened in (
            ("up", up, self._locked_up(price, ctx), up is not None and price < up),
            ("down", low, self._locked_down(price, ctx), low is not None and price > low),
        ):
            if limit_milli is None:
                continue
            latched = self._latch.get((code, direction), False)
            if locked and not latched:
                self._latch[(code, direction)] = True  # latch 轉移無條件
                ev = self._limit_event(code, "limit_lock", direction, price, key, mono, enabled)
            elif latched and opened:
                self._latch[(code, direction)] = False
                ev = self._limit_event(code, "limit_open", direction, price, key, mono, enabled)
            else:
                ev = None
            if ev is not None:
                events.append(ev)
        return events

    def _locked_up(self, price: int, ctx: TickContext) -> bool:
        """複合簽名(design §3.5):第三項排除「首攻吃光賣盤」—— 那一筆 ask 側同樣空,
        但買方市價佇列未形成、最佳限價買仍在漲停價下。"""
        if ctx.upper_milli is None or price != ctx.upper_milli or ctx.ask_limit_available:
            return False
        return ctx.bids0_is_market or ctx.best_bid_limit_milli == ctx.upper_milli

    def _locked_down(self, price: int, ctx: TickContext) -> bool:
        if ctx.lower_milli is None or price != ctx.lower_milli or ctx.bid_limit_available:
            return False
        return ctx.asks0_is_market or ctx.best_ask_limit_milli == ctx.lower_milli

    def _limit_event(
        self,
        code: str,
        kind: str,
        direction: str,
        price_milli: int,
        key: str,
        mono: float,
        enabled: frozenset[str],
    ) -> SignalEvent | None:
        if KIND_SWITCH[kind] not in enabled:
            return None
        # cooldown per (code, kind, direction) 分桶(design §3.5 amendment 2026-08-04):
        # lock 自己 600s、open 自己 600s,互不干擾 —— 共用桶會吃掉「鎖上後 600s 內的
        # 真打開」,而打開正是高價值訊號。flapping 上界 = 每 600s 一對 lock/open。
        # `limit_cooldown_secs` 仍是兩者共用的門檻值。
        bucket = (code, kind, direction)
        if self._cooling(bucket, mono):
            return None
        self._arm(bucket, mono, self._cfg.limit_cooldown_secs)
        return SignalEvent(
            kind=kind,
            code=code,
            price_milli=price_milli,
            time=key[:8],
            time_key=key,
            levels=(),
            direction=direction,
            pct=None,
            touch_count=self._bump((code, kind, direction)),
        )
