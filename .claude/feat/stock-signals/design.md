# Design:個股即時訊號(stock-signals)v3

對應 `brainstorm.md`(2026-08-04 拍板)。SC 對應見 §10。

## Changelog

- v3(2026-08-04):限縮 round 2(P1×4 / P2×6)修入 — R2-1 `time_key` 毫秒欄 +
  簿路事件時刻定義(§3.1、§3.5、§4.3)/ R2-2 on_book 呼叫點移 `_handle_quote` 尾端
  + 換日 pending 跳過(§4.1)/ R2-3 lifespan 改 `_boot` 隔離(§4.5)/
  R2-4 基準預抓提前 stage1、stage2 只 swap(§4.1、§4.2)/ R2-5 TickContext 補對稱
  欄位(§3.1)/ R2-6 touch_count 合併語意(§3.2)/ R2-7 levels 固定序(§3.2)/
  R2-8 全域節流改只作用 Discord(§4.3)/ R2-9 鎖停簽名說明更正(§3.5)/
  R2-10 零寫早退回傳 canonical 現況(§6)。
- v2(2026-08-04):design-review round 1(P0×1 / P1×8 / P2×13)全數修入 —
  R1 訊號 id 改決定性鍵(§4.3)/ R2 狀態推進與事件產出分離(§3.1、§3.6)/
  R3 rollover 同步清基準(§4.1、§4.2)/ R4 rearm 毫元化 + `tick_size_milli`(§3.2)/
  R5 membership gate(§4.1)/ R6 lifespan 序列明定(§4.5)/
  R7 同 tick 合併 + 全域上限 + toast 上限(§3.2、§4.3、§8.3)/
  R8 trade_date gate(§3.1)/ R9 鎖停複合簽名(§3.5)/
  R10 爆量地板(§3.4)/ R11 時間軸單一化(§3.1)/ R12 day_volume=cum_vol(§3.1)/
  R13 jsonl 入佇列 worker(§4.3)/ R14 端點改名 + 503 閘(§7)/ R15 TQ v5 形(§8.1)/
  R16 去 weekday gate(§3.1)/ R17 slash defer(§5)/ R18 canonical 零寫早退(§6)/
  R19 長欄名理由記錄(§7)/ R20 on_book 掛點(§3.5、§4.1)/ R21 touch_count key 統一
  (§3.6)/ R22 Known Risks 填寫。
- v1(2026-08-04):初版。

## 1. 概觀與資料流

```
TC4 push ──> StockEngine._handle_quote(live tick 路徑)
               ├ state.ingest(tick) 為真(已排除試撮/重複)
               │    └ SignalHub.on_tick(code, tick, state)      ← 掛點 1(全部 kind)
               │         └ SignalDetector.evaluate(...)  [零 IO 狀態機]
               │              └ list[SignalEvent]
               │                   ├ engine._publish({"type":"signal",...})   → /ws/stock(同步)
               │                   └ fanout queue → worker → jsonl append + Discord(非同步)
               ├ update_book 之後:SignalHub.on_book(code, state)  ← 掛點 2(僅鎖板 kind)
               └ apply_backfill 路徑:完全不經過 SignalHub(SC-5)

Discord slash command(/watch add|remove|list)
  └ discord_bot(defer → followup)→ WatchlistService(lock)
       ├ save_watchlist(落檔)
       ├ stock.set_watchlist(訂閱池)──→ SignalHub.on_watchlist(差集:新增排基準/移除逐出)
       └ engine._publish({"type":"watchlist_changed"}) → 前端自動 refetch
(前端 PUT /api/stock/watchlist 走同一個 WatchlistService,同一把 lock)
```

原則:

- **偵測邏輯(`SignalDetector`)零 IO**,時鐘可注入 — 沿 live/ 模組慣例。
- **接線(`SignalHub`)持有所有 IO**;tick 熱路徑上只做純計算 + 入佇列,
  jsonl 與 Discord 全走 worker(R13)。
- **無 heartbeat loop** [auto-default: 理由同 v1 — 四類訊號全由新 tick / 簿更新觸發,
  免整組 stale-tick 重餵坑]。

## 2. 檔案組織

新增(後端):

| 檔案 | 職責 |
|---|---|
| `copycat/signals_config.py` | 門檻 dataclass + `configs/signals.json` 覆寫載入(strategy_config 慣例) |
| `copycat/live/signal_state.py` | `SignalDetector` 零 IO 狀態機 + `SignalEvent` dataclass |
| `copycat/server/signal_hub.py` | 接線層:基準 worker、fanout worker(jsonl/Discord)、enabled 開關持久化 |
| `copycat/server/discord_bot.py` | discord.py client、slash commands、`send_signal()` |
| `copycat/server/watchlist_service.py` | 「落檔 + set_watchlist + 廣播」複合操作 + asyncio.Lock |

修改(後端):`copycat/market.py`(公開 `tick_size_milli(price_milli) -> int`,
薄包 `_tick_milli`,R4)、`copycat/server/stock_engine.py`(兩個掛點 + attach +
rollover/watchlist 通知)、`copycat/server/app.py`(lifespan 序列 §4.5、3 條新 route、
PUT watchlist 改走 service)、`pyproject.toml`(extras `discord = ["discord.py>=2.4"]`)。

新增(前端):`signal-model.ts` / `signal-bus.ts`(§8.1 的 module-level
EventTarget,impl-review R11 補列)/ `SignalRail.tsx` / `ToastStack.tsx` /
`useSignalFeed.ts` / `useSignalAlerts.ts` / `useSignalsConfig.ts`。
修改(前端):`useStockStream.ts`、`StockPage.tsx`、`App.tsx`。

## 3. SignalDetector(`copycat/live/signal_state.py`)— SC-1/2/3/4/6

### 3.1 介面與 gate

```python
@dataclass(frozen=True)
class SignalEvent:
    kind: str            # "cdp_cross" | "surge" | "crash" | "vol_burst" | "limit_lock" | "limit_open"
    code: str
    price_milli: int
    time: str            # "HH:MM:SS" 台北(= time_key[:8];顯示用)
    time_key: str        # "HH:MM:SS.fff" 台北(R2-1;id 組成用):tick 路 = tick.time,
                         #   簿路 = now_fn() 毫秒時刻(§9 記「簿路 time 為伺服器時刻」)
    levels: tuple[str, ...]   # cdp_cross:同 tick 穿越的全部線(R7 合併);其他 kind 空 tuple
    direction: str | None     # cdp_cross:"from_below"|"from_above";limit_*:"up"|"down"
    pct: float | None    # surge/crash 實際漲跌幅;vol_burst 實際倍率
    touch_count: int     # 當日計數;合併事件取 levels[0] 的計數(§3.2)

@dataclass(frozen=True)
class TickContext:
    trade_date: str             # engine 當前交易日(R8 gate 用)
    upper_milli: int | None
    lower_milli: int | None
    ask_limit_available: bool   # asks 過濾 price>0 後非空
    bid_limit_available: bool
    bids0_is_market: bool       # bids[0] 存在且 price == 0(鎖停市價佇列簽名,R9)
    asks0_is_market: bool       # 對稱(鎖跌停用,R2-5)
    best_bid_limit_milli: int | None
    best_ask_limit_milli: int | None
    day_volume: int             # = 當筆 tick.cum_vol(R12);簿路無 tick → 0,
                                #   簿路只評估鎖板 kind,不會用到(R2-1c)

class SignalDetector:
    def __init__(self, cfg: SignalsConfig, *, now_fn=...) -> None: ...
    def set_basis(self, code: str, cdp: dict[str, int] | None) -> None: ...
    def clear_all_basis(self) -> None: ...                      # R3
    def evaluate(self, code: str, tick: StockTick, ctx: TickContext) -> list[SignalEvent]: ...
    def evaluate_book(self, code: str, ctx: TickContext) -> list[SignalEvent]: ...  # R20,僅鎖板
    def reset_day(self) -> None: ...
    def drop_code(self, code: str) -> None: ...
```

- **時間軸單一化(R11)**:窗 trim、elapsed_min、cooldown、rearm 全用 `now_fn()`
  (wall-clock 台北,恆單調);`SignalEvent.time` 用 tick 時刻,僅顯示。
- `evaluate` 四道 gate,任一不過回 `[]` **且不推進任何狀態**:
  1. wall-clock `09:00 <= t < 13:30` 台北(**無 weekday 條件**,R16 — 休市日天然無
     tick,補市日照常工作;盤後 snapshot 由本條 + gate 2 雙擋);
  2. `tick.trade_date != ctx.trade_date` → 舊日 snapshot,直接丟(R8);
  3. 首 tick(該 code 無 prev 狀態)→ 只初始化(prev/window/latch 以當下值建立)
     不評估;
  4. (試撮已被 `state.ingest` 短路,不重複判)。
- **狀態推進與事件產出分離(R2)**:過 gate 後,`_prev_price` 更新、`_window`
  append/trim、`_limit_latch` 轉移**無條件執行**(與 enabled 無關);enabled(由
  Hub 傳入 `enabled_kinds: frozenset`)只決定該 kind 是否進入「事件判定 + 產出 +
  cooldown/touch_count 寫入」。關掉爆拉不影響爆量(共用 window 照常推進);
  關閉期間鎖上→打開的 latch 轉移照常發生,重開後不會誤發。

### 3.2 CDP 穿越(SC-1)

- 基準:`set_basis` 由 Hub 餵;無基準(含 rollover 清空後未補回)→ 該 code 跳過
  CDP,其他 kind 照常。
- 判定:對五線逐一:`prev < v <= curr` → `from_below`;`prev > v >= curr` →
  `from_above`;橫盤不算。**同一 tick 穿越多線 → 合併成單一事件**(R7),
  `direction` 取整體方向(跳空只發一則)。**`levels` 固定序(R2-7,id 決定性的
  前提)**:`from_below` 依線價由低到高、`from_above` 由高到低。
- 去重三層(全毫元,R4):
  1. 方向過濾;
  2. rearm:觸發後每條穿越線進 suppressed,直到
     `abs(price_milli - v_milli) >= 5 * tick_size_milli(price_milli)` 解除;
  3. cooldown per (code, level) 600s — 合併事件對 `levels` 內每條線各寫 cooldown,
     事件成立條件 = 至少一條線不在 cooldown/suppressed 內(在冷卻中的線不列入
     `levels`)。
- **touch_count 合併語意(R2-6)**:合併事件對 `levels` 內每條線的
  `(code, kind, level)` 計數各 +1;事件的 `touch_count` 欄取 `levels[0]` 的計數
  (§3.1 / §3.6 同此措辭)。

### 3.3 爆拉 / 爆跌(SC-2)

- per-code `deque[(mono_ts, price_milli, qty)]`(mono_ts = now_fn 秒),append 後
  trim 至 300s。
- 窗內 ≥ 2 點:`pct = (curr - oldest) / oldest * 100`;`>= +2.0` → surge、
  `<= -2.0` → crash。cooldown per (code, kind) 1800s。

### 3.4 爆量(SC-3)

- gate:`elapsed_min >= 15`(now_fn 對 09:00)且 `day_volume` 可得。
- `avg_per_min = day_volume / elapsed_min`;`window_vol = Σ qty(300s 窗)`;
  `ratio = window_vol / (avg_per_min * 5)`。
- 觸發 = `ratio >= 3.0` **且** `window_vol >= min_window_lots(預設 100 張)`
  **且** `day_volume >= min_day_lots(預設 500 張)`(R10 地板,config 可調)。
  cooldown per code 1800s。`avg_per_min == 0` → 不評估。

### 3.5 鎖漲停 / 打開(SC-4)

- **鎖上(up)複合簽名(R9)**:`price == upper_milli` 且 `not ask_limit_available`
  且(`bids0_is_market` 或 `best_bid_limit_milli == upper_milli`)→ 未 latch 則發
  `limit_lock`(direction "up")並 latch。第三項排除「首攻吃光賣盤」誤判:
  首攻那一筆 ask 側同樣空,但買方市價佇列未形成、最佳限價買仍在漲停價下。
  跌停對稱(`price == lower_milli` 且 `not bid_limit_available` 且
  (`asks0_is_market` 或 `best_ask_limit_milli == lower_milli`))。
  **與 `relabel_locked_side` 的關係(R2-9)**:同一制度恆等式,但**判準因資料形
  不同而相反** — 該函式面對歷史單檔 row(鎖停時 bid/ask 皆歸 None,判
  「兩側皆不可得」);REALTIME 有五檔,真鎖停時 bid 側**必然可得**(市價佇列 0
  或漲停價限價),故本簽名用「可得且為市價/漲停價」。**不可**抄它的 `is None`
  條件或直接呼叫它(在 REALTIME 路徑恆假 → 鎖板訊號整條靜默不發)。
- **打開**兩條路(R20):
  (a) 成交路:latched 且 `price < upper_milli` → 發 `limit_open` 解 latch;
  (b) 簿路:`evaluate_book`(掛點 2)— latched 且 ask 側限價檔重新出現
  (`ask_limit_available` 轉真)→ 同樣發 `limit_open` 解 latch(尾盤解鎖無成交
  也抓得到)。兩路共用 latch,先到先發。簿路事件無成交:`price_milli` 用漲停價、
  `time_key` 用 `now_fn()` 毫秒時刻(R2-1b)。
- 再鎖回可重發。cooldown **per (code, kind, direction) 分桶**(lock 自己 600s、
  open 自己 600s)[amendment 2026-08-04 T2 落地釐清:原「lock 與 open 共用」會吃掉
  鎖上後 600s 內的真打開 — 與 SC-4 字面衝突且打開正是高價值訊號;分桶後 flapping
  上界 = 每 600s 一對 lock/open,可接受]。
- `upper_milli is None` → 跳過。`evaluate_book` 只跑鎖板 kind,gate 1(時窗)
  適用;日別防護不在 detector — 由掛點位置保證(§4.1:換日 pending 期間
  engine 不呼叫 on_book,R2-2)。

### 3.6 內部狀態總表

| 狀態 | key | 推進時機 | reset_day |
|---|---|---|---|
| `_prev_price` | code | 無條件(過 gate 後) | 清 |
| `_window` | code → deque | 無條件 | 清 |
| `_suppressed` | (code, level) | 事件產出時寫入;無條件檢查解除 | 清 |
| `_cooldown` | (code, kind, level 或 direction 或 "") → mono | 事件產出時 | 清 |
| `_touch_count` | (code, kind, level)(R21 統一) | 事件產出時 | 清 |
| `_limit_latch` | (code, direction) → bool | 無條件 | 清 |
| `_basis` | code → dict 或 None | set_basis / clear_all_basis(R3) | **清(→ None)** |

## 4. SignalHub(`copycat/server/signal_hub.py`)— SC-5/7/12

### 4.1 介面與掛點

```python
class SignalHub:
    def __init__(self, cfg, *, publish, daily_bars, notify_fallback, data_dir, now_fn=...) -> None: ...
    async def start(self) -> None      # 基準 worker + fanout worker
    async def close(self) -> None      # 停 worker、flush 佇列(盡力)
    def on_tick(self, code, tick, state: StockDayState) -> None
    def on_book(self, code, state: StockDayState) -> None       # R20
    def on_rollover_pending(self, new_date: str) -> None  # stage1(R2-4):以 new_date 預抓暫存 basis
    def on_rollover(self) -> None      # stage2:**先 detector.reset_day 再 swap 暫存 basis**
                                       #   (順序不可反 — reset_day 清 _basis,反序會把剛換上的
                                       #   當日基準洗掉,T2 落地釐清);swap 回 False(無暫存)
                                       #   → fallback 清空 + 排隊重抓(R3)
    def on_watchlist(self, codes: list[str]) -> None
    def request_basis(self, codes: list[str]) -> None
    def enabled(self) -> dict[str, bool]
    async def set_enabled(self, flags: dict[str, bool]) -> None
    def attach_discord(self, sender) -> None
```

- **membership gate(R5)**:hub 自維護 `_watch: set[str]`(由 `on_watchlist` 全量
  替換,初始由 §4.5 boot 序列餵)。`on_tick` / `on_book` 開頭
  `if code not in self._watch: return` — 主圖臨時看的非自選股不評估、不發任何訊號。
- `on_tick` 全包 try/except log(丟棄該 tick 評估,不汙染主路徑);組 `TickContext`
  (trade_date 取 engine 當前值,由 attach 時傳入 getter 或 on_tick 參數帶入)。
- StockEngine 增 `attach_signal_hub(hub)`;`_handle_quote` ingest 為真分支呼叫
  `on_tick`;**`on_book` 呼叫點在 `_handle_quote` 尾端(rollover 快路徑與 stage2
  之後,與 book 廣播同位置),且引擎處於換日 pending 狀態(stage1 已觸發、stage2
  未完成)時跳過**(R2-2 — 否則跨日後第一則簿更新會拿今日簿對照昨日 latch 誤發
  `limit_open`)。hub None 則全跳過。
  **apply_backfill 路徑零接觸**(SC-5 結構保證 + 測試鎖死)。
- `set_watchlist` 尾端呼叫 `hub.on_watchlist(codes)`(新增→排基準、移除→
  `detector.drop_code`);rollover stage1(`_checkpoint_loop` 偵測換日,離開盤近
  一小時)呼叫 `hub.on_rollover_pending(new_date)`、stage2(首筆新日 tick)呼叫
  `hub.on_rollover()`(R2-4 — 基準預抓在盤前完成,stage2 只 swap,**開盤第一筆
  起 CDP 即用當日正確基準**,不再有「開盤數十秒 CDP 停用」窗;週六補市日 stage1
  可能未跑 → fallback 清空重抓,該日開盤初段 CDP 停用為已知限制,入 Known Risks)。

### 4.2 CDP 基準 worker

- `asyncio.Queue` + 單工 worker,job = `(code, basis_date, staged: bool)`:逐 code
  `await daily_bars(code, n=5)` → 最後一根已完成 bar(date < basis_date)→
  `compute_cdp` → `set_basis`(staged 時寫暫存區,stage2 swap 才生效,R2-4)。
- **每檔之間 `await asyncio.sleep(0.2)`**(Known Risk 3 緩解:與 `_backfill_worker`
  / route 層共用同一條 TC4 stock session,30 檔連發要讓位主圖回補;盤前預抓時段
  無主圖競爭,間隔無感)。
- 失敗:log + `set_basis(code, None)`,不自動重試 [auto-default 同 v1]。
- 觸發點:boot 序列(§4.5)、`on_rollover_pending`(盤前預抓)、`on_rollover`
  fallback(stage1 未跑時清空重抓)、`on_watchlist` 新增 code。

### 4.3 Fanout(R1/R13)

1. **WS 同步先送**:`publish({"type":"signal", ...})`(既有 per-client 有界 queue)。
2. **jsonl 與 Discord 拆兩條佇列/worker** [amendment 2026-08-04 review CC-5:原單一
   佇列讓慢 Discord 擋住 jsonl 真相源]:jsonl 佇列 maxsize 1000(滿丟最舊+計數;
   worker 只 `asyncio.to_thread` append `data/signals/YYYYMMDD.jsonl`,失敗 log 不
   raise 且 worker 不死)/ Discord 佇列 maxsize 100(丟最舊 + 30/min 節流;bot
   sender 可用先 bot,失敗或未 attach → `asyncio.to_thread(notify_fallback)`;兩層
   都敗只 log)。`close()` 停收件 → jsonl 佇列 drain 到空(零漏)→ Discord 放棄。
3. **訊號 id 決定性鍵(R1)**:
   `id = f"{trade_date}-{code}-{kind}-{'+'.join(levels) or direction or '-'}-{time_key}"`
   (`time_key` 見 §3.1,毫秒級;levels 固定序見 §3.2)。跨重啟不碰撞
   (不依賴 process 記憶),同一事件天然同 id。
4. **全域節流只作用 Discord(R7 + R2-8)**:hub 級每分鐘 Discord 發送上限
   (預設 30,config 可調),超出者不入 Discord 佇列 + 計數 log;
   **WS 與 jsonl 不節流**(成本極低且是歷史真相源)— 據此 detector 的
   cooldown/touch_count 無需回滾,前端「reconnect refetch today」自癒語意完整,
   被節流的只有外部通知一路。

文案(bot / webhook 同一段):
`🔔 突破 CDP AH(壓力・第2次)｜台積電 2330｜123.45｜09:31:02`;多線合併列
`AH+NH`。kind 中文:突破/跌破 CDP、爆拉/爆跌(附 %)、爆量(附倍率)、
鎖漲停/漲停打開(跌停對稱)。`cdp` 線顯示「中軸」。

### 4.4 enabled 開關(SC-12)

- 四鍵 `{"cdp_cross","surge_crash","vol_burst","limit_lock"}`;載入
  `data/signals_enabled.json`(缺檔全開;atomic write)。
- 生效語意(R2):停用 kind **不產生事件、不發送、不寫 cooldown/touch_count**;
  狀態推進不受影響(§3.1)。SC-12 驗收措辭同步 amendment。

### 4.5 Lifespan 序列(R6)

`app.py` lifespan 在既有 stock `_boot` 之後,**整段套既有 `_boot` 隔離慣例**
(R2-3 — 任一步拋例外只讓訊號功能停用,不波及其他引擎;discord.py 登入失敗 /
load_watchlist 壞檔都被 `_boot` 的 except 接住):

```
stock = _boot("stock", ...)                       # 既有
signals = await _boot("signals", "訊號引擎",
    make=_make_signals,      # stock None → 回 None;否則建 SignalHub(不做 IO)
    start=_start_signals,    # hub.start() → stock.attach_signal_hub(hub)
                             # → hub.on_watchlist(load_watchlist(wl_path)["codes"])
                             # → bot = await create_bot(service, hub)(token 未設 → None)
                             # → bot 非 None 時 hub.attach_discord(bot.send_signal)
    close=...)               # bot.close() → hub.close()
service = WatchlistService(wl_path, stock)  if stock else None   # 純物件,不會拋
app.state.signal_hub / watchlist_service / discord_bot 掛載;任一 None →
  3 條新 route 回 503 NOT_READY、/watch 指令回「服務未就緒」、PUT watchlist
  維持既有 _stock() 閘行為。
```

關機(finally 最前,先於既有 corr→…→stock 反序):
`bot.close()` → `hub.close()`(fanout worker 停止後才輪到 `stock.close()`,
不對已收攤 engine publish)。

## 5. Discord bot(`copycat/server/discord_bot.py`)— SC-8

- extras `[discord]`;import 失敗或 `DISCORD_BOT_TOKEN` 未設 → `create_bot` 回
  None,server 照常。env 讀取:`name in os.environ` 即用 → repo root .env
  (utf-8-sig)。
- `on_ready`:fetch `SIGNALS_DISCORD_CHANNEL_ID` → 取 guild → 對該 guild sync
  slash commands(即時生效)[auto-default 同 v1;覆蓋 treading-king 舊指令風險
  已記 Known Risks]。指令僅接受該 guild。
- **每個 handler 一進來先 `await interaction.response.defer(thinking=True)`,
  結果用 `followup.send`(R17;`/watch add` 的路徑含 ZMQ 往返可能 > 3s)**。
  fake interaction 測試斷言 defer 被呼叫。
- 指令(回覆繁中):`/watch add code [group]`、`/watch remove code`、`/watch list`
  (依群組列出,未分組殿後)。`WatchlistError` → 對應文案不落檔;
  service 不可用(stock None)→「服務未就緒」。
- `send_signal(text) -> bool`:channel send;未 ready / 無頻道 → False。

## 6. WatchlistService(`copycat/server/watchlist_service.py`)— SC-8/11

- 介面同 v1(`apply` / `add` / `remove`),單一 `asyncio.Lock`。
- **零寫早退比較基準(R18)**:比較「請求經 `save_watchlist` 同款正規化後的
  canonical 形」vs「`load_watchlist` 現況 canonical 形」;相同 → 不落檔、不
  `set_watchlist`、不廣播。**此為既有 PUT 行為改動(🔴)**:同內容 PUT 從
  「全量 UNSUB/SUB」變 no-op — 補測試「同內容 PUT 兩次,第二次不觸發
  set_watchlist 不廣播」。正規化抽 `stock_watchlist.normalize(wl)` 純函數
  (save_watchlist 內部改用它,單一定義)。**早退分支的回傳 = 現況 canonical 形**
  (比較時算出的那份),與落檔路徑回傳同形(R2-10);測試斷言同內容 PUT 兩次
  response body 完全相同。
- 變更成功 → `engine.set_watchlist` → `engine._publish({"type":"watchlist_changed"})`。

## 7. API / WS 契約

- WS `/ws/stock` 新增兩型(既有 client 忽略未知 type):
  - `{"type":"signal","id","kind","code","name","price","time","levels":[...],
     "direction","pct","touch_count"}`(price 毫元 int;name 由 hub 從 state.meta
     取,缺 "")。**刻意用長欄名**(R19):訊號訊息同時是 jsonl row 與歷史 API
    形狀,事件型資料偏可讀性;與 tick/quote 短欄名分屬不同語族,消費端不共用
    解析器。
  - `{"type":"watchlist_changed"}`
- `GET /api/stock/signals/today` → `{"signals":[...]}`(讀當日 jsonl,壞行跳過)。
- `GET /api/stock/signals/enabled` → `{"enabled":{...4 鍵}}`;`PUT` 同形;非法鍵/值
  400 `INVALID_SIGNALS_ENABLED`(R14 改名,名實相符;門檻仍在 configs/ 不經 API)。
- 三條 route 一律先過 `_stock(request)` 閘(hub 掛在 app.state,stock None 或 hub
  None → 503 `{"detail":{"error":"NOT_READY"}}`),沿既有優先序(R14)。

## 8. 前端 — SC-9/10/11

### 8.1 資料流

- `useStockStream` 新增分發:`signal` → 訊號 bus(module-level EventTarget);
  `watchlist_changed` → `queryClient.invalidateQueries({ queryKey: ["stock-watchlist"] })`
  (TQ v5 物件形,R15;key 與 useStockWatchlist 一致)。
- `useSignalFeed`:baseline `GET signals/today` + bus 事件 prepend,id 去重,上限
  200;**WS reconnect 時 refetch today**(Known Risk 2 自癒:斷線期間 WS 丟的訊號
  由 jsonl 補回)。
- `useSignalsConfig`:TQ query + mutation(PUT enabled)。

### 8.2 SignalRail(SC-9)

同 v1(w-52 左欄、上半訊號流點擊切主圖、下半四 toggle + 通知權限按鈕)。
被停用類型即時訊號不入列(feed 端過濾)。localStorage 一律 `copycat-` 前綴。

### 8.3 通知(SC-10)

- `ToastStack`:同時顯示上限 4 則,溢出以「+N」計數列呈現(R7);每筆 5s 自動
  消失,點擊即關。
- `useSignalAlerts`:bus 訂閱 → toast;`document.hidden` 且權限 granted →
  Notification;提示音 Web Audio 短嗶;靜音 toggle localStorage
  `copycat-signal-sound`(預設開)。

## 9. 邊界與失效樣態

- 回補重放:掛點結構隔離 + SC-5 測試。
- 盤後 / 舊日 snapshot:gate 1(時窗)+ gate 2(trade_date)雙擋;盤中新增自選的
  fresh subscribe 舊日 snapshot 由 gate 2 擋(R8)。
- 鎖停市價 0 檔位:TickContext 由 `_best_limit_price` 同款過濾組出;複合簽名見
  §3.5。
- 重啟:cooldown/latch 不持久;首 tick gate 防誤發;id 決定性鍵保證 feed 合併不
  碰撞(R1)。最壞 = 重啟後同訊號多發一次(Discord/toast),feed 端同 id 去重。
- Discord 全掛:WS + jsonl 不受影響;佇列滿丟最舊有計數。
- 補市日:無 weekday gate,照常工作(R16);但 stage1 可能未跑 → 開盤初段 CDP
  停用(Known Risk 5)。
- 鎖板打開以「成交 < 漲停」或「ask 限價檔重現」兩路觸發;簿路訊號無成交價,
  price 欄用漲停價、time 為**伺服器時刻**非成交時刻(R20、R2-1)。

## Known Risks

1. **slash command sync 覆蓋同 application 舊指令**(treading-king bot 已退役,
   接受;收尾回報提醒 user)。
2. **/ws/stock 有界 queue 滿丟訊號**:前端靠「reconnect 時 refetch today」自癒;
   同連線內被丟(慢消費)的訊號要等下次 reconnect 或重整才補回。
3. **基準 worker 與主圖回補 / K 線 route 共用 TC4 session**:啟動時 30 檔以
   0.2s 間隔錯開;若實測仍搶,調大間隔(config)。
4. **爆量門檻(ratio 3.0 / 地板 100+500 張)未經回測**,treading-king 只有 schema
   沒有 production 參數;上線後依實際噪音調 config。
5. **週六補市日 / server 開盤後才啟動時,CDP 基準抓齊前該窗停用**(stage1 預抓
   只覆蓋常規換日;fallback 路徑 30 檔 × (RTT + 0.2s) 約十數秒)。
6. **Discord 節流(30/min)只丟外部通知**,WS/jsonl 完整;被丟筆數有計數 log。
7. **PUT watchlist 的自我廣播回彈**(review MFS-7,documented 不修):發起端也會收到
   `watchlist_changed` → 多一趟 GET;連續兩次快速編輯時 GET1 晚到可能把 cache 短暫
   回捲(下一次廣播自癒)。單人本機用量可接受;若可見抖動再做發起端 gate。
8. **快路徑換日(補市日)staged 預抓派不上用場**(MFS-2 fix 後的殘餘代價):stage1/
   stage2 同步連發時 staged 必空 → 走 fallback 重抓,該日開盤初段 CDP 停用且
   daily_bars 多抓一輪;日別標記保證不會錯用舊基準(正確性已鎖),成本面接受。

## 10. SC 對應表

| SC | 設計節 |
|---|---|
| SC-1 CDP 穿越 | §3.2, §4.3 |
| SC-2 爆拉/爆跌 | §3.3 |
| SC-3 爆量 | §3.4 |
| SC-4 鎖板/打開 | §3.5 |
| SC-5 回補不誤發 | §4.1 |
| SC-6 盤別 gate | §3.1 |
| SC-7 訊號歷史 | §4.3, §7 |
| SC-8 Discord bot | §5, §6 |
| SC-9 左側訊號欄 | §8.2 |
| SC-10 即時通知 | §8.3 |
| SC-11 自選同步 | §6, §8.1 |
| SC-12 開關持久化 | §4.4, §7, §8.2 |
