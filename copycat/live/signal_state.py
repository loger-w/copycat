"""個股即時訊號偵測狀態機(零 IO;design §3 — SC-1/2/3/4/6)。

四類訊號:CDP 五線穿越 / 爆拉跌 / 爆量 / 鎖漲跌停與打開。設計要點:

- **零 IO、時鐘可注入**:窗判定、elapsed、cooldown、rearm 全部讀 `now_fn()`
  (台北牆鐘,恆單調);`SignalEvent.time` 只放 tick 時刻,純顯示用。兩條時間軸
  混用會讓「盤後補推的舊 snapshot」把 cooldown 推到未來,故單一化(design R11)。
- **狀態推進與事件產出分離**(design R2):過 gate 後 `_prev` / `_window` /
  `_limit_latch` 無條件推進,`enabled` 只決定該 kind 是否「產出事件 + 寫
  cooldown/touch_count/suppressed」。關掉爆拉不影響共用同一個窗的爆量;停用期間
  鎖上→打開的 latch 照常轉移,重開後不會補發一則過期的打開。
- **CDP rearm 是「距離 + 駐留」兩道**(signal-denoise SC-1):解除 suppressed 要
  **連續**待在線外(`|price − 線價| ≥ cdp_rearm_ticks × tick`)滿 `cdp_rearm_dwell_secs`,
  中途任一筆回到帶內即歸零重算。起算時點就記在 `_suppressed` 的值上(None = 帶內 /
  尚未起算);穿越當筆若已在線外(跳空)即從該筆起算。`dwell = 0` 完全等於舊語意。
- **穿越判定看側別不看不等式**(signal-denoise SC-2):`_side[(code, level)] =
  (線價, −1/0/+1)`,`price == 線價` 是「線上」—— 不觸發也不改變側別,穿越 = 上一個
  非線上側別與本 tick 側別相反。側別存了線價,基準換線即自動失效;`set_basis` 另外
  一律清該檔側別(盲窗 None 之後同線價回來,線價比對擋不住 —— review C-1)。
  側別推進與駐留計時同屬狀態推進,在 `enabled` gate **之前**跑。
- **接線層(SignalHub)持有所有 IO 與 membership gate**,本模組不認得自選清單。

呼叫順序契約(換日,design §4.1 stage2):**先 `reset_day()` 再 promote 暫存基準**
—— `reset_day` 會清空 `_basis`(當日基準不可跨日沿用),反過來呼叫會把剛換上的
當日基準洗掉,失效樣態是「CDP 整天靜默不發」。

**暫存區家族(`set_staged_basis` / `clear_staged` / `swap_staged_basis`)已無呼叫端**
(signal-rules:規則化之後暫存區與日別判定整組移交 `SignalHub`,基準快照歸 hub 唯一
持有,detector 只認 `set_basis`)。留著是為了不在同一輪裡混入純結構改動 —— 真移除
是 🔵,已記 `docs/next-time.md`。改換日流程時**不要**回頭呼叫它們:hub 的暫存區才是
真值,兩份暫存會漂。
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

#: 事件 kind → enabled 開關鍵(design §4.4;2026-09-02 起五鍵)。
KIND_SWITCH: dict[str, str] = {
    "cdp_cross": "cdp_cross",
    "surge": "surge_crash",
    "crash": "surge_crash",
    "surge_pullback": "surge_pullback",
    "vol_burst": "vol_burst",
    "limit_lock": "limit_lock",
    "limit_open": "limit_lock",
}
SWITCH_KEYS: tuple[str, ...] = (
    "cdp_cross",
    "surge_crash",
    "surge_pullback",
    "vol_burst",
    "limit_lock",
)


@dataclass(frozen=True)
class SignalEvent:
    kind: str  # cdp_cross | surge | crash | surge_pullback | vol_burst | limit_lock | limit_open
    code: str
    price_milli: int
    time: str  # 台北 HH:MM:SS(= time_key[:8];顯示用)
    time_key: str  # 台北 HH:MM:SS.fff;tick 路 = tick.time、簿路 = now_fn 毫秒時刻
    levels: tuple[str, ...]  # cdp_cross:同 tick 穿越的全部線(固定序);其他 kind 空
    direction: str | None  # cdp_cross:from_below|from_above;limit_*:up|down
    pct: float | None  # surge/crash 實際漲跌幅(%);vol_burst 實際倍率;surge_pullback 回落幅度(正)
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


def _sign(value: int) -> int:
    """−1 / 0 / +1;0 = 「在線上」,不是任何一側。"""
    return (value > 0) - (value < 0)


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
        # 值 = 「連續線外」的起算 mono(None = 目前在帶內 / 尚未起算)
        self._suppressed: dict[tuple[str, str], float | None] = {}
        # (code, level) → (線價, 側別 −1/0/+1);線價一起存,基準換線即自動失效
        self._side: dict[tuple[str, str], tuple[int, int]] = {}
        self._cooldown: dict[tuple[str, str, str], float] = {}
        self._touch: dict[tuple[str, str, str], int] = {}
        self._latch: dict[tuple[str, str], bool] = {}
        # 爆拉回檔波狀態:code → (armed, 峰值 milli)。缺鍵 = 尚未武裝(等 surge 條件);
        # armed=False = 本波已發過(或停用期間被消耗),等創新高重武裝。
        self._pullback: dict[str, tuple[bool, int]] = {}

    # ---- 基準(CDP)----

    def set_basis(self, code: str, cdp: dict[str, int] | None) -> None:
        """None = 該檔基準不可得(抓取失敗),CDP 跳過、其他 kind 照常。

        換基準**一律清該檔側別**(review C-1):側別存的線價只擋得住「換了線價」,
        擋不住「盲窗(None)之後同一條線回來」—— 盲窗期間 CDP 整段跳過、側別不推進,
        價格卻照走,殘留的舊側別會讓恢復後的首筆假發一則穿越。清掉之後首筆退回
        `prev` 推定,與基準第一次到位時同一條路徑(舊語意)。
        """
        self._basis[code] = dict(cdp) if cdp else None
        self._side = {k: v for k, v in self._side.items() if k[0] != code}

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
        self._side.clear()
        self._cooldown.clear()
        self._touch.clear()
        self._latch.clear()
        self._pullback.clear()

    def drop_code(self, code: str) -> None:
        self._basis.pop(code, None)
        self._staged.pop(code, None)
        self._prev.pop(code, None)
        self._window.pop(code, None)
        self._suppressed = {k: v for k, v in self._suppressed.items() if k[0] != code}
        self._side = {k: v for k, v in self._side.items() if k[0] != code}
        self._cooldown = {k: v for k, v in self._cooldown.items() if k[0] != code}
        self._touch = {k: v for k, v in self._touch.items() if k[0] != code}
        self._latch = {k: v for k, v in self._latch.items() if k[0] != code}
        self._pullback.pop(code, None)

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
        events.extend(self._eval_pullback(code, price, key, window, mono, enabled))
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
        # 駐留計時與側別推進都是**狀態推進**,在 enabled gate 之前無條件跑(停用期間
        # 也照走,重開後語意才對:不補發、方向也不會因為漏掉幾筆而反過來)。
        gap = self._cfg.cdp_rearm_ticks * tick_size_milli(price)
        self._advance_rearm(code, basis, price, gap, mono)
        direction, crossed = self._advance_sides(code, basis, prev, price)
        if "cdp_cross" not in enabled or direction is None:
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
            # 起算時點:當筆已在線外(跳空穿越)就從這一筆算,否則等第一筆線外 tick
            outside = abs(price - basis[name]) >= gap
            self._suppressed[(code, name)] = mono if outside else None
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

    def _advance_rearm(
        self,
        code: str,
        basis: dict[str, int],
        price: int,
        gap: int,
        mono: float,
    ) -> None:
        """suppressed 的解除:**連續**待在線外滿 `cdp_rearm_dwell_secs` 才解,回帶內即歸零。

        起算時點記在 `_suppressed` 的值上(None = 目前在帶內 / 尚未起算)。只看
        `|price − 線價| ≥ gap` 的絕對距離、不分上下側(跨側跳空本身會產生新的穿越判定,
        分側只會讓稀疏 tick 誤歸零)。`cdp_rearm_dwell_secs = 0` 完全等於舊語意
        「第一筆線外 tick 即解除」。
        """
        dwell = self._cfg.cdp_rearm_dwell_secs
        for name, value in basis.items():
            key = (code, name)
            if key not in self._suppressed:
                continue
            if abs(price - value) < gap:
                self._suppressed[key] = None  # 回帶內 → 駐留歸零重算
                continue
            since = self._suppressed[key]
            if since is None:
                since = mono
                self._suppressed[key] = since
            if mono - since >= dwell:
                del self._suppressed[key]

    def _advance_sides(
        self,
        code: str,
        basis: dict[str, int],
        prev: int,
        price: int,
    ) -> tuple[str | None, list[tuple[int, str]]]:
        """推進「價格在線的哪一側」並回傳本 tick 的穿越(碰線點透明,SC-2)。

        `price == 線價` 是「線上」:不觸發、也不改變側別。故逐 tick 走過線價的真穿越
        (79.5 → 80.0 → 80.5)仍算一次 from_below,而「貼著線價來回」不算。側別連同
        線價一起存(`_side[(code, level)] = (線價, 側別)`):基準盤中重設後線價一變,
        舊側別自動失效,改由 `prev` 推定(等價舊式 `prev < v <= price`,每檔每日第一次
        穿越照發)。`prev` 本身在線上且無存值 → 上一側別未知,只記側別不判穿越。
        """
        below: list[tuple[int, str]] = []
        above: list[tuple[int, str]] = []
        for name, value in basis.items():
            key = (code, name)
            stored = self._side.get(key)
            last = stored[1] if stored is not None and stored[0] == value else _sign(prev - value)
            cur = _sign(price - value)
            self._side[key] = (value, cur if cur else last)  # 線上點保留上一側別
            if not last or not cur or last == cur:
                continue
            (below if cur > 0 else above).append((value, name))
        if below and above:  # 同一價格序列不可能同時上下穿 —— 不變式破了,保單一方向
            keep = _sign(price - prev)
            logger.warning(
                "CDP 側別混向 code=%s prev=%s price=%s below=%s above=%s",
                code,
                prev,
                price,
                [name for _v, name in below],
                [name for _v, name in above],
            )
            if keep > 0:
                above = []
            elif keep < 0:
                below = []
            else:  # price == prev:沒有任何依據可以選邊 → 寧可少發,不擲硬幣決定方向
                below = []
                above = []
        if below:
            return "from_below", below
        if above:
            return "from_above", above
        return None, []

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
        # 冷卻桶 surge / crash 共用(SC-3):拉上去又摔下來是同一段行情,兩則訊號的
        # 資訊量不獨立。`touch_count` 仍分 kind 計(`_bump` 用各自的鍵)。
        bucket = (code, "surge_crash", "")
        if self._cooling(bucket, mono):
            return []
        self._arm(bucket, mono, self._cfg.surge_cooldown_secs)
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

    # ---- 爆拉回檔(spec #174)----

    def _eval_pullback(
        self,
        code: str,
        price: int,
        key: str,
        window: deque[tuple[float, int, int]],
        mono: float,
        enabled: frozenset[str],
    ) -> list[SignalEvent]:
        """surge 同式武裝 → 追蹤波峰 → 回落 ≥ `pullback_pct` 一波一則。

        - **重武裝唯一路徑 = 創該波新高**(嚴格 > 峰值):發訊後 window 內漲幅往往仍
          ≥ `surge_pct`(窗尾還掛著起漲點),拿 surge 條件重武裝會讓回檔卡沿路連發 ——
          「創新高重武裝」正是 grilling 拍板要擋的這條。代價是深跌後的新一波要先過
          前波峰才會再武裝(拍板接受:目標場景是攻板股,創高是常態)。
        - **狀態轉移沿 latch 紀律無條件推進**(design R2):停用期間武裝 / 消耗照走,
          重開不補發;cooldown 同樣只 gate 事件產出(被擋的那一波不延後補發)。
        - 0 價 tick(壞資料)整段跳過:否則 (peak−0)/peak 是一記假 100% 回檔。
        """
        if price <= 0:
            return []
        entry = self._pullback.get(code)
        if entry is None:
            # 未武裝:surge 同式判定(窗內自最舊點漲幅);峰值自武裝當筆起算
            if len(window) < 2:
                return []
            oldest = window[0][1]
            if oldest <= 0:
                return []
            if (price - oldest) / oldest * 100 >= self._cfg.surge_pct:
                self._pullback[code] = (True, price)
            return []
        armed, peak = entry
        if price > peak:
            self._pullback[code] = (True, price)  # 創波高:峰值前推,發過的波重武裝
            return []
        if not armed:
            return []
        # (peak−price)*100/peak 而非 /peak*100:讓「恰好整除」的門檻值浮點精確(邊界含)
        drop = (peak - price) * 100.0 / peak
        if drop < self._cfg.pullback_pct:
            return []
        self._pullback[code] = (False, peak)  # 消耗本波(無條件,先於 enabled/cooldown gate)
        if "surge_pullback" not in enabled:
            return []
        bucket = (code, "surge_pullback", "")
        if self._cooling(bucket, mono):
            return []
        self._arm(bucket, mono, self._cfg.pullback_cooldown_secs)
        return [
            SignalEvent(
                kind="surge_pullback",
                code=code,
                price_milli=price,
                time=key[:8],
                time_key=key,
                levels=(),
                direction=None,
                pct=drop,
                touch_count=self._bump(bucket),
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
