"""個股訊號接線層(design §4 — SC-1/5/7/12)。

`SignalDetector` 是零 IO 狀態機,本模組持有它的**全部** IO 與 membership:

- **membership gate**:`_watch` 由 `on_watchlist` 全量替換。主圖臨時看的非自選股
  照樣會走 engine 的 `_handle_quote`,但不評估、不發任何訊號。
- **熱路徑只做純計算 + 入佇列**:`on_tick` 同步算完 → WS `publish` 同步送出
  (前端要即時),jsonl 與 Discord 一律丟進**有界**佇列由 worker 消化。
  佇列滿時**丟最舊**再放入(design R14)—— 不 `await put`,熱路徑零反壓;
  丟棄有 `dropped` 計數與節流 log,不是靜默吞掉。
- **訊號 id 是決定性鍵**(`trade_date-code-kind-levels|direction-time_key`):
  不依賴 process 記憶,重啟後重發同一事件會得到同一個 id,前端與 jsonl 都據此去重。
- **Discord 節流只擋 Discord**:WS 與 jsonl 是歷史真相源,節流它們會讓
  「reconnect refetch today」自癒語意破掉(design §4.3 R2-8)。

換日順序契約(design §4.1 stage2):`on_rollover` **先 `reset_day()` 再
`swap_staged_basis()`** —— 反了會把剛換上的當日基準洗掉(見 signal_state 模組
docstring)。stage1 (`on_rollover_pending`) 在盤前把次日基準抓進暫存區,
stage2 只做 swap,開盤第一筆 tick 起 CDP 即用當日正確基準。
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt
import inspect
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from copycat.fileio import atomic_write_text
from copycat.live.signal_state import (
    SWITCH_KEYS,
    SignalDetector,
    SignalEvent,
    TickContext,
)

# 私有名刻意共用:鎖停時 TC4 在第一檔推「市價單佇列」價格欄為 0,而過濾規則寫成兩份
# 就會漂移(CLAUDE.md §8 已記四處被同一個 0 打穿的事故)。這裡要的正是消費端那把尺。
from copycat.live.stock_models import StockTick, _best_limit_price
from copycat.live.stock_source import DailyBar
from copycat.live.stock_state import StockDayState
from copycat.server.overlay import compute_cdp
from copycat.signals_config import SignalsConfig

logger = logging.getLogger(__name__)

__all__ = ["QUEUE_MAXSIZE", "SignalHub", "format_signal_text"]

#: fanout 佇列上限(design §4.3);測試以 monkeypatch 縮小驗滿載策略。
QUEUE_MAXSIZE = 100
_ENABLED_FILE = "signals_enabled.json"
_SIGNAL_DIR = "signals"
_BASIS_BARS = 5  # CDP 只要最後一根已完成 bar,多抓幾根當緩衝
_DROP_LOG_EVERY = 20  # 丟棄計數每 N 筆記一次(避免爆量時 log 自己變瓶頸)
_DISCORD_WINDOW_SECS = 60.0

_LEVEL_LABEL = {"cdp": "中軸", "ah": "AH", "nh": "NH", "nl": "NL", "al": "AL"}
_LEVEL_ROLE = {"ah": "壓力", "nh": "壓力", "nl": "支撐", "al": "支撐"}


def _levels_of(row: dict[str, Any]) -> list[str]:
    raw = row.get("levels") or []
    return [str(x) for x in raw]


def _kind_text(row: dict[str, Any]) -> str:
    kind = str(row.get("kind", ""))
    direction = row.get("direction")
    if kind == "cdp_cross":
        levels = _levels_of(row)
        label = "+".join(_LEVEL_LABEL.get(x, x.upper()) for x in levels)
        verb = "突破" if direction == "from_below" else "跌破"
        role = _LEVEL_ROLE.get(levels[0]) if levels else None
        note = "・".join([x for x in (role, f"第{row.get('touch_count')}次") if x])
        return f"{verb} CDP {label}({note})"
    pct = row.get("pct")
    value = float(pct) if isinstance(pct, (int, float)) else 0.0
    if kind in ("surge", "crash"):
        return f"{'爆拉' if kind == 'surge' else '爆跌'} {value:+.2f}%"
    if kind == "vol_burst":
        return f"爆量 {value:.1f} 倍"
    if kind == "limit_lock":
        return "鎖漲停" if direction == "up" else "鎖跌停"
    if kind == "limit_open":
        return "漲停打開" if direction == "up" else "跌停打開"
    return kind


def format_signal_text(row: dict[str, Any]) -> str:
    """Discord 文案(bot 與 webhook 同一段,design §4.3)。"""
    price = row.get("price")
    price_text = f"{price / 1000:.2f}" if isinstance(price, int) else "-"
    who = f"{row.get('name') or ''} {row.get('code', '')}".strip()
    return f"🔔 {_kind_text(row)}｜{who}｜{price_text}｜{row.get('time', '')}"


class SignalHub:
    def __init__(
        self,
        cfg: SignalsConfig,
        *,
        publish: Callable[[dict], None],
        daily_bars: Callable[[str, int], Awaitable[list[DailyBar]]],
        notify_fallback: Callable[[str], bool],
        data_dir: Path,
        trade_date_fn: Callable[[], str],
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    ) -> None:
        self._cfg = cfg
        self._publish = publish
        self._daily_bars = daily_bars
        self._notify_fallback = notify_fallback
        self._data_dir = Path(data_dir)
        self._trade_date_fn = trade_date_fn
        self._now_fn = now_fn
        self._detector = SignalDetector(cfg, now_fn=now_fn)
        self._watch: set[str] = set()
        self._enabled: dict[str, bool] = self._load_enabled()
        self._enabled_set: frozenset[str] = self._as_set(self._enabled)
        self._basis_jobs: asyncio.Queue[tuple[str, str, bool]] = asyncio.Queue()
        self._staged_date: str | None = None  # 當前 stage1 的基準日(過期 job 的判準)
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._tasks: list[asyncio.Task[None]] = []
        self._discord_sender: Callable[[str], Any] | None = None
        self._discord_sent: deque[_dt.datetime] = deque()
        self.dropped = 0

    # ---- 生命週期 ----

    async def start(self) -> None:
        if self._tasks:
            return
        self._tasks.append(asyncio.create_task(self._basis_worker()))
        self._tasks.append(asyncio.create_task(self._fanout_worker()))

    async def close(self) -> None:
        tasks = list(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._flush_pending()

    def attach_discord(self, sender: Callable[[str], Any]) -> None:
        """sender 可為同步或 async(`bot.send_signal`);回傳 falsy = 未送出。"""
        self._discord_sender = sender

    # ---- engine 掛點 ----

    def on_tick(self, code: str, tick: StockTick, state: StockDayState) -> None:
        if code not in self._watch:
            return
        try:
            ctx = self._context(state, tick.cum_vol)
            for event in self._detector.evaluate(code, tick, ctx, self._enabled_set):
                self._emit(event, state)
        except Exception:
            # engine 熱路徑不可被訊號層汙染:丟棄這一筆評估,tick 本身照常走完
            logger.exception("訊號評估失敗(丟棄該 tick):%s", code)

    def on_book(self, code: str, state: StockDayState) -> None:
        if code not in self._watch:
            return
        try:
            ctx = self._context(state, 0)  # 簿路只評估鎖板 kind,不會用到 day_volume
            for event in self._detector.evaluate_book(code, ctx, self._enabled_set):
                self._emit(event, state)
        except Exception:
            logger.exception("簿更新訊號評估失敗(丟棄):%s", code)

    def on_rollover_pending(self, new_date: str) -> None:
        """stage1(盤前):以次日為基準日預抓進暫存區,stage2 只做 swap。

        **先清暫存區**(MFS-2):快路徑(pending 與 stage2 同一輪 loop 連發)會讓 stage1
        的 job 在 swap 之後才被 worker 消化,結果留在暫存區到下一輪換日;不清掉的話
        下一次 swap 會回 True 並把舊日基準當當日基準用一整天,零錯誤訊號。
        """
        self._detector.clear_staged()
        self._staged_date = new_date
        self.request_basis(sorted(self._watch), basis_date=new_date, staged=True)

    def on_rollover(self) -> None:
        expected = self._trade_date_fn()  # engine 已前進到新日別(stage2 契約)
        self._detector.reset_day()  # 順序契約:reset 會清 _basis,必須先於 swap
        if not self._detector.swap_staged_basis(expected):
            # stage1 沒跑過(週六補市日 / server 盤中才啟動)→ 重抓;該窗 CDP 停用
            logger.info("換日無預抓基準,清空重抓(design §4.2 fallback)")
            self.request_basis(sorted(self._watch))

    def on_watchlist(self, codes: list[str]) -> None:
        new = set(codes)
        added = new - self._watch
        removed = self._watch - new
        self._watch = new
        for code in sorted(removed):
            self._detector.drop_code(code)
        if added:
            self.request_basis(sorted(added))

    # ---- CDP 基準 ----

    def request_basis(
        self, codes: list[str], *, basis_date: str | None = None, staged: bool = False
    ) -> None:
        date = basis_date or self._trade_date_fn()
        for code in codes:
            self._basis_jobs.put_nowait((code, date, staged))

    async def _basis_worker(self) -> None:
        while True:
            code, basis_date, staged = await self._basis_jobs.get()
            try:
                await self._resolve_basis(code, basis_date, staged)
            except asyncio.CancelledError:
                raise  # finally 仍會 task_done,取消不留未完成計數
            except Exception:
                # worker 死掉 = 之後所有基準靜默停用(stock_engine._backfill_worker CR4 同款)
                logger.exception("CDP 基準解析未預期失敗,%s 停用 CDP", code)
                self._detector.set_basis(code, None)
            finally:
                self._basis_jobs.task_done()
            if self._cfg.basis_gap_secs > 0:
                # 與主圖回補 / K 線 route 共用同一條 TC4 stock session,連發要讓位
                await asyncio.sleep(self._cfg.basis_gap_secs)

    async def _resolve_basis(self, code: str, basis_date: str, staged: bool) -> None:
        try:
            bars = await self._daily_bars(code, _BASIS_BARS)
        except Exception:
            # 具體處理 = 基準設 None(CDP 跳過、其他 kind 照常),不重試(design §4.2)
            logger.exception("CDP 基準日 K 取得失敗,%s 停用 CDP", code)
            bars = []
        done = [b for b in bars if b["date"] < basis_date]  # 今日 partial bar 不得入計算
        cdp: dict[str, int] | None = None
        if done:
            last = done[-1]
            cdp = compute_cdp(last["high"], last["low"], last["close"])
        else:
            logger.warning("%s 無 %s 之前的已完成日 K,CDP 停用", code, basis_date)
        if staged:
            if basis_date != self._staged_date:
                # 這則是上一輪 stage1 排的、在 `clear_staged` 之後才跑完的 in-flight job;
                # 放進去等於把殘渣重新種回暫存區(MFS-2)
                logger.info("捨棄過期的 staged 基準:%s(%s)", code, basis_date)
                return
            self._detector.stage_basis(code, cdp, basis_date)
        else:
            self._detector.set_basis(code, cdp)

    # ---- 事件 fanout ----

    def _context(self, state: StockDayState, day_volume: int) -> TickContext:
        book = state.book
        bids = book.bids if book is not None else []
        asks = book.asks if book is not None else []
        meta = state.meta
        best_bid = _best_limit_price(bids)
        best_ask = _best_limit_price(asks)
        return TickContext(
            trade_date=self._trade_date_fn(),
            upper_milli=meta.upper_milli if meta is not None else None,
            lower_milli=meta.lower_milli if meta is not None else None,
            ask_limit_available=best_ask is not None,
            bid_limit_available=best_bid is not None,
            bids0_is_market=bool(bids) and bids[0][0] == 0,
            asks0_is_market=bool(asks) and asks[0][0] == 0,
            best_bid_limit_milli=best_bid,
            best_ask_limit_milli=best_ask,
            day_volume=day_volume,
        )

    def _emit(self, event: SignalEvent, state: StockDayState) -> None:
        trade_date = self._trade_date_fn()
        payload = {
            "type": "signal",
            "id": _event_id(trade_date, event),
            "kind": event.kind,
            "code": event.code,
            "name": state.meta.name if state.meta is not None else "",
            "price": event.price_milli,
            "time": event.time,
            "levels": list(event.levels),
            "direction": event.direction,
            "pct": event.pct,
            "touch_count": event.touch_count,
        }
        self._publish(payload)  # WS 同步先送(前端要即時)
        self._enqueue({**payload, "trade_date": trade_date})

    def _enqueue(self, row: dict) -> None:
        try:
            self._queue.put_nowait(row)
            return
        except asyncio.QueueFull:
            pass
        with contextlib.suppress(asyncio.QueueEmpty):
            self._queue.get_nowait()  # 丟最舊:新訊號比舊訊號值錢,且熱路徑不可反壓
            self._queue.task_done()
        self.dropped += 1
        if self.dropped % _DROP_LOG_EVERY == 1:
            logger.warning("訊號 fanout 佇列滿,已丟棄 %d 筆(WS 不受影響)", self.dropped)
        try:
            self._queue.put_nowait(row)
        except asyncio.QueueFull:
            logger.error("訊號 fanout 佇列騰位失敗,丟棄 %s", row.get("id"))

    async def _fanout_worker(self) -> None:
        while True:
            row = await self._queue.get()
            try:
                await asyncio.to_thread(self._append_jsonl, row)
                await self._send_discord(row)
            except asyncio.CancelledError:
                raise  # finally 仍會 task_done
            except Exception:
                logger.exception("訊號 fanout 失敗(worker 續行):%s", row.get("id"))
            finally:
                self._queue.task_done()

    async def _flush_pending(self) -> None:
        """關機盡力落檔:jsonl 是歷史真相源,Discord 這時不再送。"""
        rows: list[dict] = []
        while True:
            try:
                rows.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for row in rows:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._append_jsonl, row)

    # ---- jsonl ----

    def _signal_path(self, trade_date: str) -> Path:
        return self._data_dir / _SIGNAL_DIR / f"{trade_date.replace('-', '')}.jsonl"

    def _append_jsonl(self, row: dict) -> None:
        path = self._signal_path(str(row.get("trade_date", "")))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("訊號 jsonl 寫入失敗(%s):%s", path, e)

    def today_signals(self) -> list[dict]:
        return self.read_signals(self._trade_date_fn())

    def read_signals(self, trade_date: str) -> list[dict]:
        """當日 jsonl → row 清單;壞行跳過(半寫入的最後一行不該讓整條端點掛掉)。"""
        path = self._signal_path(trade_date)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.error("訊號 jsonl 讀取失敗(%s):%s", path, e)
            return []
        rows: list[dict] = []
        skipped = 0
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            if isinstance(row, dict):
                rows.append(row)
            else:
                skipped += 1
        if skipped:
            logger.warning("訊號 jsonl %s 跳過 %d 壞行", path.name, skipped)
        return rows

    # ---- Discord ----

    def _allow_discord(self) -> bool:
        now = self._now_fn()
        cutoff = now - _dt.timedelta(seconds=_DISCORD_WINDOW_SECS)
        while self._discord_sent and self._discord_sent[0] < cutoff:
            self._discord_sent.popleft()
        if len(self._discord_sent) >= self._cfg.discord_per_min:
            logger.warning(
                "Discord 每分鐘上限 %d 已滿,本則只進 WS/jsonl", self._cfg.discord_per_min
            )
            return False
        self._discord_sent.append(now)
        return True

    async def _send_discord(self, row: dict) -> None:
        if not self._allow_discord():
            return
        text = format_signal_text(row)
        sender = self._discord_sender
        if sender is not None:
            try:
                result = sender(text)
                if inspect.isawaitable(result):
                    result = await result
                if result:
                    return
                logger.warning("Discord bot 未送出 %s,改走 webhook", row.get("id"))
            except Exception:
                logger.exception("Discord bot 發送失敗,改走 webhook:%s", row.get("id"))
        try:
            ok = await asyncio.to_thread(self._notify_fallback, text)
        except Exception:
            logger.exception("Discord webhook 發送失敗:%s", row.get("id"))
            return
        if not ok:
            logger.warning("Discord 兩層皆未送出 %s(WS/jsonl 不受影響)", row.get("id"))

    # ---- enabled 開關(SC-12)----

    @staticmethod
    def _as_set(flags: dict[str, bool]) -> frozenset[str]:
        return frozenset(key for key, value in flags.items() if value)

    def enabled(self) -> dict[str, bool]:
        return dict(self._enabled)

    async def set_enabled(self, flags: dict[str, bool]) -> None:
        """非法鍵 / 非 bool 值 → ValueError(route 轉 400 INVALID_SIGNALS_ENABLED)。"""
        for key, value in flags.items():
            if key not in SWITCH_KEYS or not isinstance(value, bool):
                raise ValueError(f"非法訊號開關:{key}={value!r}")
        merged = {**self._enabled, **flags}
        self._enabled = merged
        self._enabled_set = self._as_set(merged)
        await asyncio.to_thread(self._write_enabled, merged)

    def _enabled_path(self) -> Path:
        return self._data_dir / _ENABLED_FILE

    def _load_enabled(self) -> dict[str, bool]:
        flags = dict.fromkeys(SWITCH_KEYS, True)  # 缺檔 = 全開
        path = self._enabled_path()
        if not path.exists():
            return flags
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("訊號開關檔讀取失敗,套全開:%s", e)
            return flags
        if not isinstance(raw, dict):
            logger.warning("訊號開關檔格式非物件,套全開:%s", path)
            return flags
        for key in SWITCH_KEYS:
            value = raw.get(key)
            if isinstance(value, bool):
                flags[key] = value
        return flags

    def _write_enabled(self, flags: dict[str, bool]) -> None:
        path = self._enabled_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, json.dumps(flags, ensure_ascii=False, indent=2))
        except OSError as e:
            logger.error("訊號開關檔寫入失敗(%s):%s", path, e)


def _event_id(trade_date: str, event: SignalEvent) -> str:
    """決定性鍵(design §4.3 R1):不依賴 process 記憶 → 重啟後同一事件同 id。"""
    tag = "+".join(event.levels) or event.direction or "-"
    return f"{trade_date}-{event.code}-{event.kind}-{tag}-{event.time_key}"
