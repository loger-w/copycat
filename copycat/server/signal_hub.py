"""個股訊號接線層(design §4 — SC-1/5/7/12)。

`SignalDetector` 是零 IO 狀態機,本模組持有它的**全部** IO 與 membership:

- **membership gate**:`_watch` 由 `on_watchlist` 全量替換。主圖臨時看的非自選股
  照樣會走 engine 的 `_handle_quote`,但不評估、不發任何訊號。
- **熱路徑只做純計算 + 入佇列**:`on_tick` 同步算完 → WS `publish` 同步送出
  (前端要即時),jsonl 與 Discord 各自丟進一條**有界**佇列由**各自的** worker 消化。
  佇列滿時**丟最舊**再放入(design R14)—— 不 `await put`,熱路徑零反壓;
  丟棄有 `dropped_jsonl` / `dropped_discord` 計數與節流 log,不是靜默吞掉。
- **兩條佇列不可合併**(CC-5):jsonl 是歷史真相源(重連 refetch 讀它),Discord 是
  可丟的通知路。共用一條時 Discord 一卡住 jsonl 就跟著缺角,而缺角靜默且不可回復。
  關機時 jsonl 佇列要排空(含 worker 手上那則),Discord 佇列直接放棄。
- **訊號 id 是決定性鍵**(`trade_date-rule_id-code-kind-levels|direction-time_key`):
  不依賴 process 記憶,重啟後重發同一事件會得到同一個 id,前端與 jsonl 都據此去重。
  規則 id 是其中一段(signal-rules R13):同 kind 兩條規則同一 tick 各發一則,沒有
  這一段兩則會撞成同一個 id 被前端當重複丟掉。
- **Discord 節流只擋 Discord**:WS 與 jsonl 是歷史真相源,節流它們會讓
  「reconnect refetch today」自癒語意破掉(design §4.3 R2-8)。

規則引擎(signal-rules design「SC-2/3/5 hub」):**每條規則一顆未改動的
`SignalDetector`**(per-rule `SignalsConfig`,`rule_config()` 映射)。hub 持:

- `_slots`:熱路徑唯一讀取點。CRUD 在鎖內組好完整新 dict,**落檔成功後**才以單一
  賦值替換(dict 賦值原子)—— 任何時刻熱路徑看到的都是自洽快照,落檔失敗則記憶體
  零變更(畫面有、重啟後沒有,是最難查的一種不一致)。
- `_basis_cache` / `_staged_cache`:CDP 基準的**唯一**快照(帶基準日),由 hub 依
  各規則的 `cdp_levels` 過濾後餵給該規則的 detector。基準日不符一律**丟棄**(不寫
  cache、不分發、不餵 None)—— 餵 None 會把 rollover 已 promote 的正確基準洗掉,
  而且不會自癒。

換日順序契約(design §4.1 stage2):`on_rollover` **先逐 slot `reset_day()` 再
promote 暫存區** —— 反了會把剛換上的當日基準洗掉(見 signal_state 模組
docstring)。stage1 (`on_rollover_pending`) 在盤前把次日基準抓進暫存區,
stage2 只做 promote,開盤第一筆 tick 起 CDP 即用當日正確基準。
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server.overlay import compute_cdp
from copycat.signal_rules import (
    MAX_RULES,
    Rule,
    RuleError,
    default_rules,
    load_rules,
    new_rule_id,
    normalize_rule,
    rule_config,
    save_rules,
)
from copycat.signals_config import SignalsConfig
from copycat.stock_watchlist import Group

logger = logging.getLogger(__name__)

__all__ = [
    "DISCORD_QUEUE_MAXSIZE",
    "JSONL_QUEUE_MAXSIZE",
    "SignalHub",
    "format_signal_group_text",
    "format_signal_text",
]

#: jsonl 佇列上限(CC-5):真相源,給大得多的緩衝;測試以 monkeypatch 縮小驗滿載策略。
JSONL_QUEUE_MAXSIZE = 1000
#: Discord 佇列上限(design §4.3):可丟的路徑,滿了丟最舊。
DISCORD_QUEUE_MAXSIZE = 100
#: 關機時等 jsonl worker 把手上與佇列中的訊號寫完的上限
_CLOSE_FLUSH_TIMEOUT = 5.0
_ENABLED_FILE = "signals_enabled.json"
_RULES_FILE = "signal_rules.json"
_SIGNAL_DIR = "signals"
_BASIS_BARS = 5  # CDP 只要最後一根已完成 bar,多抓幾根當緩衝
#: 基準取得**例外**的重試上限(per (code, basis_date, staged));超限才落 None
_BASIS_MAX_RETRIES = 2
_DROP_LOG_EVERY = 20  # 丟棄計數每 N 筆記一次(避免爆量時 log 自己變瓶頸)
_DISCORD_WINDOW_SECS = 60.0
#: 單則 Discord 訊息的字數上限(留在 2000 硬上限之下);超過依 row 分批,不截斷
_DISCORD_MAX_CHARS = 1900
#: 分批時預留給批尾 ` (i/N)` 的字數 —— 批數要切完才知道,先扣掉才不會切出超標的批
_BATCH_TAG_RESERVE = 16

_LEVEL_LABEL = {"cdp": "中軸", "ah": "AH", "nh": "NH", "nl": "NL", "al": "AL"}
_LEVEL_ROLE = {"ah": "壓力", "nh": "壓力", "nl": "支撐", "al": "支撐"}

#: 同群摘要最多印幾檔其他成員(group-grid SC-1);超過就只補一句總數
_GROUP_PEERS = 4


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
    """Discord 文案(bot 與 webhook 同一段,design §4.3)。

    有 `rule_name` 才在文末附規則名(R14b):同 kind 多規則在 Discord 靠它辨識來源;
    升級當日的舊 jsonl row 沒有這個鍵,不得因此留下一個空的分隔符。
    """
    price = row.get("price")
    price_text = f"{price / 1000:.2f}" if isinstance(price, int) else "-"
    who = f"{row.get('name') or ''} {row.get('code', '')}".strip()
    text = f"🔔 {_kind_text(row)}｜{who}｜{price_text}｜{row.get('time', '')}"
    rule_name = row.get("rule_name")
    return f"{text}｜{rule_name}" if rule_name else text


def _dedup(items: list[str]) -> list[str]:
    """保序去重(dict 保插入序):同 kind 兩規則同一 tick 只該印一段文案。"""
    return list(dict.fromkeys(items))


def format_signal_group_text(rows: list[dict[str, Any]]) -> str:
    """同 (code, time) 多則的合併文案(SC-4)。

    單則**逐字**委派給 `format_signal_text` —— 絕大多數訊號走的是這條路,合併版
    自己重組一遍就等於開了第二份格式定義,漂掉時只會在真實推播上看見。

    多則:kind 文案與規則名各自**去重**後以「・」串接(同 kind 兩規則同一 tick 印
    兩段一模一樣的字沒有資訊);`price` / `name` / `code` / `time` 取 rows[0]
    (同一秒同一檔,差別只在最後一筆的價位)。規則名段沿用「有才附」語意。
    """
    if len(rows) == 1:
        return format_signal_text(rows[0])
    head = rows[0]
    price = head.get("price")
    price_text = f"{price / 1000:.2f}" if isinstance(price, int) else "-"
    who = f"{head.get('name') or ''} {head.get('code', '')}".strip()
    kinds = "・".join(_dedup([_kind_text(row) for row in rows]))
    text = f"🔔 {kinds}｜{who}｜{price_text}｜{head.get('time', '')}"
    names = _dedup([str(row["rule_name"]) for row in rows if row.get("rule_name")])
    return f"{text}｜{'・'.join(names)}" if names else text


@dataclass(frozen=True)
class _RuleSlot:
    """規則 / detector / 開關集合是**不可分割**的一組(R2)。

    拆成三個平行 dict 時,熱路徑可能讀到「新規則配舊 detector」的混血快照;
    綁成一顆 frozen slot 之後,替換永遠是整顆換掉。
    """

    rule: Rule
    detector: SignalDetector
    enabled: frozenset[str]  # rule.enabled ? {rule.kind} : frozenset()


def _rule_tag(rule: Rule) -> str:
    """log 用的規則識別:名稱可以改、可以重複,id 才追得回是哪一顆 slot(review A4)。"""
    return f"{rule['name']}({rule['id']})"


def _copy_rule(rule: Rule) -> Rule:
    """對外回傳的規則一律是副本 —— 呼叫端改到的不能是熱路徑正在讀的那份。"""
    out = cast("Rule", dict(rule))
    out["params"] = dict(rule["params"])
    out["cdp_levels"] = list(rule["cdp_levels"])
    return out


def _filter_levels(cdp: dict[str, int] | None, levels: list[str]) -> dict[str, int] | None:
    """規則只訂閱部分 CDP 線 → 只餵那幾條(detector 只認得被餵進去的線)。"""
    if not cdp:
        return None
    picked = {name: cdp[name] for name in levels if name in cdp}
    return picked or None


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
        groups_fn: Callable[[], list[Group]] | None = None,
        quotes_fn: Callable[[], dict[str, tuple[str, float | None]]] | None = None,
    ) -> None:
        self._cfg = cfg
        self._publish = publish
        self._daily_bars = daily_bars
        self._notify_fallback = notify_fallback
        self._data_dir = Path(data_dir)
        self._trade_date_fn = trade_date_fn
        self._now_fn = now_fn
        # 同群摘要(group-grid SC-1/2)。兩者皆 None = 停用 —— 這是**測試預設**,
        # 生產端由 `create_app` 接上;接線測試在 `test_stock_routes` 那一側把關。
        self._groups_fn = groups_fn
        self._quotes_fn = quotes_fn
        self._groups: list[Group] = []
        self._rules_path = self._data_dir / _RULES_FILE
        # 壞規則檔在此往外拋(R9):`app._boot` 傘接手 → hub None + signals routes 503。
        # 靜默套預設會在盤中無預警改變推播行為,所以這裡要大聲。
        self._slots: dict[str, _RuleSlot] = {}
        self._rule_seq = 0  # id 單調計數(R12):刪掉的 id 不回收
        self._load_or_migrate_rules()
        self._rules_lock = asyncio.Lock()  # CRUD 的驗證 + 落檔 + swap 共同臨界區
        self._watch: set[str] = set()
        self._basis_jobs: asyncio.Queue[tuple[str, str, bool]] = asyncio.Queue()
        #: CDP 基準的唯一快照:code → (基準日, cdp);日別是丟棄過期結果的判準(R3)
        self._basis_cache: dict[str, tuple[str, dict[str, int] | None]] = {}
        self._staged_cache: dict[str, dict[str, int] | None] = {}
        self._staged_date: str | None = None  # 當前 stage1 的基準日(過期 job 的判準)
        #: 例外路徑的重試記帳(X-2b):(code, 基準日, staged) → 已排過幾次重試。
        #: 基準日在鍵裡 → 跨日天然作廢,再由 `on_rollover` 清掉舊日別的鍵(不長大)。
        self._basis_retries: dict[tuple[str, str, bool], int] = {}
        #: 在途的延遲重試(同一個鍵最多一筆:基準 worker 是序列的)。close() 要能
        #: 全部取消 —— 關機後才觸發的 callback 會往一條再也沒有 worker 的佇列塞件。
        self._retry_handles: dict[tuple[str, str, bool], asyncio.TimerHandle] = {}
        # 兩條獨立佇列 + 兩個 worker(CC-5):Discord 卡住時 jsonl 這條真相源要照走
        self._jsonl_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=JSONL_QUEUE_MAXSIZE)
        self._discord_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=DISCORD_QUEUE_MAXSIZE)
        self._tasks: list[asyncio.Task[None]] = []
        self._jsonl_task: asyncio.Task[None] | None = None
        self._closing = False
        #: Discord worker 的單槽緩衝(SC-4):取到不同 (code, time) 的那一則存這裡,
        #: 下一輪當 head。回塞佇列會排到隊尾 → 順序亂掉,所以只能存在槽裡。
        self._discord_pending: dict | None = None
        self._discord_sender: Callable[[str], Any] | None = None
        self._discord_sent: deque[_dt.datetime] = deque()
        self.dropped_jsonl = 0
        self.dropped_discord = 0

    @property
    def dropped(self) -> int:
        return self.dropped_jsonl + self.dropped_discord

    @property
    def trade_date(self) -> str:
        """引擎日別(唯讀,AR6):`today_signals()` 讀的兩個日別之一,給 today 端點掛出去。

        route 直接讀屬性而不是自己算日期 —— hub 內外算法一旦分家,端點回報的日別會跟
        實際讀的那個檔悄悄不同(rollover 前後最容易發生),而畫面看起來完全正常。
        """
        return self._trade_date_fn()

    @property
    def today(self) -> str:
        """牆鐘日(唯讀,AR7):與 `today_signals()` 取聯集用的**同一顆**時鐘(`_now_fn`)。

        與 `trade_date` 兩次取樣中間可能夾著 rollover stage2(錯位一拍),差別只是
        標題晚一拍更新,可接受;換成別的時鐘則會整天不一致。
        """
        return self._now_fn().date().isoformat()

    # ---- 規則(SC-2)----

    def _load_or_migrate_rules(self) -> None:
        """三態(`load_rules`):缺檔 → 由既有全域設定 + 舊開關檔生成預設並落檔;
        合法(含空陣列)→ 照用(使用者刪光規則不得復活預設);壞檔 → 往外拋。
        """
        rules = load_rules(self._rules_path)
        if rules is None:
            rules = default_rules(self._cfg, self._legacy_flags())
            save_rules(self._rules_path, rules)  # OSError 往外拋:記憶體不得先於落檔
            logger.info("訊號規則檔不存在,已由現行設定生成 %d 條預設規則", len(rules))
        self._slots = {rule["id"]: self._make_slot(rule) for rule in rules}
        self._rule_seq = len(rules)

    def _make_slot(self, rule: Rule) -> _RuleSlot:
        """建 detector 的**唯一**入口(R5):初始化 / 遷移 / upsert 三處同式,
        漏帶 `now_fn` 的那一顆會偷用真實時鐘,而測試與盤後重放都看不出來。
        """
        return _RuleSlot(
            rule=rule,
            detector=SignalDetector(rule_config(rule, self._cfg), now_fn=self._now_fn),
            enabled=frozenset({rule["kind"]}) if rule["enabled"] else frozenset(),
        )

    def rules(self) -> list[Rule]:
        return [_copy_rule(slot.rule) for slot in self._slots.values()]

    async def upsert_rule(self, payload: dict[str, Any], rule_id: str | None = None) -> Rule:
        """`rule_id` None = 新增(配新 id),否則 = 編輯(缺 → RULE_NOT_FOUND)。

        順序(R17):鎖內驗證 → 落檔 → **同一個不含 await 的同步區塊**內 swap `_slots`
        並 seed 新 slot。seed 與 swap 之間插不進 basis worker,新 slot 必帶最新快照;
        落檔失敗則記憶體零變更、例外往外拋(route 轉 500 RULE_SAVE_FAILED)。
        """
        async with self._rules_lock:
            current = {rid: slot.rule for rid, slot in self._slots.items()}
            seq = self._rule_seq
            if rule_id is None:
                if len(current) >= MAX_RULES:
                    logger.warning("規則數已達上限 %d,拒絕新增", MAX_RULES)
                    raise RuleError("INVALID_RULE")
                epoch = int(self._now_fn().timestamp())
                target = new_rule_id(epoch, seq)
                while target in current:  # 同秒多次新增 / 匯入過的 id:單調往前找
                    seq += 1
                    target = new_rule_id(epoch, seq)
            elif rule_id not in current:
                raise RuleError("RULE_NOT_FOUND")
            else:
                target = rule_id
            others = {rid: r for rid, r in current.items() if rid != target}
            rule = normalize_rule(cast("Rule", {**payload, "id": target}), others)
            slot = self._make_slot(rule)

            merged = dict(current)
            merged[target] = rule
            await asyncio.to_thread(save_rules, self._rules_path, list(merged.values()))

            slots = dict(self._slots)
            slots[target] = slot
            self._slots = slots
            if rule_id is None:
                self._rule_seq = seq + 1
            self._seed_slot(slot)
            return _copy_rule(rule)

    async def delete_rule(self, rule_id: str) -> None:
        async with self._rules_lock:
            if rule_id not in self._slots:
                raise RuleError("RULE_NOT_FOUND")
            remaining = [slot.rule for rid, slot in self._slots.items() if rid != rule_id]
            await asyncio.to_thread(save_rules, self._rules_path, remaining)
            slots = dict(self._slots)
            slots.pop(rule_id, None)
            self._slots = slots

    def _seed_slot(self, slot: _RuleSlot) -> None:
        """upsert 的反向軸(R17):新 detector 補上已在手的當日基準。

        沒有這一步,盤中編輯規則等於把該規則的 CDP 停到隔天 —— 而畫面只會顯示
        「這條規則今天都沒發」,沒有任何錯誤訊號。
        """
        if slot.rule["kind"] != "cdp_cross":
            return
        today = self._trade_date_fn()
        for code, (basis_date, cdp) in self._basis_cache.items():
            if basis_date != today:
                continue
            slot.detector.set_basis(code, _filter_levels(cdp, slot.rule["cdp_levels"]))

    # ---- 生命週期 ----

    async def start(self) -> None:
        if self._tasks:
            return
        self._jsonl_task = asyncio.create_task(self._jsonl_worker())
        self._tasks.append(asyncio.create_task(self._basis_worker()))
        self._tasks.append(self._jsonl_task)
        self._tasks.append(asyncio.create_task(self._discord_worker()))

    async def close(self) -> None:
        """先停收件 → 等 jsonl 佇列排空 → 才取消 worker;Discord 佇列直接放棄。

        `join()` 先於 `cancel()` 是零漏的關鍵(CC-5):worker 手上那一則已經 `get()` 出來
        但還沒寫完,先取消就沒有任何地方找得回它(`_flush_pending` 只掃得到還在佇列裡的)。
        """
        self._closing = True
        for handle in self._retry_handles.values():
            handle.cancel()  # 在途的基準重試:關機後入列的 job 永遠不會有人消化
        self._retry_handles.clear()
        jsonl_task = self._jsonl_task
        if jsonl_task is not None and not jsonl_task.done():
            try:
                await asyncio.wait_for(self._jsonl_queue.join(), _CLOSE_FLUSH_TIMEOUT)
            except TimeoutError:
                logger.error("關機落檔逾時,剩餘 %d 筆改走盡力落檔", self._jsonl_queue.qsize())
        tasks = list(self._tasks)
        self._tasks.clear()
        self._jsonl_task = None
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._discard_discord_pending()
        await self._flush_pending()  # worker 沒起來(或逾時)時的保底

    def _discard_discord_pending(self) -> None:
        """單槽 pending 已 `get()` 未 `task_done()`,worker 一取消它就無人記帳。

        少記那一格 `_discord_queue.join()` 就永遠不返回(關機屏障吊死);Discord
        關機本來就放棄不送,所以是「記帳 + 留痕」而不是補送 —— 丟掉的是哪一則要在
        log 找得回來。
        """
        pending = self._discord_pending
        if pending is None:
            return
        self._discord_pending = None
        logger.info("關機丟棄 Discord 待合併訊號:%s", pending.get("id"))
        self._discord_queue.task_done()

    def attach_discord(self, sender: Callable[[str], Any]) -> None:
        """sender 可為同步或 async(`bot.send_signal`);回傳 falsy = 未送出。"""
        self._discord_sender = sender

    # ---- engine 掛點 ----

    def on_tick(self, code: str, tick: StockTick, state: StockDayState) -> None:
        if code not in self._watch:
            return
        try:
            ctx = self._context(state, tick.cum_vol)  # ctx 每 tick 一次,全規則共用
        except Exception:
            # engine 熱路徑不可被訊號層汙染:丟棄這一筆評估,tick 本身照常走完
            logger.exception("訊號 ctx 組建失敗(丟棄該 tick):%s", code)
            return
        for slot in self._slots.values():
            try:
                events = list(slot.detector.evaluate(code, tick, ctx, slot.enabled))
            except Exception:
                # per-rule 隔離(R1):一條規則炸掉只跳過它自己這一 tick,其餘照評
                logger.exception("訊號規則評估失敗(丟棄):%s / %s", code, _rule_tag(slot.rule))
                continue
            self._fanout(code, slot, events, state)

    def on_book(self, code: str, state: StockDayState) -> None:
        if code not in self._watch:
            return
        try:
            ctx = self._context(state, 0)  # 簿路只評估鎖板 kind,不會用到 day_volume
        except Exception:
            logger.exception("簿更新 ctx 組建失敗(丟棄):%s", code)
            return
        for slot in self._slots.values():
            try:
                events = list(slot.detector.evaluate_book(code, ctx, slot.enabled))
            except Exception:
                logger.exception("簿更新規則評估失敗(丟棄):%s / %s", code, _rule_tag(slot.rule))
                continue
            self._fanout(code, slot, events, state)

    def _fanout(
        self, code: str, slot: _RuleSlot, events: list[SignalEvent], state: StockDayState
    ) -> None:
        """evaluate 與 fanout 分開接(review A4):兩者的失敗語意完全不同 ——
        前者是「這條規則的判定壞了」(狀態機可能已半推進),後者是「這一則送不出去」。
        合在同一個 try 時,fanout 炸掉會讓同 tick 剩下的事件連帶被吞,而 log 會指向
        detector,排查從一開始就走錯方向。
        """
        for event in events:
            try:
                self._emit(event, slot.rule, state)
            except Exception:
                logger.exception("訊號 fanout 失敗(丟棄該則):%s / %s", code, _rule_tag(slot.rule))

    def on_rollover_pending(self, new_date: str) -> None:
        """stage1(盤前):以次日為基準日預抓進暫存區,stage2 只做 promote。

        **先清暫存區**(MFS-2):快路徑(pending 與 stage2 同一輪 loop 連發)會讓 stage1
        的 job 在 promote 之後才被 worker 消化,結果留在暫存區到下一輪換日;不清掉的話
        下一次 promote 會成立並把舊日基準當當日基準用一整天,零錯誤訊號。
        """
        self._staged_cache.clear()
        self._staged_date = new_date
        self.request_basis(sorted(self._watch), basis_date=new_date, staged=True)

    def on_rollover(self) -> None:
        expected = self._trade_date_fn()  # engine 已前進到新日別(stage2 契約)
        # 重試記帳的日別作廢:新的一天是新的鍵,舊日別的計數再也不會被讀到 ——
        # 不清的話這張表會隨開機天數單調長大(長駐 server 的慢性洩漏)。staged 鍵
        # 一併作廢:方法尾端 `_staged_date` 歸 None,staged 尺此後恆過期,連
        # 「基準日 = 新日別」的 staged 鍵也是死條目,同一把尺清 timer 與計數。
        self._basis_retries = {
            k: v for k, v in self._basis_retries.items() if k[1] == expected and not k[2]
        }
        # 在途重試 timer 同尺取消:醒來也只會被 `_stale` 丟掉,但那是白走一趟
        # 換日這個最忙窗的佇列;close() 的全清是關機路徑,換日要自己清自己的。
        for k in [k for k in self._retry_handles if k[1] != expected or k[2]]:
            self._retry_handles.pop(k).cancel()
        for slot in self._slots.values():
            slot.detector.reset_day()  # 順序契約:reset 會清 _basis,必須先於 promote
        if self._staged_cache and self._staged_date == expected:
            self._basis_cache = {code: (expected, cdp) for code, cdp in self._staged_cache.items()}
            for code in self._basis_cache:
                self._distribute(code)
            # promote 是**整批取代**:暫存區沒抓到的檔等於基準被刪掉,而它們排在
            # 換日前的當日 job 隨後會被日別尺丟棄 → 那些檔整天沒有 CDP 且不自癒。
            # 此刻 trade_date 已前進,補抓拿到的就是當日基準(R18 不會丟掉它)。
            missing = sorted(set(self._watch) - set(self._basis_cache))
            if missing:
                logger.info("換日 promote 差集補抓 %d 檔基準:%s", len(missing), missing)
                self.request_basis(missing)
        else:
            # stage1 沒跑過(週六補市日 / server 盤中才啟動)→ 重抓;該窗 CDP 停用
            logger.info("換日無預抓基準,清空重抓(design §4.2 fallback)")
            self._basis_cache.clear()
            self.request_basis(sorted(self._watch))
        self._staged_cache.clear()
        self._staged_date = None

    def on_watchlist(self, codes: list[str]) -> None:
        self._refresh_groups()
        new = set(codes)
        added = new - self._watch
        removed = self._watch - new
        self._watch = new
        for code in sorted(removed):
            self._drop_code(code)
        if added:
            self.request_basis(sorted(added))
            if self._staged_date is not None:
                # stage1 已經跑過(盤前窗內)才加進來的檔:**加排**一筆暫存 job,
                # 否則 stage2 整批取代時它不在暫存區,隔天一整天沒有基準。
                # 當日那筆照排不動 —— 今天剩下的時間仍要有 CDP。
                self.request_basis(sorted(added), basis_date=self._staged_date, staged=True)

    def _refresh_groups(self) -> None:
        """群組結構跟著自選一起更新(SC-2)。

        `groups_fn` 生產端是讀自選檔 —— 失敗時**保舊值**而不是清空:membership 這一邊
        照樣更新完,清空只會讓摘要從此永久消失,而畫面上完全看不出來(Discord 只是
        少了一段尾巴)。舊群組頂多是「上一次的分組」,比沒有好。
        """
        if self._groups_fn is None:
            return
        try:
            self._groups = self._groups_fn()
        except Exception:
            logger.exception("群組結構讀取失敗,同群摘要沿用上一份(%d 組)", len(self._groups))

    def _group_suffix(self, row: dict[str, Any]) -> str:
        """同群摘要(SC-1)。在 **Discord worker** 呼叫 —— 離熱路徑,quotes 取的是
        「發送當下」的快照(訊號產生到送出之間的價差可接受,拿的是最新的更有用)。

        回空字串的三種正常情況:兩 fn 未注入 / code 不屬任何群組(未分組是衍生桶不是
        群組)/ 群組只有觸發者自己。一檔可屬多群組 → 取**群組序**第一個含它的。

        排序鍵 `(chg is None, -abs(chg))`:無行情的排最後 —— 摘要要回答的是「同群
        今天有沒有一起動」,一個還沒開盤的成員排在第一位等於把版面讓給零資訊。

        整段 never-raise:摘要是通知的**裝飾**,它壞掉不得讓訊號本身消失(WS/jsonl
        有而 Discord 沒有,對照時最容易被誤判成 Discord 掛了)。
        """
        quotes_fn = self._quotes_fn
        if quotes_fn is None or self._groups_fn is None:
            return ""
        try:
            code = str(row.get("code", ""))
            group = next((g for g in self._groups if code in g["codes"]), None)
            if group is None:
                return ""
            peers = [c for c in group["codes"] if c != code]
            if not peers:
                return ""
            quotes = quotes_fn()
            peers.sort(key=lambda c: _peer_sort_key(quotes.get(c)))
            shown = "、".join(_peer_text(c, quotes.get(c)) for c in peers[:_GROUP_PEERS])
            total = len(group["codes"])
            tail = f"、…共 {total} 檔" if total > _GROUP_PEERS + 1 else ""
            return f"｜同群 {group['name']}:{shown}{tail}"
        except Exception:
            logger.exception("同群摘要組裝失敗(通知照送):%s", row.get("id"))
            return ""

    def _drop_code(self, code: str) -> None:
        """SC-5:逐 slot 丟 + 雙 cache pop —— 漏掉 cache 的話重新加入時
        `_seed_slot` 會拿舊快照當當日基準,而那份可能已經是別天的。
        """
        for slot in self._slots.values():
            slot.detector.drop_code(code)
        self._basis_cache.pop(code, None)
        self._staged_cache.pop(code, None)
        # 在途重試會在移出後才醒來:重打 TC4 事小,`_basis_failed` 還會把上面剛清掉
        # 的 cache 條目寫回去(復活成 (date, None))。計數一併清 —— 重新加入是使用者
        # 驅動的新機會,不背舊帳。已在佇列裡的 job 攔不到(秒級窗,`_stale` 之外無
        # 名單 gate;與 stock_engine A-1 殘留窗同構,不值得為它加新不變式)。
        for k in [k for k in self._retry_handles if k[0] == code]:
            self._retry_handles.pop(k).cancel()
        for k in [k for k in self._basis_retries if k[0] == code]:
            del self._basis_retries[k]

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
            fetched = True  # 例外路徑落點未知 → 保守付 gap(下方只用來省掉早退那一格)
            try:
                fetched = await self._resolve_basis(code, basis_date, staged)
            except asyncio.CancelledError:
                raise  # finally 仍會 task_done,取消不留未完成計數
            except Exception:
                # worker 死掉 = 之後所有基準靜默停用(stock_engine._backfill_worker CR4 同款)
                logger.exception("CDP 基準解析未預期失敗,%s 停用 CDP", code)
                self._basis_failed(code, basis_date, staged)
            finally:
                self._basis_jobs.task_done()
            if fetched and self._cfg.basis_gap_secs > 0:
                # 與主圖回補 / K 線 route 共用同一條 TC4 stock session,連發要讓位。
                # 沒打日 K 的那一格(過期早退)不必付 —— 一批過期 job 會把 gap 疊成分鐘級。
                await asyncio.sleep(self._cfg.basis_gap_secs)

    def _stale(self, basis_date: str, staged: bool) -> bool:
        """日別尺的**唯一**定義:staged 比暫存區的基準日,非 staged 比當日。

        成功 / 失敗 / 早退三條路徑共用同一把尺 —— 分開寫的那次,例外路徑就漏了它。
        """
        return basis_date != (self._staged_date if staged else self._trade_date_fn())

    def _schedule_basis_retry(self, code: str, basis_date: str, staged: bool) -> bool:
        """例外路徑的有限重試(X-2b)。回傳「有沒有排到重試」—— False = 已達上限,
        呼叫端照舊落 None。

        **只有例外走這裡**(連線 / 傳輸層,暫時性):落 None 是**整天**的決定,而
        basis sweep 逐檔間隔只有 0.2s —— 一次連線抖動(例:REQ 棄連線級聯)可以在
        數秒內把十幾檔的 CDP 停掉一整天,而畫面只是「那條規則今天都沒發」。反過來
        「日 K 回空」是資料面的答案(新上市無歷史),重抓一百次也一樣,不得重試。

        重試 job 走**同一條佇列**且帶原 `basis_date`/`staged` → `_stale` 這把既有的
        尺自然擋掉跨日殘留,不必另立一套過期判定。
        """
        if self._closing:
            return False
        key = (code, basis_date, staged)
        tries = self._basis_retries.get(key, 0)
        if tries >= _BASIS_MAX_RETRIES:
            logger.warning("CDP 基準連續失敗 %d 次,%s 當日停用 CDP", tries + 1, code)
            return False
        self._basis_retries[key] = tries + 1
        delay = self._cfg.basis_retry_delay_secs
        old = self._retry_handles.get(key)
        if old is not None:
            # 同鍵兩筆 job 先後失敗(rollover 差集補抓 / 同檔重複 request 都造得出
            # 同鍵並存的 job):不取消就成孤兒 timer —— 照樣醒來多打 TC4,先醒的那支
            # 還會走到 cap 路徑把重試記帳 pop 歸零,兩支孤兒互相回充預算接近乒乓;
            # 且孤兒 `_requeue_basis` pop 掉 dict 條目後,close() 再也看不到在途的那支。
            old.cancel()
        handle = asyncio.get_running_loop().call_later(delay, self._requeue_basis, key)
        self._retry_handles[key] = handle
        logger.info(
            "CDP 基準取得失敗,%.0fs 後重試(第 %d 次):%s(%s,staged=%s)",
            delay,
            tries + 1,
            code,
            basis_date,
            staged,
        )
        return True

    def _requeue_basis(self, key: tuple[str, str, bool]) -> None:
        """延遲到期:把原封不動的 job 放回佇列(過期與否由 worker 的 `_stale` 判)。"""
        self._retry_handles.pop(key, None)
        if self._closing:
            return
        self._basis_jobs.put_nowait(key)

    def _basis_failed(self, code: str, basis_date: str, staged: bool) -> None:
        """未預期失敗的收斂點(review A1+B2):日別符才落 None,且**經由 cache**。

        繞過 cache 直摸 detector 有兩個獨立的坑:(a) 沒有日別尺 —— 一則 stage1
        (次日)或 promote 前排下的舊 job 崩掉,就把當日基準停掉;(b) cache 仍寫著
        舊值 → 之後任何 `_distribute` 都會把它再餵回去,兩份真值就此分岔。

        日別符時**先試重試**(X-2b:worker 級未預期例外同屬暫時性失敗那一類),
        超限才落 None。
        """
        if self._stale(basis_date, staged):
            logger.info("捨棄過期基準 job 的失敗結果:%s(%s,staged=%s)", code, basis_date, staged)
            return
        if self._schedule_basis_retry(code, basis_date, staged):
            return
        if staged:
            self._staged_cache[code] = None
            return
        self._basis_cache[code] = (basis_date, None)
        self._distribute(code)

    async def _resolve_basis(self, code: str, basis_date: str, staged: bool) -> bool:
        """回傳「有沒有真的打一次日 K」—— worker 據此決定要不要付 gap sleep。"""
        if self._stale(basis_date, staged):
            # 排進佇列後、輪到它之前就換日了 → 連 TC4 都不必打(review A3)
            logger.info("捨棄過期的基準 job:%s(%s,staged=%s)", code, basis_date, staged)
            return False
        try:
            bars = await self._daily_bars(code, _BASIS_BARS)
        except Exception as exc:
            # 具體處理 = 有限重試(X-2b,收窄 design §4.2),超限才落 None
            # (CDP 跳過、其他 kind 照常)。過期的失敗不排重試 —— 日別都換了,
            # 這則 job 的答案已經沒有人要。
            if isinstance(exc, HistoryTimeoutError):
                # 逾時是**預期中的暫時態**(TC4 首頁還沒備妥,不是 TC4 掛了):堆疊每次
                # 都是同一條 `to_thread` → raise,零資訊量。盤前 basis sweep 逐檔 0.2s,
                # TC4 忙窗一來就是幾十份 traceback,把真正該看的例外(型別錯 / 解析爆)
                # 整段沖掉 —— 而那正是 traceback 唯一有用的場合。
                # **處置完全相同**,差別只有 log 等級與有沒有 traceback。
                logger.warning("CDP 基準日 K 逾時(非 TC4 down):%s(%s)", code, exc)
            else:
                logger.exception("CDP 基準日 K 取得失敗:%s", code)
            if not self._stale(basis_date, staged) and self._schedule_basis_retry(
                code, basis_date, staged
            ):
                return True
            bars = []
        done = [b for b in bars if b["date"] < basis_date]  # 今日 partial bar 不得入計算
        cdp: dict[str, int] | None = None
        if done:
            last = done[-1]
            cdp = compute_cdp(last["high"], last["low"], last["close"])
        else:
            logger.warning("%s 無 %s 之前的已完成日 K,CDP 停用", code, basis_date)
        # 走到這裡 = 這則 job 已經產出答案(含「資料面就是沒有」):抖動過去了,重試
        # 記帳歸零。**不可提前到取得 bars 之後** —— 那之後還有 `compute_cdp`,它每次
        # 都炸的話計數會被歸零成無限重試(這正是本輪先寫錯再被既有測試抓到的那條)。
        self._basis_retries.pop((code, basis_date, staged), None)
        if self._stale(basis_date, staged):
            # 打日 K 的期間換了日別(staged:暫存區已清空 MFS-2;非 staged:promote 走完
            # R18)→ **丟棄**。餵進去等於把舊日別的基準當今天用,而且整天不會自癒。
            logger.info("捨棄過期的基準結果:%s(%s,staged=%s)", code, basis_date, staged)
            return True
        if staged:
            self._staged_cache[code] = cdp
            return True
        self._basis_cache[code] = (basis_date, cdp)
        self._distribute(code)
        return True

    def _distribute(self, code: str) -> None:
        """把快照餵給每條 CDP 規則(levels 過濾 + 日別 guard,冪等)。

        日別 guard 在此**再判一次**(review A6(5)):呼叫點有四處,漏一處的失效樣態
        是「昨天的基準被當成今天的用一整天」,而那是靜默的。
        """
        entry = self._basis_cache.get(code)
        if entry is None:
            return
        basis_date, cdp = entry
        if basis_date != self._trade_date_fn():
            logger.warning("basis cache 日別不符,不分發:%s(%s)", code, basis_date)
            return
        for slot in self._slots.values():
            if slot.rule["kind"] != "cdp_cross":
                continue
            slot.detector.set_basis(code, _filter_levels(cdp, slot.rule["cdp_levels"]))

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

    def _emit(self, event: SignalEvent, rule: Rule, state: StockDayState) -> None:
        trade_date = self._trade_date_fn()
        payload = {
            "type": "signal",
            "id": _event_id(trade_date, rule["id"], event),
            "rule_id": rule["id"],
            "rule_name": rule["name"],
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
        self._enqueue({**payload, "trade_date": trade_date}, notify=rule["notify_discord"])

    def _enqueue(self, row: dict, *, notify: bool) -> None:
        """`notify` 只擋 Discord:jsonl 是歷史真相源,關通知不等於不留紀錄。"""
        if self._closing:  # 關機已開始:再收件就永遠不會被寫出去
            return
        if _put_drop_oldest(self._jsonl_queue, row):
            self.dropped_jsonl += 1
            if self.dropped_jsonl % _DROP_LOG_EVERY == 1:
                logger.warning(
                    "訊號 jsonl 佇列滿,已丟棄 %d 筆(WS 不受影響)", self.dropped_jsonl
                )
        if not notify:
            return
        if _put_drop_oldest(self._discord_queue, row):
            self.dropped_discord += 1
            if self.dropped_discord % _DROP_LOG_EVERY == 1:
                logger.warning(
                    "Discord 佇列滿,已丟棄 %d 筆(WS/jsonl 不受影響)", self.dropped_discord
                )

    async def _jsonl_worker(self) -> None:
        while True:
            row = await self._jsonl_queue.get()
            try:
                await asyncio.to_thread(self._append_jsonl, row)
            except asyncio.CancelledError:
                raise  # finally 仍會 task_done
            except Exception:
                logger.exception("訊號 jsonl 落檔失敗(worker 續行):%s", row.get("id"))
            finally:
                self._jsonl_queue.task_done()

    async def _discord_worker(self) -> None:
        """同 (code, time) 且**相鄰**的多 row 合成一則送出(SC-4)。

        單槽 `_discord_pending`:取到不同組的那一則時把它**存起來**(不回塞佇列 ——
        `put_nowait` 會排到隊尾,順序就亂了),下一輪直接當 head,不再 `get()`。

        `task_done()` 一律在**送出之後**、batch 內每 row 恰一次;pending 那則要等它
        自己當 head 送完才記。少記一格 `join()` 永遠不返回(關機卡住),多記一格則
        `task_done() called too many times` 當場打死 worker(之後整天 Discord 無聲,
        而 WS/jsonl 都正常)—— 兩種失效都不會指向這裡。
        """
        while True:
            head = self._discord_pending
            if head is None:
                head = await self._discord_queue.get()
            else:
                self._discord_pending = None
            batch = [head]
            while True:
                try:
                    row = self._discord_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if _same_tick(row, head):
                    batch.append(row)
                else:
                    self._discord_pending = row
                    break
            try:
                await self._send_discord(batch)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Discord 發送失敗(worker 續行):%s", head.get("id"))
            finally:
                for _ in batch:
                    self._discord_queue.task_done()

    async def _flush_pending(self) -> None:
        """關機盡力落檔:jsonl 是歷史真相源,Discord 這時不再送。"""
        rows: list[dict] = []
        while True:
            try:
                rows.append(self._jsonl_queue.get_nowait())
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
        """讀取日集合 = {engine 日別, 牆鐘日}(R2-3);通常同一天 = **單檔讀**。

        寫檔的日別有兩個來源(XR-3):engine 在場時走 engine 的 trade_date,engine
        缺席時 hub 以牆鐘為日別。而 engine 的 trade_date 只在 stage2(當日首 tick)
        前進 —— 空自選 / 訂閱零推播時它會靜默停在昨日,於是同一天內兩種來源可能落在
        不同的檔。取聯集讓 today 端點兩邊都看得到,不必去猜這一輪是誰寫的。

        兩日不同時依**日期字串升冪**串接(舊日在前)並以 `id` 去重、保檔內順序。
        同日走單檔讀而不是「聯集後去重」:當日檔本來就可能有同 id 兩列(重啟後重發
        同一事件,SC-7 的決定性鍵),無條件去重會把那一列吃掉 —— 既有行為必須逐字不變。
        """
        dates = {self._trade_date_fn(), self._now_fn().date().isoformat()}
        if len(dates) == 1:
            return self.read_signals(dates.pop())
        rows: list[dict] = []
        seen: set[str] = set()
        for date in sorted(dates):
            for row in self.read_signals(date):
                key = row.get("id")
                if isinstance(key, str):
                    if key in seen:
                        continue
                    seen.add(key)
                rows.append(row)
        return rows

    def read_signals(self, trade_date: str) -> list[dict]:
        """當日 jsonl → row 清單;壞行跳過(半寫入的最後一行不該讓整條端點掛掉)。

        `errors="replace"` 而非嚴格解碼:半寫入切在中文多位元組序列中間時嚴格解碼丟
        `UnicodeDecodeError`(ValueError 系,**不在** `except OSError` 內)→ 整個當日檔
        一起消失,兩條消費路(today 端點 / 前端自癒)整天壞著。
        壞位元組換成 U+FFFD 後只有那一行 `json.loads` 失敗、被既有「壞行跳過」吃掉,
        好行全數保留 —— 把 except 擴成 `(OSError, ValueError)` 則是整檔丟掉,更差
        (review round-2 HR-1)。
        """
        path = self._signal_path(trade_date)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
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

    async def _send_discord(self, rows: list[dict]) -> None:
        """一組(已確認同 code 同 time)row → 一則訊息;超長才依 row 分批。

        分批的每一批**各計一次節流**(它們是各自獨立的一則訊息);後續批被擋下時
        缺角要在 log 看得見 —— 截斷是更差的選項:被砍掉的那幾則在任何地方都不留痕。
        """
        head = rows[0]
        # 摘要**只接在 Discord 這一段**:WS/jsonl 是歷史真相源,格式不隨通知裝飾漂移
        suffix = self._group_suffix(head)
        text = format_signal_group_text(rows) + suffix
        if len(rows) == 1 or len(text) <= _DISCORD_MAX_CHARS:
            if not self._allow_discord():
                # 合併之後「一則」不等於「一筆訊號」:`_allow_discord` 那句「本則」
                # 看不出缺角有多大,也認不出是哪一組(C-5)
                if len(rows) > 1:
                    logger.warning("Discord 節流擋下合併 %d 則:%s", len(rows), head.get("id"))
                return
            await self._send_text(text, head)
            return
        batches = _split_batches(rows, suffix)
        total = len(batches)
        blocked = 0
        for index, batch in enumerate(batches, 1):
            if not self._allow_discord():
                blocked += 1
                continue
            await self._send_text(
                f"{format_signal_group_text(batch)}{suffix} ({index}/{total})", head
            )
        if blocked:
            logger.warning(
                "Discord 合併訊息分 %d 批,其中 %d 批被節流擋下(缺角):%s",
                total,
                blocked,
                head.get("id"),
            )

    async def _send_text(self, text: str, row: dict) -> None:
        """單則送出:bot 優先,未送出 / 例外都降級走 webhook(log 用 row 的 id 追)。"""
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

    # ---- 舊四鍵開關檔(**唯讀**的遷移來源)----

    def _enabled_path(self) -> Path:
        return self._data_dir / _ENABLED_FILE

    def _legacy_flags(self) -> dict[str, bool]:
        """舊四鍵開關檔(遷移專用來源;fail-open 全開)。

        規則化之後這份**只在「規則檔不存在」時被讀一次**,用來決定四條種子規則的
        `enabled`;之後永遠不再回頭讀它。setter 與 route 已隨開關家族退役,這個檔
        從此唯讀 —— 留著只為了讓既有部署的關閉態能跟著遷移過來。
        """
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


def _peer_sort_key(quote: tuple[str, float | None] | None) -> tuple[bool, float]:
    """同群成員排序(SC-1):|漲跌幅| 降冪,**無行情一律墊底**。

    第一位是 bool 而不是把 None 當 0:當 0 排的話「還沒開盤」會混進平盤那一區,
    而那兩件事對「同群有沒有一起動」的判讀完全不同。
    """
    chg = quote[1] if quote is not None else None
    return (chg is None, -abs(chg or 0.0))


def _peer_text(code: str, quote: tuple[str, float | None] | None) -> str:
    """`{代碼}{名稱} {+x.x%}`;名稱缺(盤前 / 未訂閱)→ 只印代碼,不留尾隨空白。"""
    name, chg = quote if quote is not None else ("", None)
    return f"{code}{name} {'-' if chg is None else f'{chg:+.1f}%'}"


def _same_tick(row: dict, head: dict) -> bool:
    """合併粒度(D4):同 code + 同 `time`(秒)。row 不帶 time_key,秒是能拿到的最細。"""
    return row.get("code") == head.get("code") and row.get("time") == head.get("time")


def _split_batches(rows: list[dict], suffix: str) -> list[list[dict]]:
    """依 row 貪婪切批,每批(含摘要與批尾標記的預留)不超過上限(edge 8)。

    切不動的單 row(自己就超長)照樣自成一批送出 —— 現況本來就沒有截斷,本輪不改。
    """
    limit = _DISCORD_MAX_CHARS - _BATCH_TAG_RESERVE
    batches: list[list[dict]] = []
    current: list[dict] = []
    for row in rows:
        candidate = [*current, row]
        if current and len(format_signal_group_text(candidate)) + len(suffix) > limit:
            batches.append(current)
            current = [row]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def _put_drop_oldest(queue: asyncio.Queue[dict], row: dict) -> bool:
    """有界佇列滿載策略(design R14):丟最舊再放入,熱路徑零反壓。回傳「是否丟了一筆」。"""
    try:
        queue.put_nowait(row)
        return False
    except asyncio.QueueFull:
        pass
    with contextlib.suppress(asyncio.QueueEmpty):
        queue.get_nowait()  # 新訊號比舊訊號值錢
        queue.task_done()
    try:
        queue.put_nowait(row)
    except asyncio.QueueFull:
        logger.error("訊號佇列騰位失敗,丟棄 %s", row.get("id"))
    return True


def _event_id(trade_date: str, rule_id: str, event: SignalEvent) -> str:
    """決定性鍵(design §4.3 R1):不依賴 process 記憶 → 重啟後同一事件同 id。

    `rule_id` 是必要的一段:同 kind 兩條規則同一 tick 各發一則,少了它兩則同 id,
    前端去重會把第二則整個吃掉(signal-rules 邊界 2)。
    """
    tag = "+".join(event.levels) or event.direction or "-"
    return f"{trade_date}-{rule_id}-{event.code}-{event.kind}-{tag}-{event.time_key}"
