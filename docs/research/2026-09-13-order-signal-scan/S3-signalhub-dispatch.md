# S3-signalhub-dispatch —— 訊號:SignalHub 分派、slot 模型與 fanout

掃描日期:2026-09-13 · 主檔 `copycat/server/signal_hub.py`(1697 行,整檔讀完)
週邊:`copycat/live/signal_state.py`、`copycat/signal_rules.py`、`copycat/server/signal_policy.py`、
`copycat/server/ws.py`、`copycat/server/stock_engine.py::_handle_quote`、`copycat/server/app.py` lifespan、
`copycat/server/shutdown_budget.py`

量測腳本留在本目錄:`bench_hub.py` / `bench_hub2.py` / `bench_hub3.py` / `bench_cdp.py` /
`bench_pol.py` / `bench_lat.py`;資料回推腳本 `an1.py`–`an4.py`。
**未改動 repo 任何檔案、未啟動 server、未下任何單。**
執行環境 = repo 內 `.venv`(CPython 3.13.13 / Windows 11 / ProactorEventLoop)。

---

## 0. 一句話結論

**分派層(slot 迴圈 + 雙佇列 fanout)在現況量級下不是延遲問題** —— 實測全日訊號層
佔用 event loop **0.19%**(30.9 s CPU / 16,200 s 連續盤,由真實 tick 數回推)。
但這一段有三件事會在「要下實單 / 量化放大」時咬人,而且**全部零錯誤訊號**:

1. **`rule_id` 每次重啟換一次**(遷移種子卡走 `int(time.time())`),決定性訊號 id 契約
   對 `surge_pullback` ×2 / `sweep_cluster` / **全部政策列** 已經破了 —— prod jsonl 實證
   同一天出現兩組 rule_id(09-08 / 09-10 / 09-11)。影子期對帳直接受影響。
2. **Discord 節流是一條沒有計數器的丟棄通道**:`dropped_discord` 恆 0,而 09-03 / 09-09
   開盤實際各有 15 / 8 則被 `_allow_discord` 擋掉且**永不補送**;八則裡只有一則 log 帶得出 id。
   盤後判準 `grep 佇列滿 = 0` 讀起來像「全數送達」,實際不是。
3. **`_flush_pending` 無逾時且走共用 20-worker executor**,是關機路徑上唯一沒被
   `shutdown_budget` 記帳的一段;而 `_CLOSE_FLUSH_TIMEOUT`(5.0 s)恰等於
   `LIFESPAN_SLACK_SECS`(5.0 s)這個要涵蓋**整個 signals + screen + breadth + crosscheck**
   的裕度 —— 帳面上已經超支。

反過來:**雙佇列 + `_put_drop_oldest` 背壓、`_discord_worker` 單槽合批、`_RuleSlot` frozen
原子替換、`_emit` 的欄位組裝、政策層純函式 —— 全部寫得對,不要動**(§7)。

---

## 1. 現況地圖:slot 模型與分派

### 1.1 資料結構

```
SignalHub
├ _slots: dict[rule_id, _RuleSlot]         # 熱路徑唯一讀取點,整顆 dict 原子替換
│   └ _RuleSlot(frozen)                     signal_hub.py:340-350
│       ├ rule: Rule                        # TypedDict:id/name/kind/enabled/notify_discord/
│       │                                   #            cooldown_secs/params/cdp_levels
│       ├ detector: SignalDetector          # ← 每條規則一顆**完整**狀態機
│       └ enabled: frozenset[str]           # rule.enabled ? {rule.kind} : frozenset()
├ _watch: set[str]                          # membership gate(on_watchlist 全量替換)
├ _basis_cache / _staged_cache              # CDP 基準唯一快照(帶基準日)
├ _basis_jobs: asyncio.Queue                # **無界**
├ _jsonl_queue: asyncio.Queue(maxsize=1000) # 真相源
├ _discord_queue: asyncio.Queue(maxsize=100)# 可丟的通知路
├ _discord_pending: dict | None             # 合批單槽
├ _discord_sent: deque[datetime]            # 60 s 滾動節流窗
└ _policy_touch / _multi_group_warned / _peers_fn_failures / _exclude_missing
```

### 1.2 `_make_slot` 逐行:一顆 detector 持有什麼

`signal_hub.py:455-463`

```python
def _make_slot(self, rule: Rule) -> _RuleSlot:
    return _RuleSlot(
        rule=rule,
        detector=SignalDetector(rule_config(rule, self._cfg), now_fn=self._now_fn),
        enabled=frozenset({rule["kind"]}) if rule["enabled"] else frozenset(),
    )
```

`SignalDetector.__init__`(`signal_state.py:193-218`)每顆各持 **14 份 per-code 表**:

| 欄位 | 內容 | 被哪個 kind 讀 | 一條規則實際用得到? |
|---|---|---|---|
| `_basis` | code → CDP 五線 | cdp_cross | 只有 cdp_cross 規則 |
| `_staged` / `_staged_date` | 暫存基準 | **零呼叫端**(hub 接手後死碼,模組 docstring 自承) | 沒有 |
| `_prev` | code → 前一筆價 | cdp_cross(穿越推定) | 全 kind 都寫 |
| `_window` | code → deque[(mono, price, qty)] 300 s | surge / pullback / vol_burst | 全 kind 都**寫**(`evaluate` 無條件 append + 剪裁) |
| `_suppressed` / `_side` | (code, level) → 駐留 / 側別 | cdp_cross | 只有 cdp_cross |
| `_cooldown` / `_touch` | (code, kind, tag) → 冷卻 / 計數 | 全 kind | 只有自己那個 kind 寫得到 |
| `_latch` | (code, dir) → 鎖停 latch | limit_lock / limit_open | 只有 limit_lock |
| `_pullback` | code → (armed, peak, fired_at, rearm_base) | surge_pullback | 只有 surge_pullback,但**無條件推進** |
| `_sweep_group` / `_sweeps` / `_lookback` | 掃單簇三份 | sweep_cluster | 只有 sweep_cluster,但**無條件推進** |

**重複度(實測)**:prod 7 條規則 = 7 顆 detector。
`bench_hub.py` 灌單檔 1501 筆 tick 到穩態:

```
窗長(每顆 detector)      = [1501, 1501, 1501, 1501, 1501, 1501, 1501]
一檔 7 顆 detector 窗總筆數 = 10,507      （必要值 1,501 → 7.0×）
7 份 _window pickle 近似大小 = 185.1 KB / 檔
lookback 總筆數            = 2,107        （必要值 301 → 7.0×）
```

→ 80 檔自選、窗長 1501 的最壞:7 × 80 × 1501 ≈ 84 萬筆 tuple。
實務上大多數檔窗長很短(09-09 全日 tick 中位數 **132 筆/檔**,窗長 ≈ 2),
所以記憶體實際壓力遠低於這個上界 —— 這一點與 B06 的「最壞 120 MB」是同一件事,
但要誠實標明那是**最壞**、不是常態。

**重複度的 CPU 面(實測,窗長 1501 / 檔,`bench_hub3.py`)**:

```
prod 7 條(全啟用)                           73.43 us/tick
7 條全部 enabled=false(純死工)              24.84 us/tick
7 條(只停 vol_burst)                        25.30 us/tick
1 條 cdp_cross                                6.88 us/tick
1 條 vol_burst                               55.77 us/tick
1 條 sweep_cluster                            7.00 us/tick
1 條 limit_lock                               6.84 us/tick
單顆 detector / 六 kind 全開(去重後理論值)   55.46 us/tick
```

拆解:**成本 ≈ 固定 3.5 µs × 規則數 + 0.0326 µs × 窗長**(vol_burst 的 `sum()`,只有一條規則付)。
7 條的固定成本 24.84 µs 中,約 **21 µs 是重複的市場狀態維護**(窗 append/剪裁、
`_eval_sweep` 的 lookback 與同毫秒群、`_eval_pullback` 的波狀態、`_eval_limit_tick` 的 latch)。

### 1.3 去重方案:怎麼切、動到哪些介面、風險

**切法(兩層)**:

```
新增 per-code 市場狀態(每 tick 每檔算一次)        新增 per-rule 判定(只做比較)
┌─────────────────────────────────────┐            ┌──────────────────────────┐
│ MarketState(code)                    │            │ RuleEvaluator(rule)      │
│  prev, side[], suppressed[]          │  ────────► │  cooldown[], touch[],    │
│  windows: dict[window_secs, Window]  │            │  latch[], pullback[]     │
│    Window = deque + running_sum      │            │  只讀 MarketState 的     │
│  sweep_group, sweeps, lookback       │            │  衍生量,不再自己維護窗  │
│  latch_up / latch_down(唯一一份)    │            └──────────────────────────┘
└─────────────────────────────────────┘
```

去重率 = 規則數 → **不同窗長的種類數**。prod 7 條規則只有 **2 種窗長**
(surge/pullback/vol_burst 共用的 300 s、sweep lookback 的 60 s)→ 7 → 2。

**動到的介面**:
- `SignalDetector.evaluate(code, tick, ctx, enabled)` 的簽名要多吃一個已算好的
  `MarketState`(或整個拆成兩個類)。`now_fn` 注入契約(`signal_hub.py:455-458` 明文
  「漏帶 `now_fn` 的那一顆會偷用真實時鐘」)要移到 `MarketState`。
- `_make_slot` / `_seed_slot` / `_drop_code` / `on_rollover` 四處逐 slot 迴圈都要改成
  「一次動市場狀態 + 逐 rule 動判定表」。
- `signal_rules.py` 模組 docstring 明寫的設計決定「一條規則 = 一顆**未改動**的 detector,
  調參數永遠只是換一份 config」**就是被改掉的那一條** —— 要 user 拍板。

**風險**:
1. `tests/fixtures/sweep_cluster_golden.json`(CLAUDE.md §4)釘住 `_eval_sweep` 必須與
   `expected_prefix` 集合相等 —— 重構後這支必須仍綠,是第一道門。
2. 兩條**同 kind 但窗長不同**的規則(例:一條 vol_burst 60 s、一條 300 s)必須各有窗。
   共享鍵必須是 `(code, window_secs)`,不是 `code`。寫成 per-code 一份窗會**靜默**把
   兩條規則的門檻對到同一個母體上,而畫面完全正常。
3. `_eval_cdp` 的 `_side` / `_suppressed` 是 per (code, level),但**線價來自 per-rule
   的 `cdp_levels` 過濾後基準** —— 兩條 cdp_cross 規則訂閱不同線時,側別表可以共享
   (鍵含 level),但 `_suppressed` 的 rearm 駐留是**規則參數**(`rearm_ticks` /
   `rearm_dwell_secs`)的函數,**不可共享**。這是最容易寫錯的一格。

**收益(實測上界)**:73.43 → 55.46 µs/tick(25%);**再配合 running-sum 修掉 vol_burst 的
`sum()` 才是主菜**(55.46 → ~7 µs)。單做去重不做 running-sum,收益不到三成。

> **建議順序:先做 §8 的 S1/S2/S3(零風險、有量測判準),去重排在最後**,
> 因為以現況量級(0.19% loop)它解的是**餘裕**不是**現有延遲**。

---

## 2. `on_tick` / `on_book` 的呼叫鏈與頻率

### 2.1 呼叫鏈

```
TC4 ZMQ listener thread
 └ stock_source 解析 → loop.call_soon_threadsafe(_handle_quote)   stock_engine.py:1150
    └ _handle_quote(quote)                                        （event loop 單執行緒）
       ├ …漲跌停值變 / rollover stage1 / stage2 / 首筆入列回補…
       ├ if tick is not None and state.ingest(tick):              stock_engine.py:1316
       │    ├ (打包 ticks / dirty watchlist)
       │    └ hub.on_tick(code, tick, state)                      stock_engine.py:1352
       │         ├ if code not in self._watch: return             signal_hub.py:599   ← 閘 1
       │         ├ ctx = self._context(state, tick.cum_vol)       signal_hub.py:603
       │         └ for slot in self._slots.values():              signal_hub.py:607   ← N = 7
       │              ├ slot.detector.evaluate(code, tick, ctx, slot.enabled)
       │              │    ├ if not _in_session(now): return []   signal_state.py:295 ← 閘 2
       │              │    └ if tick.trade_date != ctx.trade_date: return []  :297  ← 閘 3
       │              └ self._fanout(code, slot, events, state)   signal_hub.py:614
       ├ (轉態補推 / book publish)
       └ if hub is not None and self._pending_date is None:       stock_engine.py:1365 ← 閘 A
            hub.on_book(code, state)                              stock_engine.py:1366
              ├ if code not in self._watch: return                signal_hub.py:617   ← 閘 1
              ├ ctx = self._context(state, 0)                     signal_hub.py:620   ← **第二次建構**
              └ for slot in self._slots.values():                 signal_hub.py:625   ← N = 7
                   slot.detector.evaluate_book(code, ctx, slot.enabled)
```

### 2.2 每則推播跑幾次(這是本節的正解)

| | on_tick | on_book |
|---|---|---|
| 觸發條件 | `tick is not None` **且** `state.ingest(tick)` 為真(試撮 / 重複 cum_vol 已短路) | **每一則走到 `_handle_quote` 尾端的 quote**,無條件 —— **不判簿有沒有變、不判有沒有成交** |
| engine 側閘 | 無(靠 detector 內的日別閘) | `_pending_date is None` |
| hub 側閘 | `code not in _watch`(0.06 µs) | 同 |
| 每則跑幾次 evaluate | **7**(= `len(_slots)`) | **7** |
| `_context` 建構 | 1 次 | 1 次(**同一則帶成交的 quote 共建 2 次,只差 `day_volume`**) |

> **帶成交的 quote → `_context` 建 2 次 + 14 次 detector 呼叫**。
> `on_book` 的 docstring(`signal_state.py:334`)自承「只評估鎖停打開」,而 `limit_open`
> 一天全自選只有個位數則(09-11 實測 **5 則**、09-09 **6 則**)。

### 2.3 頻率(由真實 log 回推,`an3.py`)

回補行 `stock backfill <code>: <n> ticks` 記了每檔當日 tick 數,滿日重啟的 log 可直接加總:

| log | 檔數 | 總 tick | 均 tick/s(09:00–13:30) | 最大單檔 | 中位數 |
|---|---|---|---|---|---|
| `server-20260909-2248.log` | 181 | 518,114 | **32.0/s** | 58,938 | 132 |
| `server-20260911-0036.log` | 167 | 382,747 | 23.6/s | — | — |
| `server-20260908-1911.log` | 95 | 490,322 | 30.3/s | — | — |

`on_book` 的母體(REALTIME quote 數)**現況量不到**(零儀器)。下界 = tick 數;上界 =
tick 數 + 純簿更新數。下面的預算以「= tick 數」估,實際只會更高 —— **這是要加探針的第一件事**。

### 2.4 loop 佔用(實測 × 實測,`an3.py`,以 09-09 的 518,114 tick 為母體)

```
7 顆 detector 固定成本        = 13.0 s CPU / 全日   (0.080% loop)
vol_burst sum() 全部合計       =  7.2 s CPU / 全日   (0.044% loop)   ← Σ(WIN/SESSION)·T_i² 精算
on_book(假設母體 = tick 數)   = 10.7 s CPU / 全日   (0.066% loop)
───────────────────────────────────────────────────────────────
訊號分派層合計                ≈ 30.9 s / 16,200 s  = 0.19% loop
```

**開盤尖峰**(推估):首 15 分鐘約佔全日 tick 的 25% → 144 tick/s ×(25 µs + 20.6 µs)
≈ **6.6 ms/s = 0.66% loop**。窗長在 09:05 前最長只有「開盤以來的筆數」,所以 vol_burst
的 `sum()` 在開盤反而**還沒**長到最貴。

→ **結論:現況量級下分派層不是瓶頸,任何「換掉 slot 模型能救延遲」的說法都不成立。**
真正的風險在 §5 的 REST 可寫放大軸。

---

## 3. `_distribute` / `_seed_slot` 的過濾條件與 `enabled` 漏檢

### 3.1 漏檢在哪

`signal_hub.py:972-990`(`_distribute`)與 `517-529`(`_seed_slot`)**都只看 `kind`,不看 `enabled`**:

```python
# _distribute(986-990)
for slot in self._slots.values():
    if slot.rule["kind"] != "cdp_cross":
        continue
    slot.detector.set_basis(code, _filter_levels(cdp, slot.rule["cdp_levels"]))

# _seed_slot(524-529)
if slot.rule["kind"] != "cdp_cross":
    return
...
slot.detector.set_basis(code, _filter_levels(cdp, slot.rule["cdp_levels"]))
```

被餵了基準之後,`_eval_cdp`(`signal_state.py:383-386`)的第一道早退 `if not basis: return []`
**不成立** → 每 tick 照跑 `_advance_rearm`(5 線迴圈)+ `_advance_sides`(5 線迴圈 + dict 讀寫),
一路跑到 `signal_state.py:392` 的 `if "cdp_cross" not in enabled` 才回頭。

**實測代價(`bench_cdp.py`,單條規則、有五線基準、窗長 400)**:

```
1 條 cdp_cross:enabled=True,有 basis                     8.95 us/tick
1 條 cdp_cross:enabled=False,_distribute 仍餵 basis       9.30 us/tick   ← 比啟用的還貴
1 條 cdp_cross:enabled=False,無 basis(理想)             7.30 us/tick
```

停用的規則**比啟用的還貴 0.35 µs**(啟用那條會在 cooldown / suppressed 分支提早 return)。
`enabled` 漏檢的淨代價 = **2.0 µs/tick/規則**。

**誠實標註**:prod 目前的 CDP 規則是 `enabled=True`(只有 `notify_discord=false`,
09-11 jsonl 實證 295 列 cdp_cross)。**這條現在是潛在成本,只有 user 在規則視窗按下
「停用」才真的發生。**

### 3.2 更重要的:`on_tick` / `on_book` 的 slot 迴圈**完全不看 `enabled`**

`signal_hub.py:607` 與 `625` 都是 `for slot in self._slots.values():` 無過濾。
停用的規則付**全額**狀態推進 —— 實測 `7 條全部 enabled=false = 24.84 µs/tick`。

設計文件的辯護(`signal_state.py:19-23`)是:「狀態推進與事件產出分離…關掉爆拉不影響
共用同一個窗的爆量;停用期間鎖上→打開的 latch 照常轉移,重開後不會補發一則過期的打開」。

**這個理由在 per-rule detector 架構下已經不成立**,而且是可證明的:

- `_RuleSlot` 的唯一建構點是 `_make_slot`(`signal_hub.py:455`)。
- `_make_slot` 的唯一兩個呼叫端是 `_load_or_migrate_rules`(:452)與 `upsert_rule`(:493)。
- 改 `enabled` 的**唯一**路徑是 `PUT /api/stock/signals/rules/{id}` → `_save_rule`
  (`app.py:1593`)→ `upsert_rule` → `_make_slot` → **一顆全新的、狀態全空的 detector**。

→ 停用期間辛苦推進的那份狀態,**在重新啟用的那一刻就被整顆丟掉**。
它不可能被任何人讀到(該 slot 的 `enabled` 空,而別的 slot 讀不到它的表)。

> **因此 `if not slot.enabled: continue` 是「逐字行為等價」的改動,不是取捨。**
> 這是本輪最便宜、最安全的一條:三行、零契約、零行為差。

---

## 4. 雙佇列 fanout + `_put_drop_oldest` 背壓 —— 確認並量化

### 4.1 設計(確認寫得對)

`signal_hub.py:405-408`(建構)/ `1167-1184`(`_enqueue`)/ `1673-1688`(`_put_drop_oldest`):

- 兩條**獨立**有界佇列:jsonl 1000(真相源)、Discord 100(可丟)。
  不可合併的理由(模組 docstring CC-5)成立:Discord 一卡住,共用佇列會讓 jsonl 缺角,
  而缺角靜默且不可回復。
- `_put_drop_oldest` 不 `await put` → **熱路徑零反壓**。滿了 `get_nowait()` 丟最舊
  (+ `task_done()` 記帳,少記一格 `join()` 會永遠不返回)、再 `put_nowait`。
- 丟棄有計數 + 每 20 筆一則 WARNING 節流。

**實測成本**:

```
_put_drop_oldest(佇列空)    0.406 us
_put_drop_oldest(滿載丟最舊) 0.958 us
_enqueue(notify=True,佇列空) 1.099 us   ← 兩條佇列各一次 put
asyncio.Queue put → worker get  p50 3.2 us / p95 4.0 us / p99 4.5 us
```

### 4.2 量化:佇列從來沒滿過,但**Discord 一直在丟**

```
$ grep -c "佇列滿" logs/server-20260911-0905.log   → 0
$ grep -c "佇列滿" logs/server-20260910-0905.log   → 0
$ grep -c "佇列滿" logs/server-20260909-0812.log   → 0
```
**全 20 份 log 零命中「佇列滿」。** 背壓路徑從未觸發 —— 合理:訊號量級是
**~700 列/日 ≈ 0.04 列/秒**(`an1.py`:09-09 670 / 09-10 719 / 09-11 686),
而佇列 1000 / 100。

**但同一批 log 的另一條 grep 不是 0**:

```
$ grep -c "Discord 每分鐘上限\|Discord 節流" logs/*.log | grep -v ':0$'
logs/server-20260828-0814.log:12
logs/server-20260831-0810.log:9
logs/server-20260901-0857.log:6
logs/server-20260902-0810.log:7
logs/server-20260903-0823.log:15
logs/server-20260909-0812.log:8
```

`_allow_discord`(`signal_hub.py:1486-1497`)是**第二條、沒有計數器**的丟棄通道:
60 s 滾動窗滿 `discord_per_min=30` 就 `return False`,`_send_discord` 直接 return、
**不重排、不補送、`dropped_discord` 不加 1**。

實測(`an4.py`,09-09 jsonl 回推):

```
09:00:00–09:02:00 notify 列 = 47
  kind: surge 18 / crash 10 / surge_pullback 13 / limit_lock 2 / limit_open 1 / policy 3
  同 (code,time) 合批後訊息數 = 43
  每分鐘訊息數: {'09:00': 34, '09:01': 9}     ← 34 > 30,節流必觸發
```
log 側對得上:09-09 09:00:53–09:01:11 共 **8 則**被擋。
09-03 開盤 09:00:43–09:01:03 共 **15 則**被擋。

**而且擋掉的是哪一則,log 大多說不出來**:

```
09:00:53,383 WARNING Discord 每分鐘上限 30 已滿,本則只進 WS/jsonl        ← 無 id
09:00:57,384 WARNING Discord 節流擋下合併 2 則:2026-09-09-r-…-5475-surge-…  ← 只有合批才帶 id
```
`_send_discord:1530-1536` 只在 `len(rows) > 1` 時補一則帶 id 的 WARNING;單則被擋時
`_allow_discord` 自己那句沒有 id。09-09 八則裡 **七則無法從 log 指認**。

**影子期的具體暴露**:政策列與 `surge_pullback` 在同一個 FIFO 配額裡競爭。
09-09 的三則政策列落在 09:01:25 / 09:01:56,而 `_discord_sent` 是 60 s 滾動窗
(不是日曆分鐘)—— 09:01:25 那兩則(3441 的 P + S)當時的窗裡還裝著 09:00:25 之後的
三十幾則 surge/crash,是**真的踩在界上**。spec #192 影子期最重要的那一種列,
沒有任何優先權。

### 4.3 `_discord_worker` 的合批(確認寫得對)

`signal_hub.py:1198-1234`:單槽 `_discord_pending`(不回塞佇列,避免順序亂)、
`task_done()` 恰一次(少一格關機吊死、多一格 worker 猝死)。

**合批在同一 tick 內一定成立**,因為 `on_tick` 的整個 slot 迴圈 → `_fanout` → `_emit`
→ `_enqueue` 全在**同一個無 await 的同步區塊**內跑完,worker 要到下一輪 loop 才醒;
醒來時同 tick 的全部列已經在佇列裡,`get_nowait()` 迴圈一次撈完。**這是對的,不要動。**

---

## 5. `_emit` / `_emit_policies` 的欄位組裝成本與 `notify` 閘語意

### 5.1 `_emit`(`signal_hub.py:1012-1040`)—— 每則事件 ~700 次/日

```
_event_id()                     0.152 us
_emit(一般列,佇列空)           2.24 us    ← 含 15 鍵 dict + publish + enqueue
  ├ WsBroadcaster.publish 0 client   0.136 us
  │                       1 client   0.470 us
  │                       4 client   1.420 us
  │                       8 client   2.892 us
  └ _enqueue                         1.099 us
json.dumps(一般列 14 鍵)        2.61–3.05 us
```

700 次/日 × 2.24 µs = **1.6 ms 全日**。零優化空間也零必要。

### 5.2 `_emit_policies`(`signal_hub.py:1042-1165`)—— 只在掃單簇事件時 ~50 次/日

實測(`bench_pol.py`,真實 `data/stock_watchlist.json`:80 檔 / 12 組,測試檔 3481 屬「散熱」3 檔組):

```
resolve_groups(12 組)           1.11 us
evaluate_policies(3 同伴)       2.71 us
_emit_policies(命中 1 條政策)   11.50 us      政策列鍵數 = 33
json.dumps(政策列)              7.96 us
format_policy_group_text        3.73 us
```

最大族群是「無塵室」32 檔 → `resolve_groups` / `evaluate_policies` 隨同伴數線性,
上界仍在十幾 µs。**50 次/日 → 完全不是問題,不要動。**

### 5.3 `notify` 閘語意(CLAUDE.md §4 契約,已確認兩邊一致)

- 一般列:`notify = rule["notify_discord"]`(`signal_hub.py:1014`),逐列蓋在 payload 上。
- 政策列:`notify = first and not late`(`signal_hub.py:1133`),`first` = 同檔同政策當日首筆
  (`_policy_touch[(code, policy)]`),`late` = 時刻 > `policy_push_end`(12:30:00)。
- **`_enqueue(row, notify=)`(`:1167-1184`)只擋 Discord 佇列** —— jsonl 無條件入列。
- `self._publish(payload)`(WS)在 `_enqueue` **之前**、與 `notify` 完全無關。

→ 契約「jsonl / WS / rail 永遠不受 `notify` 影響(真相源)」在 code 上成立。
prod 實證:09-11 686 列中只有 284 列 `notify=true`(cdp_cross 295 + vol_burst 30 +
sweep_cluster 49 = 374 列 quiet,加上 late 政策列)。

**一個順序上的細節**:`_emit` 先 `_publish` 後 `_enqueue`。若 `_publish` 拋,
`_fanout`(`:632-644`)的 per-event 傘接住 → **該列進了 WS、沒進 jsonl**。
實務上 `publish=stock_ws.publish`(`app.py:833`)= `WsBroadcaster.publish`,
內部 `QueueFull` 全部 suppress、不拋 → 現況安全。但這是一條「換掉 publish 注入就
靜默破掉」的隱式依賴,值得在 docstring 記一句。

### 5.4 WS 出境:per-client 各編一次(已知事實的本區確認)

`WsBroadcaster.publish` fanout 的是 **dict**;序列化在 `relay._send` → `websocket.send_json`
(`ws.py:263`)才發生,每個 client 各一次 `json.dumps`。
訊號列 ~700/日 × 8 client × 2.6 µs = **15 ms 全日**。不值得改。

但要記帳的是:**訊號列與逐筆打包共用同一個 `stock_ws`(maxsize=1000,`app.py:554`)**。
逐筆打包把佇列灌滿時,訊號列會被 `drop-oldest` 一起丟掉,而訊號沒有 `seq` 跳號自癒 ——
它只能等前端 5 分鐘的 `today` 輪詢。實測全日零丟包,所以現況沒發生。

---

## 6. 換日(`_pending_date`)與 rollover 期間的行為

### 6.1 三段

| 階段 | 誰呼叫 | hub 做什麼 |
|---|---|---|
| stage1(08:00 checkpoint / 快路徑) | `stock_engine:949-951` → `hub.on_rollover_pending(new_date)` | `signal_hub.py:646-655`:**先清暫存區**(MFS-2)→ `_staged_date = new_date` → `request_basis(全 watch, staged=True)` |
| pending 窗(stage1 後 ~ 新日首筆前) | — | `on_book` **被 engine 擋掉**(`stock_engine:1365` `_pending_date is None`);`on_tick` **不被擋**,靠 detector 內 `tick.trade_date != ctx.trade_date`(`signal_state.py:297`)回 [] |
| stage2(新日首筆 tick) | `stock_engine:1124-1127` → `hub.on_rollover()` | `signal_hub.py:657-712`:清過期重試記帳 / 取消在途 timer → **逐 slot `reset_day()`** → 清 `_policy_touch` / `_multi_group_warned` → 印昨日 `peers_fn` 失敗彙總 → **promote 暫存區** → 差集補抓 |

### 6.2 兩個要記帳的點

**(a) 同一個危害用了兩種不同機制擋。**
`on_book` 靠 engine 的 `_pending_date` 閘;`on_tick` 靠 detector 內 `ctx.trade_date` 比對,
而 `ctx.trade_date` 來自 `_context` 的 `self._trade_date_fn()`(= `engine.trade_date`)。
兩者**沒有共同的不變式測試**。若哪天 `_context` 的日別來源改成別的(例如 hub 自己的
牆鐘),tick 路的守門會**靜默消失**,而症狀是「換日當天早上發一則昨日 latch 的假 limit_open」。

實務上 pending 窗(08:00 → 08:45/09:00)整段落在 `_in_session`(09:00–13:30)之外,
detector 第一行就早退 → **現況零暴露**。這是「兩道閘剛好都在」的幸運,不是設計保證。

**(b) stage2 的 `reset_day()` 是逐 slot 的 O(規則數 × 14 張表 clear)。**
7 顆 detector × 14 個 dict/deque 的 `.clear()`,一天一次,µs 級。不是問題。

**(c) promote 是整批取代 + 差集補抓**(`:698-707`):暫存區沒抓到的檔會被
`missing = sorted(set(self._watch) - set(self._basis_cache))` 撈回來重排。
寫得對(註解已說明「不補抓的話那些檔整天沒有 CDP 且不自癒」)。**不要動。**

**(d) `on_watchlist`(`:714-731`)每次都呼 `_refresh_groups()`(`:733-772`)**,
而生產端 `groups_fn = lambda: load_watchlist(wl_path)["groups"]`(`app.py:844`)
是**同步檔案讀**,跑在 event loop 上。頻率 = 自選變更 / 開機 / 盤前篩選落檔(每日一次
~60 檔寫入群組)。檔案 ~10–30 KB,單次 < 1 ms。記帳用,**不值得改**。

---

## 7. `_CLOSE_FLUSH_TIMEOUT`(5.0 s)= `LIFESPAN_SLACK_SECS`(5.0 s)的關機預算衝突

### 7.1 帳面上已經超支

`shutdown_budget.py` 的三方同源(CLAUDE.md §4):

```
run_grace_secs() = WS_DRAIN_SECS(5)
                 + TC4_LANE_DEPTH(2) × close_worst_secs(34)     = 68
                 + COM_JOIN_TIMEOUT_SECS(5)
                 + LIFESPAN_SLACK_SECS(5)
                 = 83 s
```

`LIFESPAN_SLACK_SECS` 的 docstring 逐字寫著它要涵蓋:
> 「TC4 之外的段(crosscheck cancel / breadth / **signals 的 bot.close + hub drain**)+ 執行緒排程。」

而 `SignalHub.close()`(`signal_hub.py:551-577`)**光是 jsonl drain 的逾時就是 5.0 s**:

```python
await asyncio.wait_for(self._jsonl_queue.join(), _CLOSE_FLUSH_TIMEOUT)   # :564
```

→ **signals 一段就吃掉整個 slack,screen / breadth / crosscheck / `bot.close()` /
執行緒排程全部沒有預算。** 而 `app.py:1240` 的 lifespan 是**序列**:
`crosscheck → screen → breadth → signals → (TC4 並行 lane) → capital`,
signals 慢 5 s 就是 TC4 lane 晚 5 s 起跑。

### 7.2 但實際關機時會怎樣?(實測)

**健康路徑實測:14 次關機,signals 段全部 0.00–0.01 s。**

```
$ grep -h "關機收尾" logs/*.log | tail -14
2026-09-11 09:05:06 關機收尾 0.21s:screen 0.00s / breadth 0.00s / signals 0.00s / … / txo 0.21s
2026-09-10 09:05:56 關機收尾 0.30s:… signals 0.00s …
2026-09-09 22:48:33 關機收尾 0.58s:… signals 0.00s …
…(14 筆全部 signals 0.00s)
```

理由:佇列常態是空的(0.04 列/秒),`join()` 立刻返回。
**最壞情況也不痛**(`bench_lat.py` 實測,佇列灌滿 1000 則):

```
jsonl worker 排空 1000 則(close 的 join 對象)   0.356 s    ← _CLOSE_FLUSH_TIMEOUT = 5.0 s
_flush_pending 1000 則(逾時後的保底)            0.367 s
_append_jsonl(同步,NTFS)  p50 208.5 / p95 271.0 / p99 353.7 us
jsonl worker 一則(含 to_thread)p50 343.1 / p95 426.9 / p99 476.6 us
```

→ **5.0 s 的逾時是實際需求的 14 倍。**

### 7.3 真正的危險不是 drain,是 `_flush_pending` 與共用 executor

`_jsonl_worker`(`:1189`)與 `_flush_pending`(`:1244`)都用 `asyncio.to_thread`
= loop 預設 ThreadPoolExecutor(本機 20 workers),鄰居是**最壞 20–30 s 且不可中斷的
TC4 歷史取數**(`daily_bars` / `bars_range` / basis sweep / 回填 worker)。

關機當下:`close()` 先 `self._closing = True` 停收件 → `wait_for(join(), 5.0)`。
若此刻 20 個 worker 全被 TC4 取數佔住,`_jsonl_worker` 的下一次 `to_thread`
**排在它們後面** → `join()` 必定逾時 → 走 `_flush_pending()`:

```python
async def _flush_pending(self) -> None:                      # :1236-1245
    rows = [...]                                             # 把剩餘整批 get_nowait 出來
    for row in rows:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._append_jsonl, row) # ← **沒有逾時**
```

`contextlib.suppress(Exception)` 不會讓 `await` 提早返回;它只吞例外。
**這是關機路徑上唯一一段沒有上界、也沒有被 `shutdown_budget` 任何一項記到的時間。**
最壞 = 1000 則 × (等一格 executor 空出來的時間)。
TC4 半死時單格最壞 20–30 s → 這一段可以是**分鐘級**。

失效後果與 CLAUDE.md §4 記載的完全相同:run.ps1 在 83 s 到期硬殺,落在 TC4 還在退訂的
中途 → 健康 session 也變殭屍 → 下一台開頭 ~60 s 零推播,零錯誤訊號
(只有 TC4 log 的 `RemoveLoginInfo` 晚 60 s 才看得到)。

### 7.4 `bot.close()` 也沒有逾時

`discord_bot.py:490-491` `await self.client.close()` —— discord.py 的 gateway 收攤,
無 timeout 參數。正常毫秒級,但它也算在同一個 5.0 s slack 裡。

---

## 8. 端到端延遲:一筆成交 → 訊號列出現在 rail / Discord

全部區段實測於 repo `.venv`(ProactorEventLoop)。標「推估」的是沒有儀器量不到的。

| # | 區段 | 位置 | 成本 | 基礎 |
|---|---|---|---|---|
| A | ZMQ listener thread → loop(`call_soon_threadsafe`) | `stock_engine.py:1150` | p50 **46.6 µs** / p95 64.4 / p99 74.4 / max 273(閒置 loop) | measured |
| B | engine `_handle_quote` 前段 → `hub.on_tick` | `stock_engine.py:1200-1352` | 不在本區塊(見 B04) | — |
| C | hub membership gate | `signal_hub.py:599` | **0.06–0.09 µs** | measured |
| D | `_context()` 建構 | `signal_hub.py:992` | **1.21 µs**(有簿)/ 1.12(無簿)。**帶成交的 quote 建 2 次** | measured |
| E | slot 迴圈 7 × `detector.evaluate` | `signal_hub.py:607-614` | **73–85 µs/tick** @窗長1501;**≈ 25 µs + 0.0326 µs × 窗長** | measured |
| F | slot 迴圈 7 × `evaluate_book` | `signal_hub.py:625-631` | **20.6 µs/quote**(盤中)/ 3.8 µs(盤外) | measured |
| G | `_fanout` → `_emit`(每則事件) | `signal_hub.py:632 / 1012` | **2.24 µs**(`_event_id` 0.15 + 15 鍵 dict + publish + enqueue) | measured |
| H | `_emit_policies`(只在掃單簇) | `signal_hub.py:1042` | **11.5 µs** / 命中 1 條(3 同伴);33 鍵列 | measured |
| I | `WsBroadcaster.publish` fanout | `ws.py:68` | **0.14 µs + 0.34 µs/client**(8 client = 2.9 µs) | measured |
| J | WS 出境 per client(`send_json`) | `ws.py:263` | `json.dumps` **2.6 µs** × N client + ASGI/loopback **~50–200 µs** | dumps measured / 傳輸推估 |
| K | `_enqueue` 兩條佇列 | `signal_hub.py:1167` | **1.10 µs**(空)/ 0.96(滿載丟最舊) | measured |
| L | jsonl:queue put → worker get | `signal_hub.py:1187` | p50 **3.2 µs** / p99 4.5 | measured |
| M | jsonl 落檔(`to_thread` + open/write/close) | `signal_hub.py:1189 / 1412` | p50 **343 µs** / p95 427 / p99 477 | measured |
| N | Discord:worker 合批 + 節流判定 | `signal_hub.py:1198 / 1486` | < 5 µs | measured |
| O | Discord 送出(bot `channel.send`) | `signal_hub.py:1556` | **~100–400 ms** | 推估(未對外發網路) |
| P | Discord webhook fallback(`to_thread(urlopen)`) | `signal_hub.py:1563` / `notify.py` | **~150–600 ms**;429 時最壞佔一格 pool thread **10 s** | 推估 |
| Q | Discord 節流擋下 | `signal_hub.py:1486` | 0 ms(直接 return,**永不補送**) | measured(log:09-03 15 則 / 09-09 8 則) |

**加總**

```
成交 tick → 訊號列出現在 rail(WS)
  = A 46.6 + D 1.2 + E 73~85 + G 2.2 + I 0.5 + J 2.6 + 傳輸 ~100 µs
  ≈ 0.23 ms (p50);p99 ≈ 0.35 ms(未含 Windows 15.6 ms timer 抖動地板 —— 這條路徑
    是 call_soon 直送,不經 sleep,所以不吃那個地板)

成交 tick → jsonl 落地
  = 上面 + K 1.1 + L 3.2 + M 343 µs ≈ 0.58 ms (p50) / 0.73 ms (p99)

成交 tick → Discord 卡片
  = 上面 + N < 5 µs + O 100~400 ms ≈ 100~400 ms
  或 = 0(被節流擋下,永不補送 —— 開盤實測每天個位數到十幾則)
```

**尾延遲的真實來源不在本區塊**:E 這一段是**同步跑在 event loop 上**,所以它的成本
會轉成「同一條 loop 上其他工作的排隊延遲」,而不是訊號自己的延遲。
訊號自己的 rail 延遲是 sub-ms;真正要盯的是 **E × 頻率 = 0.19% loop**(§2.4),
以及 §9 的放大軸。

---

## 9. 放大軸:REST 從 UI 就按得出來的預算炸彈(本區塊的角度)

`MAX_RULES = 30`(`signal_rules.py:54`)× `WATCHLIST_LIMIT = 150`(CLAUDE.md §4)
× `vol_burst.window_secs ≤ 3600`(`signal_rules.py:73-79`)。

以本區塊實測的成本模型 `3.5 µs × 規則數 + 0.0326 µs × 窗長` 外推:

| 情境 | on_tick 成本 | 全日 tick 推估 | loop 佔用 |
|---|---|---|---|
| 現況 7 規則 / 80 檔 | 73 µs @窗長1501 | 518k | **0.19%**(實測回推) |
| 30 規則 / 80 檔 | 105 µs 固定 + 窗 | ~518k | ~0.55%(推估) |
| 30 規則 / 150 檔 | 105 µs 固定 + 窗 | ~971k | ~1.0%(推估) |
| 30 規則 / 150 檔 / 一條 `window_secs=3600` 且熱門股 10 tick/s | 窗長 36,000 → **1,174 µs/tick/規則** | — | **單檔單規則就 11.7 ms/s**(推估) |

最後一列是 B06 F-07 已指出的;本區塊的補充是:**規則數這一軸也要記帳** ——
30 條規則 = 30 顆完整 detector × 150 檔 × 各自的窗,記憶體上界是現況的 4.3 倍 × 檔數 1.9 倍。

---

## 10. Findings

> 嚴重度以「這是一個要下實單的系統」為準:影響資金 / 稽核 / 關機正確性的往上抬,
> 純 CPU 浪費在現況量級下一律壓低。

### F-01 遷移種子卡的 `rule_id` 每次重啟換一次 → 決定性訊號 id 契約已破(HIGH,正確性)

**位置**:`copycat/signal_rules.py:456-461`(`_append_seed`)+ `:247-249`(`new_rule_id`)
+ `:522-533`(`load_rules` 的「載入時不回寫檔案」)

```python
# _append_seed(456-461)
epoch = int(time.time())          # ← 每次載入都是「現在」
seq = len(out)
rule_id = new_rule_id(epoch, seq) # r-<epoch>-<seq:03d>
```

`load_rules` 的 docstring 明寫「**載入時不回寫檔案**,磁碟要到第一次 upsert 才以 v4 落檔」。
prod 的 `data/signal_rules.json` 還停在 `_cache_version: 1`(B06 已證),所以
**每一次 server 啟動都重跑 v1→v2→v3→v4 整條遷移鏈**,三張種子卡(`爆拉回檔 1%` /
`爆拉回檔 2%` / `掃單簇`)每次拿到**新的** id。

log 實證(`server-20260911-0905.log`,單一 session 內):
```
09:05:17,528 訊號規則檔 v1→v2:規則 'r-1785975520-000' 補 rearm_dwell_secs=300.0
09:05:17,529 訊號規則檔 v2→v3:append 種子卡 '爆拉回檔 1%' …
09:05:17,529 訊號規則檔 v3→v4:append 種子卡 '掃單簇' …
```

jsonl 實證(`an2.py`,**同一天**出現兩組 rule_id):
```
20260908.jsonl  surge_pullback r-1788791576-004 (43 列)  ‖  r-1788830602-004 (40 列)
                sweep_cluster  r-1788791576-006 (12 列)  ‖  r-1788830602-006 (4 列)
                policy         r-1788791576-006 ( 8 列)  ‖  r-1788830602-006 (4 列)
20260910.jsonl  surge_pullback r-1789002367-004 (90 列)  ‖  r-1788965322-004 (16 列)
20260911.jsonl  surge_pullback r-1789088717-004 (90 列)  ‖  r-1789058168-004 (15 列)
```
而原始四條(`r-1785975520-*`)橫跨所有日期**逐字不變** —— 對照組成立。

**影響**:
1. `_event_id`(`signal_hub.py:1690-1697`)的 docstring 宣告「不依賴 process 記憶,
   重啟後重發同一事件會得到同一個 id,前端與 jsonl 都據此去重」。
   **對這三條規則(以及所有政策列,id 用的是 sweep_cluster 規則的 id)已經不成立。**
2. 影子期(spec #192,09-08 起四週)的政策列對帳:任何以 `rule_id` 分群的統計會把
   同一條規則切成 N 份(N = 那段期間的重啟次數)。
3. 前端 rail 的 id 去重:盤中重啟後若同一事件重發(例:同秒同檔),兩則 id 不同 → 不去重 → 重複列。
   實務機率低(detector 狀態重啟即空),但這正是契約本來要保證的那件事。

**修法(二選一)**:
- (a) 種子卡改用**決定性 id**(例 `r-seed-surge-pullback-1` / `r-seed-sweep-cluster`)。
  改動面積小,但 id 格式與 `new_rule_id` 的 `r-<epoch>-<seq>` 分家 —— 要確認前端與
  `normalize_rule` 對 id 只當不透明字串(需查證)。
- (b) `_load_or_migrate_rules`(`signal_hub.py:446-453`)在遷移**發生過**時立刻
  `save_rules` 回寫 v4。代價 = 放棄 `load_rules` docstring 寫的「回退窗」
  (期間舊碼可直接讀原檔),要 user 拍板。

**風險**:改 id = 改 `_event_id` 的輸入 → 當日 jsonl 會出現新舊兩組 id。
選一個沒有訊號的時段(盤後)做,並在 next-time 記一筆。

---

### F-02 Discord 節流是第二條丟棄通道,`dropped_discord` 對它視而不見(HIGH,可觀測性/稽核)

**位置**:`copycat/server/signal_hub.py:1486-1497`(`_allow_discord`)、
`:1516-1518` / `:1524-1529`(`_send_discord` 的兩個擋下點)、`:416-421`(計數器)

```python
def _allow_discord(self) -> bool:
    ...
    if len(self._discord_sent) >= self._cfg.discord_per_min:
        logger.warning("Discord 每分鐘上限 %d 已滿,本則只進 WS/jsonl", ...)
        return False      # ← 不重排、不補送、不計數
```

**證據**:§4.2。09-03 15 則 / 09-09 8 則被擋;同期 `grep 佇列滿` = 0、
`dropped_discord` = 0。而 `dropped_jsonl` / `dropped_discord` / `dropped`
(`:416-421`)**在 prod 零讀者** —— `/api/health` 不含、無 route、無週期 log
(`grep -rn "dropped_discord\|hub.dropped" copycat/` 只有寫入點)。

**影響**:CLAUDE.md §1 的影子期判準 `grep 佇列滿 logs/server-*.log 為 0` 讀起來像
「Discord 全數送達」,實際上只證明了**佇列**沒滿。真正的損失在節流,而且
單則被擋時 log **不帶 id**(`:1493` 那句沒有 `row.get("id")`)—— 09-09 八則裡七則無從指認。

**修法**(零契約、零相依):
1. `_allow_discord` 加 `self.throttled_discord += 1`,並把 `row["id"]` 傳進去一起 log。
2. 把 `dropped_jsonl` / `dropped_discord` / `throttled_discord` / 兩條佇列 high-water mark
   掛進每分鐘一行 INFO(或 `/api/health` 的 `signals` 區塊)。
3. 影子期判準改成「`grep 節流擋下` 與 `grep 佇列滿` 都是 0」。

---

### F-03 `_flush_pending` 無逾時 + 走共用 executor = 關機路徑上沒有記帳的一段(HIGH,關機正確性)

**位置**:`copycat/server/signal_hub.py:1236-1245`

```python
async def _flush_pending(self) -> None:
    rows = [...]                                              # 佇列剩餘整批取出
    for row in rows:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._append_jsonl, row)  # ← 無逾時
```

`contextlib.suppress(Exception)` 只吞例外,不會讓 `await` 提早返回。
`to_thread` 走 loop 預設 20-worker executor,鄰居是最壞 20–30 s 且**不可中斷**的 TC4 取數。
TC4 半死時:`wait_for(join(), 5.0)` 必逾時 → 進 `_flush_pending` → 每一則都要等一格
executor 空出來 → 最壞分鐘級,而 `shutdown_budget.LIFESPAN_SLACK_SECS` 完全沒算它。

後果 = CLAUDE.md §4 逐字記載的那個:run.ps1 83 s 到期硬殺落在 TC4 退訂中途 →
健康 session 變殭屍 → 下一台開頭 ~60 s 零推播,零錯誤訊號。

**修法**:`_flush_pending` 整段包 `asyncio.wait_for(..., FLUSH_BEST_EFFORT_SECS)`,
並把 `_CLOSE_FLUSH_TIMEOUT + FLUSH_BEST_EFFORT_SECS + bot_close_budget <
LIFESPAN_SLACK_SECS` 加進 `tests/server/test_shutdown_budget.py` 的不等式。

---

### F-04 `_CLOSE_FLUSH_TIMEOUT`(5.0)恰等於 `LIFESPAN_SLACK_SECS`(5.0),帳面超支(MEDIUM,關機正確性)

**位置**:`signal_hub.py:109` ↔ `shutdown_budget.py:LIFESPAN_SLACK_SECS`

`LIFESPAN_SLACK_SECS` 的 docstring 自承要涵蓋 crosscheck cancel / breadth /
**signals 的 bot.close + hub drain** + 執行緒排程,而 signals 一段的 drain 逾時就是 5.0。

**實測反證(不要誇大)**:14 次關機 signals 段全部 **0.00–0.01 s**;佇列灌滿 1000 則
的最壞 drain 也只要 **0.356 s**。所以這是**帳面**問題不是**現場**問題 ——
5.0 s 是實際需求的 14 倍。

**修法**:把 `_CLOSE_FLUSH_TIMEOUT` 降到 1.5 s(仍是實測最壞的 4 倍),
並讓它**從 `shutdown_budget` 讀**(三方同源的第四個讀者),
`tests/server/test_shutdown_budget.py` 加一條不等式釘住。

---

### F-05 `on_tick` / `on_book` 的 slot 迴圈不看 `enabled`,而「停用仍推進」的設計理由在此架構下不成立(MEDIUM,可證明的零風險最佳化)

**位置**:`signal_hub.py:607`(`for slot in self._slots.values():`)與 `:625`;
辯護出處 `signal_state.py:19-23`(design R2)

**證明**(§3.2):`_RuleSlot` 唯一建構點 `_make_slot`(`:455`)→ 唯一兩個呼叫端
`_load_or_migrate_rules`(:452)/ `upsert_rule`(:493);改 `enabled` 的唯一路徑是
`PUT /rules/{id}`(`app.py:1593`)→ `upsert_rule` → **全新空狀態 detector**。
→ 停用期間推進的狀態**永遠不會被任何人讀到**。

**實測代價**:7 條全部停用仍付 **24.84 µs/tick**(vs 理想 < 2 µs)。

**修法**:`on_tick` / `on_book` 迴圈開頭加 `if not slot.enabled: continue`(兩行)。
逐字行為等價。

---

### F-06 `_distribute` / `_seed_slot` 只看 `kind` 不看 `enabled`,停用的 CDP 規則被餵基準後比啟用的還貴(MEDIUM,潛在)

**位置**:`signal_hub.py:986-990`(`_distribute`)、`:524-529`(`_seed_slot`)

**實測**(`bench_cdp.py`):enabled=False 且被餵 basis = **9.30 µs/tick**,
比 enabled=True 的 8.95 µs **還貴**;不餵 basis 是 7.30 µs。淨代價 2.0 µs/tick/規則。

**誠實標註**:prod 現況 CDP 規則是 `enabled=True`(只有 `notify_discord=false`),
所以這條**現在沒有發生**。做 F-05 之後這條就只剩「少寫一次 dict」的意義,
但仍值得加 `and slot.enabled` —— 停用的規則被餵基準本身就是語意噪音。

---

### F-07 `on_book` 對每一則 quote 無條件跑 7 × `evaluate_book`,不判簿有沒有變(MEDIUM,熱路徑)

**位置**:`stock_engine.py:1365-1366`(呼叫點,唯一的閘是 `_pending_date is None`)、
`signal_hub.py:616-630`

**實測**:20.6 µs/quote(盤中、7 顆)。`evaluate_book` 的產出 = `limit_open`,
prod 實證 09-11 **5 則 / 全日**、09-09 **6 則**。

**修法**:engine 側加「這則 quote 有沒有動到簿」旗標(`_apply` 已有
`recovered` / `was_meta_none` 這類轉態旗標,加一個同款成本低)。
**行為契約**:`limit_open` 靠的是「尾盤解鎖無成交也抓得到」(design §3.5b),
所以旗標必須把「賣側限價檔由空變有」算成簿變動 —— 要紅先行釘住。

---

### F-08 `_context()` 對帶成交的 quote 建兩次(LOW-MEDIUM,熱路徑)

**位置**:`stock_engine.py:1352`(on_tick 內建一次)與 `:1366`(on_book 內再建一次);
建構點 `signal_hub.py:992-1010`

**實測**:1.21 µs × 2 = 2.4 µs/quote。兩次除了 `day_volume` 完全相同,
各跑兩次 `_best_limit_price`。做 F-07 之後大部分 quote 根本不會走第二次 → 自然消失。

---

### F-09 背壓計數器零 prod 讀者(LOW-MEDIUM,可觀測性)

**位置**:`signal_hub.py:416-421`

`dropped_jsonl` / `dropped_discord` / `dropped` 只有寫入點,
`grep -rn "dropped_discord\|hub\.dropped" copycat/` 在 prod code 零命中讀者。
`/api/health` 刻意不含引擎健康度(其 docstring)。→ 背壓的全部證據只在 log 的節流 WARNING。
與 F-02 合併修。

---

### F-10 `_emit` 先 `publish` 後 `_enqueue`,隱式依賴「publish 不拋」(LOW,脆弱性)

**位置**:`signal_hub.py:1035-1036`

```python
self._publish(payload)                                   # WS 同步先送
self._enqueue({**payload, "trade_date": trade_date}, notify=notify)
```
`_fanout`(`:632-644`)的 per-event 傘會吞掉 `_publish` 的例外 → 該列**進了 WS、沒進 jsonl**,
而 jsonl 是真相源。現況安全:`publish=stock_ws.publish`(`app.py:833`)= `WsBroadcaster.publish`,
內部全 suppress。**修法 = docstring 記一句「注入的 publish 必須 never-raise」**,不改 code。

---

### F-11 hub 零耗時儀器(MEDIUM,量化系統的前提)

`SignalHub` 對外只有三個丟棄計數(且無人讀)。**沒有任何**
「這一 tick 評估花多久」「每秒評估幾次」「哪條規則最貴」「窗長分佈」的數字。
本報告所有數字都是離線 micro-benchmark + log 回推,**沒有一個是線上量到的**。

**修法**(純 stdlib):`on_tick` / `on_book` 進出 `time.perf_counter_ns()` → 固定桶陣列,
每分鐘一行 INFO 印 p50/p95/p99 + 次數 + 窗長分佈。零相依、零契約。
**這是 §11 fix_plan 每一步的量測判準能真的跑起來的前提。**

---

### F-12 `_basis_jobs` 是 hub 唯一的無界佇列(LOW,記帳)

**位置**:`signal_hub.py:394`。生產者上界 = 自選檔數 × 2(當日 + staged)+ 有限重試
(`_BASIS_MAX_RETRIES = 2`),不會真的爆。記帳用:日後若加「定時全量重抓基準」就沒保護。

---

### F-13 rollover pending 期間 tick 路與簿路用兩種不同機制擋,無共同不變式測試(LOW,脆弱性)

見 §6.2(a)。現況零暴露(pending 窗落在 `_in_session` 之外),但這是巧合不是保證。
**修法 = 一條測試**釘住「pending 期間 `on_tick` 不得產出事件」,而不是改 code。

---

### F-14(反向)雙佇列 + `_put_drop_oldest` + 單槽合批 —— 寫得對,不要動

見 §4。實證全日零丟包、量級 0.04 列/秒、佇列 1000/100 綽綽有餘。
`task_done()` 的記帳(少一格關機吊死 / 多一格 worker 猝死)是整段最容易寫錯的地方,
而現況寫對了。改動風險遠大於收益。

---

### F-15(反向)`_emit_policies` / `signal_policy.py` / `format_policy_group_text` —— 不要動

50 次/日 × 11.5 µs = **0.6 ms 全日**。`resolve_groups` 1.11 µs、`evaluate_policies` 2.71 µs。
`signal_policy.py` 是純函式零 IO。任何最佳化都是負收益。

---

### F-16(反向)不要在本區塊引 orjson / msgspec 寫 jsonl

`json.dumps(政策列 33 鍵)` = 7.96 µs × 50 次/日 = **0.4 ms 全日**。
而 CLAUDE.md §1 的影子期判準逐字寫著 `grep '"kind": "policy"'`(帶空白),
CLAUDE.md §4 的 T+1/T+2 回填契約以 **byte 比對**釘住鍵序與浮點字面。
**收益 0.4 ms/日,風險是兩條明文契約。不做。**

---

## 11. 改造順序(每一步的量測判準)

> 原則:先量後改;零契約的先做;動到 design 決定的排最後並停等 user 拍板。

| # | 做什麼 | 為什麼排這裡 | 規模 | 量測判準(怎麼量才算改對) | 退場 |
|---|---|---|---|---|---|
| 1 | **加最小儀器**:`on_tick`/`on_book` 耗時桶(10 µs 一格)+ 評估次數 + 窗長分佈 + `throttled_discord` 計數 + 兩條佇列 high-water mark,每分鐘一行 INFO | 後面每一步都要靠它證明;現況零線上數字(F-11) | S | 盤後 `grep "訊號分派" logs/server-*.log` 拿得到 p50/p95/p99;p99 < 200 µs、`每秒評估次數 × p50 < 10 ms/s` | 純新增 log,revert 一個 commit |
| 2 | **`_allow_discord` 帶 id + 計數**,影子期判準改成「`grep 節流擋下`+`grep 佇列滿` 都是 0」 | 稽核缺口,與 1 同一批(F-02) | S | 次一交易日開盤後 `grep "節流"` 每一則都帶得出 `id`;數量與 jsonl 的 notify 列數對得上 | 同上 |
| 3 | **釘死種子卡 `rule_id`**(決定性 id 或載入即回寫 v4) | 正確性契約已破(F-01),而且**越晚修,被污染的 jsonl 越多** | M | 連續兩次重啟 `curl /api/stock/signals/rules` 的 `id` 逐字相同;次一交易日 jsonl 每個 kind 只出現**一組** rule_id | 改回 `int(time.time())`;jsonl 舊列不動 |
| 4 | **`if not slot.enabled: continue`**(on_tick / on_book)+ `_distribute` / `_seed_slot` 同加 `enabled` | 可證明逐字等價(F-05/F-06),零風險 | S | 儀器(步驟 1)顯示:把全部規則停用後 `on_tick` p50 從 ~25 µs 降到 < 2 µs;`pytest -q` + `copycat validate` 全綠;sweep golden fixture 綠 | 拿掉兩行 |
| 5 | **`_flush_pending` 加逾時 + `_CLOSE_FLUSH_TIMEOUT` 改從 `shutdown_budget` 讀** | 關機正確性(F-03/F-04);與 TC4 lane 的預算同源 | M | `tests/server/test_shutdown_budget.py` 新不等式綠;真環境 Ctrl+C 後 `grep "關機 signals 段"` → 「關機收尾」的 signals 欄 < 1.5 s;run.ps1 不觸發 taskkill | 常數改回、逾時拿掉 |
| 6 | **jsonl / notify fallback 專屬單執行緒 executor**(`ThreadPoolExecutor(max_workers=1)`) | 讓 5 的逾時真的有意義:不再與 TC4 殭屍同池 | M | 儀器顯示 jsonl 落檔 p99 在 TC4 忙窗(開盤 basis sweep)期間不再跟著飆;`grep "T+1/T+2"` 的 13:40 耗時不變 | 改回 `to_thread` |
| 7 | **engine 側「簿有沒有變」旗標 → 有條件呼 `on_book`** | 砍掉 F-07 的 20.6 µs/quote + F-08 的第二次 `_context` | M | 儀器的 `on_book` 次數 / `on_tick` 次數比值明顯下降;**紅先行**釘「尾盤無成交解鎖仍發 `limit_open`」;次一交易日 `limit_open` 列數與前五日同量級 | 旗標恆 True = 回到現況 |
| 8 | **`vol_burst` 滾動窗改 running sum**(B06 F-01,本區塊的 `E` 段主成本) | 把 `E` 的窗長依賴拿掉,同時讓 `window_secs ≤ 3600` 不再是炸彈 | M | 儀器的「每 tick 成本 vs 窗長」曲線變**水平**(現況斜率 0.0326 µs/元素);`tests/live/test_signal_state.py` vol_burst 案全綠 | 改回 `sum()` |
| 9 | **(停等拍板)slot 去重:per-code 市場狀態 + per (code, window_secs) 窗 + per-rule 門檻** | 動到 `signal_rules.py` 明文設計決定;現況只值 25% CPU,做它是為了 30 規則 × 150 檔的餘裕 | L/XL | 窗總筆數從 7× 降到 2×(儀器直接印);`on_tick` p50 降到單顆水準;`tests/fixtures/sweep_cluster_golden.json` **集合相等**仍綠;兩條同 kind 不同窗長的規則各有自己的窗(新測試) | 分支保留;改動面積大,務必獨立 PR |
| 10 | **(選配)Discord 配額分級**:政策列優先於 surge_pullback | 影子期的實際暴露(§4.2);但 user 可能寧可調 `discord_per_min` | S | 開盤一分鐘 34 則的情境下,政策列零被擋(儀器 + jsonl 對照) | 改回 FIFO |

---

## 12. 不要動的清單(理由)

1. **雙佇列 + `_put_drop_oldest` + `_discord_worker` 單槽合批**(`:405-408 / 1167-1184 / 1198-1234 / 1673-1688`)
   —— 實證全日零丟包、`task_done()` 記帳正確。見 F-14。
2. **`_RuleSlot` frozen + `_slots` 整顆 dict 原子替換**(`:340-350 / 496-500`)——
   「落檔成功後才單一賦值」的順序是 `upsert_rule` 最難寫對的地方,現況對。
3. **CDP 基準的日別尺 `_stale`**(`:441-446`)—— 成功 / 失敗 / 早退三條路徑共用同一把尺,
   註解自承「分開寫的那次,例外路徑就漏了它」。
4. **`on_rollover` 的「先 reset_day 再 promote」順序 + 差集補抓**(`:657-712`)。
5. **`_emit_policies` / `signal_policy.py` / `format_policy_group_text`** —— 50 次/日。見 F-15。
6. **jsonl 的 `json.dumps` 寫入路徑** —— 兩條明文契約(grep 判準的空白、回填的 byte 比對)。見 F-16。
7. **`read_signals` 的 `errors="replace"` + 壞行跳過**(`:1438-1484`)——
   docstring 已記清楚為什麼不能擴成 `except (OSError, ValueError)`。
8. **`_group_suffix` 的 never-raise**(`:774-812`)—— 摘要是通知的裝飾,壞掉不得讓訊號消失。
9. **`_refresh_groups` 失敗時保舊值不清空**(`:733-772`)—— 清空 = 政策層整天零列。

---

## 13. Open questions(要 user 或別的區塊回答)

1. **`on_book` 的真實母體是多少?** 現況零儀器,本報告以「= tick 數」估。
   若 REALTIME 的純簿更新是成交的 3–5 倍,F-07 的優先序要往上抬兩格。
2. **F-01 的修法選 (a) 決定性 id 還是 (b) 載入即回寫 v4?**
   (b) 會放棄 `load_rules` docstring 明寫的「回退窗」。
3. **影子期(09-08 起四週)的對帳腳本有沒有以 `rule_id` 分群?**
   有的話 F-01 要在影子期結束前修完,否則那四週的資料已經被切碎。
4. **`discord_per_min = 30` 是外部限制還是拍板值?** 若是拍板值,step 10 可能只是調參。
5. **步驟 9(slot 去重)要不要做?** 現況它只值 25% CPU / 0.05% loop。
   做它的唯一理由是「`MAX_RULES 30` × `WATCHLIST_LIMIT 150` 要有意義」。
   若量化路線上規則數不會超過十條,建議**不做**,把預算花在儀器與關機正確性上。
