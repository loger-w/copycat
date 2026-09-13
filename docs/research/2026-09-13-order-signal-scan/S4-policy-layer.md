# S4-policy-layer — 訊號政策層(P / B-a / B-b / S)與族群判定

掃描日期:2026-09-13 · 範圍:`copycat/server/signal_policy.py`(201 行,整檔讀完)、
`copycat/server/signal_hub.py` 政策段(`_emit_policies` / `_refresh_groups` / `_emit` /
`backfill_policy_outcomes` / `format_policy_group_text` / `_send_discord`)、
`copycat/server/screen_engine.py::SCREEN_GROUP`、`copycat/stock_watchlist.py`(整檔)、
`copycat/server/stock_engine.py::policy_quotes / _quote_payload`、`copycat/signals_config.py`(整檔)、
`copycat/live/signal_state.py::_eval_sweep / tick_secs`、`frontend/src/lib/signal-model.ts`、
`tests/server/test_signal_policy.py`。

**未改動 repo 任何檔案、未啟動 server、未下任何單。** 量測腳本與原始輸出留在
`<scratchpad>/order-signal-scan/`(`bench_policy.py` / `bench_policy.txt` / `shadow_stats.txt` /
`peers.txt` / `coverage.txt` / `policy_rows.txt` / `wl.txt`)。

---

## 0. 一句話結論

政策層的**程式碼本身是本次掃描裡品質最高的一段**:純函式、零 IO、四條政策與 CONTEXT.md
逐字對得上、測試 30+ 條含邊界與 review 追蹤案、效能在現況與最壞上限下都完全不是問題
(一顆事件 ≈ 45 µs、一天 41 顆 = 1.8 ms/日)。**這一段不需要效能改造。**

真正的風險全部在**它的輸入與它的產出**:

1. **輸入面有兩顆「靠字面相等」的組名開關**(`SCREEN_GROUP` / `policy_exclude_groups`),
   其中「盤前篩選群組不存在」這一種失效**連一行 WARNING 都沒有**,而 S 政策佔全部政策列的
   **74%**(111/151)。
2. **產出面的對帳能力不足以支撐「四週後決定下實單」這個目的**:
   - 實測影子期前 5 個交易日 **B-a 命中 0 次**、B-b 3 次(同檔一筆)。外推四週 B-a 仍可能是 0,
     **這條政策四週後不會有結論**。
   - 36%(73/205)的掃單簇事件**沒有任何族群快照落檔**,門檻敏感度分析(把 3% 改 4% 會怎樣)
     結構上做不了。
   - 門檻值(`policy_peer_up_pct` / `policy_max_chg_pct` / `policy_push_end`)**不在列上**,
     中途調參之後分不出哪一列用哪組門檻。
   - T+1/T+2/d_close 回填**依賴 server 在當日 13:40 開著**,且視窗以「日檔數」計(5 個)。
     實測現況:09-10 的 38 列 `t2_open` 仍 null、09-11 的 49 列四個欄全 null。
3. **線上 P 的發生率是研究基準的 2.7 倍**(研究 42 筆 / 21 日 = 2.0/日;線上 27 筆 / 5 日 = 5.4/日),
   而「放到尾盤」的初步數字是 **中位 0 / 平均 −2,822 元/張**(研究基準 +4,923)。母體不同
   (研究面板 90 檔中僅 27 檔有自選群組;線上自選 80 檔中 75 檔有族群或盤前篩選),
   **研究的每筆期望值不可直接移植**。這是影子期第一週就該被問的問題,不是四週後。

**影子模式的隔離是乾淨的**:`signal_hub.py` / `signal_policy.py` / `signal_state.py` /
`signal_rules.py` 四檔對 `capital` 的引用數 = **0**;前端 `SignalRail.tsx` / `useSignalAlerts.ts`
對 `/api/capital` 的引用數 = **0**。沒有任何路徑會意外碰到群益(§4)。

---

## 1. 現況地圖:政策層實際怎麼運作

### 1.1 觸發鏈(唯一入口)

```
TC4 tick → stock_engine._handle_quote(loop 單執行緒)
  └ state.ingest(tick) 為真
     └ hub.on_tick(code, tick, state)
        └ for slot in _slots:  slot.detector.evaluate(...)
             └ _eval_sweep → SignalEvent(kind="sweep_cluster", detail={n30,levels,qty,up_pct})
        └ _fanout → per-event try/except → _emit(event, rule, state)
             ├ payload = 既有 signal 形 + detail
             ├ self._publish(payload)            ← WS 同步先送(raw 掃單簇列)
             ├ self._enqueue(payload, notify=rule["notify_discord"])
             └ if event.kind == "sweep_cluster" and event.detail is not None:
                  _emit_policies(event, rule, state, payload, trade_date)   ← 政策層唯一掛點
```

`signal_hub.py:1037-1040`。政策層**只掛掃單簇事件**,不跑在 per-tick 路徑上 ——
測試 `test_peers_fn_not_called_for_other_kinds` 把「其他 kind 不叫 `peers_fn`」釘住。

### 1.2 `_emit_policies` 的七個步驟(`signal_hub.py:1042-1165`)

| # | 動作 | 早退條件 | 位置 |
|---|---|---|---|
| 1 | 取 `meta.ref_milli` / `event.price_milli` | `ref is None or ref <= 0 or price <= 0` → **整顆事件零政策列**(raw 列已記) | 1058-1062 |
| 2 | `resolve_groups(code, self._groups, screen_group=, exclude=)` | — | 1065-1070 |
| 3 | `if not names and not screen_member: return` | **零族群且非盤前篩選成員 → 零政策列** | 1071-1072 |
| 4 | 多組聯集 WARNING(每檔每日一次) | `len(names) > 1` | 1073-1075 |
| 5 | `quotes = self._peers_fn(peer_codes)`(= `engine.policy_quotes`) | `peer_codes` 空或 `_peers_fn is None` → `quotes = {}`;例外 → 計數 + 當日首次印 traceback,降級成「同伴全無報價」 | 1076-1088 |
| 6 | `chg = round((price-ref)/ref*100, 2)` → `evaluate_policies(...)` | `if not ctx.hits: return` | 1089-1102 |
| 7 | 每命中一條政策 → 組 34 鍵 row → `_publish` + `_enqueue` → 記 `_policy_touch[(code,policy)]` | — | 1119-1165 |

**關鍵順序**:`self._policy_touch[key] = count` 在 `publish` / `enqueue` **之後**才寫
(1163-1165,spec review F-04)—— publish 拋例外時這一檔這條政策當日還能再發首筆。
代價是同一顆事件命中多條時中途拋例外會留下部分記帳,但 `_fanout` 的傘會 log。

### 1.3 族群資料從哪來

```
data/stock_watchlist.json
  └ app.py:843  groups_fn = lambda: load_watchlist(wl_path)["groups"]     ← 每次呼叫**讀檔**
       └ hub._refresh_groups()        signal_hub.py:715-745
            ├ self._groups = groups_fn()        例外 → **保舊值**(不清空)
            └ 比 policy_exclude_groups 對不對得上組名 → 缺名集合**變了**才 WARNING 一次
       呼叫點只有一個:hub.on_watchlist(codes)   signal_hub.py:700
            ├ 開機種子:app.py:873  hub.on_watchlist(load_watchlist(wl_path)["codes"])
            └ 自選變更:stock_engine.set_watchlist 尾端 → _signal_hub.on_watchlist(list(codes))
```

**後果**:`_groups` 只在「開機」與「自選/群組真的改了」時更新。群組編輯(移動成員、改組名)
會讓 `WatchlistService._commit` 的 canonical 形改變 → `changed=True` → `set_watchlist` →
`on_watchlist` → `_refresh_groups`,所以**改群組是會生效的**。唯一不生效的路徑是
`_superseded(seq)` 提早 return(兩筆寫入競速時較舊那一筆),那一筆本來就該被丟。

### 1.4 同伴報價從哪來

`stock_engine.policy_quotes(codes)`(`stock_engine.py:763-801`),**同步讀 engine 記憶體**、零 IO:

```python
out[code] = PeerQuote(
    name=name_meta.name if name_meta is not None else "",
    price=price, ref=meta.ref_milli if meta is not None else None, upper=upper,
    chg_pct=self._quote_payload(code)["chg_pct"],      # ← 建整份 11 鍵 dict 只取一欄
    high=high,
    touched_upper=touched_upper_flag(high, upper),      # 與 hub 對自己那一檔同一份定義
    locked_up=locked_up_flag(price, upper, asks),
)
```

**每一檔要求的 code 都在回傳字典裡**(no_data / 缺 meta / 未成交 → 值欄位 None 但鍵仍在),
這是刻意的:整檔缺席會讓「族群有幾檔」跟著行情波動。

### 1.5 產出的三條路

| 路 | 內容 | 受 `notify` 閘影響 |
|---|---|---|
| WS `_publish(row)` | 政策列原形,前端 `SignalRail` 三行 + chip | ❌(真相源) |
| jsonl `data/signals/YYYYMMDD.jsonl` | 政策列 + `trade_date`(35 鍵) | ❌(真相源) |
| Discord | `format_policy_group_text` 四行卡,**不掛同群摘要**(`signal_hub.py:1506-1518`) | ✅ |

`notify = first_of_day and not late`(1123)。批次規則:`_discord_worker` 以**相鄰且同 (code, time)**
合批,同一顆事件的多條政策落在同一批 → 一張卡並列標記(`【P・S】`)。

### 1.6 回填 worker(`backfill_policy_outcomes`,`signal_hub.py:1280-1384`)

每日 `policy_outcome_time`(13:40)一趟;**起動時只在已過當日時點才立即跑**(開盤前起動不跑,
整體 review F-10:回填的 DK 與 CDP 基準暖機共用同一把 TC4 `api.lock`)。

```
cutoff = min(trade_date_fn(), self.today)
dated  = 所有 data/signals/*.jsonl 中 date < cutoff 者,reverse sort
picked = sorted(dated[:policy_outcome_days])        ← 只掃「最新的 5 個已封閉日檔」
每個日檔:read_bytes(to_thread) → 逐行 decode + json.loads(**在 loop 上**)
         → 每檔一次 bars_range(tf="D", start=最早日檔日, end=today)
         → 補 t1_open/t1_date/t2_open/t2_date/d_close/d_high(只補 null 的)
         → 只重寫被補的列、行尾原樣、整檔 atomic_write_bytes;零補不碰檔
```

---

## 2. 端到端延遲預算

### 2.1 實測(`bench_policy.py`,repo `.venv` / Python 3.13.13 / Windows 11;純函式離線跑)

```
== resolve_groups(真實 data/stock_watchlist.json:80 檔 / 12 組)==
  10 同伴檔 6706(矽光)        1.623 us
  只在盤前篩選 1727            0.951 us
  零組 6715(ALL IN)           0.923 us
  150 檔單一族群(WATCHLIST_LIMIT 最壞) 80.125 us
  5 組 × 30 檔聯集              77.788 us
== evaluate_policies ==
  同伴   0 檔                   1.134 us
  同伴   3 檔                   2.712 us
  同伴  10 檔(現況最大)        5.517 us
  同伴  32 檔                  14.494 us
  同伴 149 檔(最壞)           63.174 us
== 旗標純函式 ==
  touched_upper_flag           0.0681 us
  locked_up_flag(5 檔簿)      0.1920 us
  tod_bucket                   0.1573 us
== 政策列 ==
  組一列(10 同伴)             1.796 us
  json.dumps 一列              9.811 us
  一列大小                      1737 bytes
== engine 側(形狀複製量測)==
  _quote_payload 形狀           0.316 us
  policy_quotes 單檔            0.815 us  → 10 檔 8.58 us / 149 檔 126.8 us
== 其他 ==
  load_watchlist(80 檔/12 組)  81.4 us(檔案 2798 bytes)
```

### 2.2 可加總的區段(一顆掃單簇事件,現況形:10 同伴 / 命中 2 條)

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 1 | `_eval_sweep` 產出事件(已在 B06 量過) | `signal_state.py:700-782` | 5.20 µs/tick × 7 顆 detector | measured(B06) | 不在本區塊 |
| 2 | `_emit` 組 raw payload + publish + enqueue | `signal_hub.py:1012-1036` | ~12 µs(json.dumps 在 WS 側 per-client) | estimated | |
| 3 | `resolve_groups` | `signal_policy.py:99-123` | **1.62 µs** | measured | 現況 12 組 / 80 檔 |
| 4 | `peers_fn = policy_quotes(10 同伴)` | `stock_engine.py:763-801` | **8.58 µs** | measured(形狀複製) | 在 **loop 上**同步 |
| 5 | `evaluate_policies`(10 同伴) | `signal_policy.py:126-188` | **5.52 µs** | measured | |
| 6 | 組政策列 × 2 | `signal_hub.py:1124-1160` | **3.59 µs** | measured | 34 鍵 + 深拷貝 peers |
| 7 | `_publish` × 2 → WS per-client `send_json` | `ws.py` | **9.81 µs × 2 × N client** | measured | 8 條 WS → 157 µs |
| 8 | `_enqueue` × 2(兩條有界 Queue put_nowait) | `signal_hub.py:1167-1184` | < 1 µs | estimated | |
| 9 | **一顆事件 loop 佔用合計(1 client)** | | **≈ 45 µs** | measured 疊加 | 8 client → ≈ 200 µs |
| 10 | jsonl 落檔 × 2(off-loop) | `signal_hub.py:1412-1419` | 200–400 µs/則 | estimated(B06 F-08) | 走**共用預設 executor** |
| 11 | `_refresh_groups` 讀檔(自選變更時) | `app.py:843` | **81.4 µs** | measured | 在 **loop 上**同步讀檔 |
| 12 | Discord 四行卡組字 + `_allow_discord` | `signal_hub.py:200-263` | < 20 µs | estimated | 在 worker task,非熱路徑 |
| 13 | 回填:逐行 decode + `json.loads` | `signal_hub.py:1330-1338` | **20–35 ms 的 loop 阻塞**(5 檔 × 686 行) | estimated(B06 F-10) | 每日 13:40 一次 |
| 14 | 回填:整趟 | log 實證 | **4.3 s**(61 列 / 5 日檔) | measured(B06 讀 log) | 主成本是 `basis_gap_secs 0.2` |

### 2.3 頻率與總量(這才是結論)

| 量 | 值 | 依據 |
|---|---|---|
| 掃單簇事件 | **41 顆/日**(205 顆 / 5 個交易日) | measured(`data/signals/2026090[789],091[01].jsonl`) |
| 政策列 | **30 列/日**(151 / 5) | measured |
| 政策層每日 loop 佔用 | 41 × 45 µs = **1.8 ms/日** | measured 疊加 |
| 理論最壞頻率(80 檔 × `sweep_cooldown_secs` 60 s × 4.5 h) | 21,600 顆/日 | 推估上界 |
| 最壞頻率 × 現況成本 | 21,600 × 45 µs = **0.97 s/日** | 推估 |
| 150 檔上限 + 單一 149 同伴族群的最壞單顆 | 80 + 127 + 63 + 2×12 = **294 µs** | measured 疊加 |
| 同一 loop turn 內 50 檔同時命中(極端叢發) | 50 × 294 µs = **14.7 ms 單次 stall** | 推估 |

**判讀:政策層在現況與可預見的最壞情況下都不是效能問題,零最佳化必要。**
(與 B06 §6.6「`signal_policy.py` 全部不要動」一致,本輪以實測支撐它。)
唯一值得記在帳上的形狀是 `resolve_groups` 的同伴去重是 **O(同伴數²)**(`member not in peers`
線性掃 list,`signal_policy.py:121-122`):現況 10 同伴 = 1.6 µs,150 檔上限 = 80 µs,
**成長 50 倍但絕對值仍可忽略**。只有在政策層被拉到 tick 級時才需要動它。

---

## 3. 四條政策與 CONTEXT.md 的逐字比對

### 3.1 逐條對照

| 政策 | CONTEXT.md 定義 | 實作(`signal_policy.py:169-178`) | 判定 |
|---|---|---|---|
| **P** | 同伴沒人 ≥3% + 自己 <6% + 同伴沒人鎖過 | `if quoted and not peer_touched:` → `peers_up == 0 and under_cap` | ✅ 逐字相符 |
| **B-a** | 自己最強 + 同伴 ≥3% 至少一檔 + <6% + 同伴沒人鎖過 | `leader and peers_up >= 1 and under_cap` | ✅ |
| **B-b** | B-a 去掉 <6% | `leader and peers_up >= 1` | ✅(**B-a ⊆ B-b 恆成立**) |
| **S** | 盤前篩選名單成員 + <6%(無族群濾網) | `if screen_member and under_cap:` —— **在 `quoted`/`peer_touched` 大分支之外** | ✅ 確實無族群濾網 |

`under_cap = chg < max_chg_pct`(嚴格小於,`test_chg_exactly_at_max_does_not_hit` 釘住)。
`quoted` 非空 = CONTEXT「P / B 政策至少要一檔同伴有報價」。✅

### 3.2 術語實作的正確性

- **族群**(`resolve_groups`):扣「盤前篩選」(`name == screen_group` → `screen_member = True; continue`)
  與 `exclude`;多組取**聯集保序去重**。✅ 與 CONTEXT 及研究 8.1 R1 相符。
  ⚠️ 研究 R1 另寫「族群組與盤前篩選重疊 → 以族群組為主」——實作正是如此(盤前篩選那一組
  只設 `screen_member`,不進 `names` / `peers`),✅。
- **同伴**:`member != code and member not in peers`。✅
- **族群最強**(`leader`):`chg >= float(peer_max["chg_pct"])`,且 `chg` 在 hub 端
  `round(..., 2)`(`signal_hub.py:1091`)與同伴的 `_quote_payload` round 2 **同一把尺**
  (review F-01;`test_self_chg_rounded_to_two_places_same_ruler_as_peers` 釘住)。✅
  平手算最強(`test_leader_tie_counts_as_leader`)。✅
- **鎖過**(`touched_upper_flag = high >= upper`):只看同伴(`peer_touched`),自己鎖過不擋,
  列上 `self.touched_upper` 有記。✅ 與 CONTEXT 及研究 `_locked_before` 相符。
- **當下鎖死**(`locked_up_flag`):`price == upper and _best_limit_price(asks) is None`,
  engine 側(同伴)與 hub 側(自己)**共用同一份定義**(review F-03)。✅ 不進政策判定,只落列。

### 3.3 兩處刻意的 fail-open(正確但值得記帳)

```python
# signal_policy.py:146
peer_chg = float(raw_chg) if isinstance(raw_chg, (int, float)) else None
...
# 160-162
if touched is True:              # ← None(不知道)不算鎖過
    peer_touched = True
peers_up = sum(1 for _c, _n, c in quoted if c >= peer_up_pct)   # ← 無報價同伴不計
```

`touched_upper` 為 `None` 的語意是「不知道」(缺 `high` 或缺 `upper`:no_data / 尚未成交 /
缺 meta),但消費端收成「沒鎖過」;同理無報價同伴不進 `peers_up` 分母也不進分子,
所以「同伴沒人 ≥3%」(P)與「鎖過閘」**都偏向成立**。

**實測量級(影子期 5 日,69 列有同伴的政策列)**:含「無報價同伴」的列 3 列(同伴實體 3)、
含「鎖過未知同伴」的列 3 列。**2%,現況不痛**;而且 `peers[]` 快照有落檔,對帳可事後過濾。
但**當下沒有任何計數或 log**,規模變大時看不見。

---

## 4. 影子模式完整性:確認沒有任何路徑碰到群益

**後端**:

```
grep -n "capital|Capital|place_order|send_order|SendStockOrder" \
  copycat/server/signal_hub.py copycat/server/signal_policy.py \
  copycat/live/signal_state.py copycat/signal_rules.py
→ 零命中
```

`signal_hub.py` 的 import 清單(38-90 行)共 13 個 `copycat.*` 模組,**無一個是 `copycat.capital`**。
`signal_hub` 的對外副作用恰好三個,全部在 `_emit` / `_emit_policies` 內:
`self._publish`(= `stock_ws.publish`)、`self._enqueue`(兩條 `asyncio.Queue`)、
以及 worker 端的檔案 append 與 Discord 送訊。

**前端**:`SignalRail.tsx` / `useSignalAlerts.ts` 對 `placeOrder` / `/api/capital` / `close-order`
的引用數 = **0**。政策列在畫面上的唯一效果是 rail 三行 + chip + toast + 雙嗶。

**結論:影子模式在結構上是安全的,不是靠紀律維持的。** 這是這一段設計最值得肯定的地方。

唯一要提醒的是**未來開實單時的接線形狀**:目前 `_emit_policies` 是 `_emit` 的同步內聯呼叫,
跑在 event loop 上、在 `_fanout` 的 per-event try/except 傘底下。若未來把「政策命中 → 下單」
接在這裡,等於把**券商往返(B10 實測 mean 70 ms / p99 2 s)接進 tick 熱路徑**,而且例外會被
那把傘**靜默吞掉**(只留一行 `訊號 fanout 失敗(丟棄該則)`)。實單接線必須走佇列 + 獨立 task,
不得沿用這個掛點。

---

## 5. 推播窗與 `late`

```python
# signal_hub.py:1107-1110
secs      = tick_secs(event.time_key)          # event.time_key = tick.time(TC4 交易所時刻)
end_secs  = tick_secs(cfg.policy_push_end)     # "12:30:00" → 45000.0
late      = secs is not None and end_secs is not None and secs > end_secs
tod       = tod_bucket(secs) if secs is not None else "1200"
# 1123
notify    = first and not late
```

- **右界 12:30:00 是 end-inclusive**(`> end_secs`):恰好 12:30:00.000 不算 late。
- **左界 09:00 不在這裡**:由 `SignalDetector._in_session`(`signal_state.py:63-64`,
  09:00–13:30 end-exclusive)提供,而那是**伺服器牆鐘**,`late` 用的是**交易所 tick 時刻**——
  兩把不同的鐘。現況兩者差幾百毫秒,無實務影響,但值得記:
  `_in_session` 用 `self._now_fn()`,`late` 用 `tick.time`。
- `event.time_key = tick.time or _clock_key(now)`(`signal_state.py:307`)。TC4 送空字串時
  退回伺服器時刻;`tick.time` 非空但解析不了 → `_eval_sweep` **整段跳過**(不發事件),
  所以 `tick_secs(event.time_key)` 在政策層永遠解析得出來 —— `secs is None` 這條分支
  prod 不可達。
- **實測**:影子期 5 日 late=True 共 5 列(3.3%),全部 `notify=False`。`tod` 五桶分佈
  0900:39 / 0910:18 / 0930:20 / 1030:26 / 1200:13(116 列已回填樣本),與研究 `tod_bucket`
  同一把尺。✅

**失效樣態**:`policy_push_end` 在建構時以 `strptime("%H:%M:%S")` 驗過(`signal_hub.py:378-382`,
壞值 → hub None → routes 503),所以 `end_secs is None` 也不可達。這一段的健壯性是夠的。

---

## 6. 政策列的 wire 形狀與 CLAUDE.md §4 契約

### 6.1 實測形狀(`data/signals/20260910.jsonl` 真實列)

```json
{"type":"signal","id":"2026-09-10-r-1788965322-006-6226-policy-S-09:01:15.000",
 "rule_id":"r-1788965322-006","rule_name":"掃單簇","kind":"policy","policy":"S",
 "code":"6226","name":"光鼎","price":30450,"time":"09:01:15","levels":[],"direction":null,
 "pct":3.395585738539908,"touch_count":1,"notify":true,"first_of_day":true,"late":false,
 "tod":"0900","sweep":{"n30":2,"levels":2,"qty":15,"up_pct":3.395585738539908},
 "self":{"chg_pct":2.7,"to_limit_pct":7.060755336617405,"touched_upper":false,"locked_up":false},
 "groups":[],"screen_member":true,"peers":[],"peers_up":0,"peer_max":null,
 "leader":false,"peer_touched":false,
 "t1_open":33050,"t1_date":"2026-09-11","t2_open":null,"t2_date":null,
 "d_close":32600,"d_high":32600,"trade_date":"2026-09-10"}
```

- `kind="policy"`、`policy ∈ {P,B-a,B-b,S}`、id 格式 `<日>-<規則id>-<代號>-policy-<標記>-<時刻鍵>`
  —— 與 CLAUDE.md §4 逐字相符 ✅。實測 151 列**零重複 id**。
- `pct` = 60 s 漲幅、`levels=[]`、`direction=null` ✅。
- `d_close` / `d_high` 存在 ✅(整體 review F-31)。
- 後端鍵集由 `tests/server/test_signal_policy.py::test_p_hit_full_row_schema` 的
  `assert set(msg) == _POLICY_KEYS` 釘住 ✅。

### 6.2 ⚠️ id 的一個小坑(記帳,不是缺陷)

id 的第一段是 `trade_date`(含兩個 `-`),第四段是固定字面 `policy`,第五段是政策標記
(**`B-a` / `B-b` 自己含 `-`**)。任何離線讀者若用 `id.split("-")` 拆欄位,
`B-a` 會被切成兩段而 `P` / `S` 不會 —— **同一支解析器對四條政策行為不一致**。
正解是讀 `row["policy"]` 欄(它就在列上),不要拆 id。目前 repo 內無此類拆解,
但研究目錄的離線腳本是無版控的、看不到。

### 6.3 ⚠️ 前端型別缺 `d_close` / `d_high`

`frontend/src/lib/signal-model.ts:67-89` 列了 `sweep` / `self` / `groups` / `peers` /
`peer_max` / `t1_*` / `t2_*` 這些「wire 存證欄、前端不讀」,但 **`d_close` / `d_high` 沒列**。
TypeScript 結構型別對多出來的 JSON 欄位不報錯,所以功能零影響;
但它是「後端加欄、前端型別鏡像沒跟」的**已發生實例**,而 CLAUDE.md §4 的其他契約
(`avg_source` / `PositionKind` / `PARAM_SPECS`)都有跨語言 parity 測試,這一條沒有。

---

## 7. 影子期對帳能力盤點(本區塊最重要的一節)

### 7.1 實測:影子期前 5 個交易日(2026-09-07 ~ 09-11)

```
掃單簇事件 205 顆;政策列 151 列
政策分佈           P 35 / B-a 0 / B-b 5 / S 111
同檔一筆(first_of_day && !late)  P 27 / B-a 0 / B-b 3 / S 62   共 92
每顆事件命中政策數  1 條 113 顆 / 2 條 19 顆;有政策的事件 132 / 205 = 64%
有同伴的政策列 69;leader=True 35;peers_up>=1 僅 15;peer_touched=True 僅 2
B 候選(leader & peers_up>=1 & !peer_touched)= 5,其中 chg<6% = 0
B-b 五列的 self.chg_pct = [7.92, 8.31, 8.19, 6.86, 9.27]
late=True 5;notify=True 92;first_of_day 93
回填完整度  t1 已補 102 / t2 已補 64 / d_close 已補 102(共 151)
  per-day  09-07 (t1✔ t2✔) 29 | 09-08 ✔✔ 12 | 09-09 ✔✔ 23 | 09-10 (t1✔ t2✘) 38 | 09-11 (✘✘) 49
```

### 7.2 三個結構性缺口

#### G-1 B-a 的樣本數結構上不可能達到可判讀的量

`B-a ⊆ B-b`(兩者差別只有 `under_cap`),而 5 天內的 5 個 B 候選 **chg 全部 ≥ 6.86%**
→ B-a 命中 0 次。外推 4 週(20 交易日)≈ **B-a 0–4 筆、B-b 12 筆**(同檔一筆)。

研究 8.1 Q3 的拍板是「分開標、影子驗」,但**這個量級四週後驗不出任何東西**。
現在就該決定:(a) 接受 B 系四週後無結論、只留 P vs S 的對照;或 (b) 把影子期對 B 的
判準改成「事件級記錄 + 事後重算」而不是「命中計數」(那需要 G-2 的修法)。

#### G-2 **36% 的掃單簇事件沒有任何族群快照落檔** → 門檻敏感度分析做不了

`_emit_policies` 在 `if not ctx.hits: return`(1101-1102)之後**什麼都不寫**。
raw `sweep_cluster` 列有落檔,但它**沒有 `groups` / `peers` / `peers_up` / `leader` /
`peer_touched` / `self.chg_pct`** 這些欄。

實測:205 顆事件中 **73 顆(36%)完全沒有政策列**。其中一部分是結構盲區(見 G-4),
另一部分是「有族群但四條全不過」—— 而後者正是「把 `peer_up_pct` 從 3% 改成 4% 會多出幾筆」
這種問題的母體。**現在這個母體的族群狀態一去不回。**

研究 8.3 的實作要求寫的是「**jsonl 每則必記族群成員快照**……事後才能重算」——
嚴格讀,「每則」指的應該是每則**事件**,現行實作是每則**命中**。

**修法(W1 契約允許)**:CLAUDE.md §4 的離線讀者契約是「不新增列型、每列 `kind` 恆在、
**既有列只加欄不改欄**」。所以把 `PolicyContext` 攤到 raw `sweep_cluster` 列上當新欄
(例如 `policy_ctx: {groups, screen_member, peers, peers_up, peer_max, leader, peer_touched,
chg_pct, to_limit_pct, hits}`)是**合契約的**:不新增列型、只加欄。
代價 = 每顆事件多付一次 `peers_fn`(現況是命中才付)與約 1.4 KB/列 ×205/日 = 290 KB/日。

#### G-3 門檻不在列上 → 中途調參之後分不出哪一列用哪組門檻

`policy_peer_up_pct` / `policy_max_chg_pct` / `policy_push_end` / `policy_exclude_groups`
**都不在政策列上**。`format_policy_group_text(rows, peer_up_pct=)` 的簽名就是這個設計的
明證(`signal_hub.py:210`「列上不帶門檻,由 hub 以 cfg 注入」)。

現況 prod **沒有 `configs/signals.json`**(實查),所以全走 `SignalsConfig` 預設
(`peer_up_pct=3.0` / `max_chg_pct=6.0` / `push_end="12:30:00"` / `exclude=("ALL IN",)`)。
四週影子期內只要有人建了這個檔或改了它,**對帳就再也分不出前後**,而且零訊號。

**修法**:每列加一個 `thresholds: {peer_up_pct, max_chg_pct, push_end}`(只加欄,合 W1),
或至少在 hub 啟動時把四個值印成一行固定字串供 `grep`。後者零契約成本。

#### G-4 政策層的結構盲區 = ALL IN 純成員

`resolve_groups` 把 `exclude` 的組**整組跳過**(`signal_policy.py:117-118`),所以一檔只屬於
「ALL IN」而不屬於任何其他組、也不在盤前篩選名單時,`names=[]` 且 `screen_member=False`
→ `_emit_policies` 在 1071 行 return → **四條政策全不評**。

實測現況自選 80 檔中有 **5 檔**落在這個盲區:`6715 / 3141 / 1595 / 7795 / 2243`
—— **恰好就是 ALL IN 的成員**(ALL IN 6 檔中只有 8103 因為同時在盤前篩選而被涵蓋)。

這與研究 8.1 R1「剩零組 → 不發」一致,**是拍板不是 bug**。但要講清楚它的後果:
**user 放進 ALL IN 的(= 最看好的)那幾檔,政策層對它們永遠沉默**,而畫面上看不出來
(rail 只是沒有那幾檔的政策列)。研究 §8.2 也記了同一件事:「面板 90 檔只 27 檔有自選群組,
其餘 63 檔政策 P 永遠不發」。

#### G-5 回填依賴 server 在 13:40 開著,且視窗以「日檔數」計

`picked = sorted(dated[:policy_outcome_days])`(1307)取的是**最新 5 個已封閉日檔**,
不是「最近 5 個日曆日」。連續停機超過 5 個有訊號的交易日,舊日檔就**永久滑出視窗**,
`t1_open` / `t2_open` / `d_close` / `d_high` 永遠是 null,而**最後那行 log
「共回填 n 列(掃 5 個日檔,start..end)」看起來完全正常**。

實測現況已經在這條路上:09-10 的 38 列 `t2_open` 仍 null(09-12 是交易日但 server 沒開),
09-11 的 49 列四欄全 null。下一次 server 起來(且過 13:40)會補上——**只要不超過 5 個日檔**。

**缺的是一個計數**:「掃到但仍有 n 列 t1/t2 是 null」以及「有 m 個日檔因為滑出視窗沒掃到」。
現況 log 只印補了幾列,補不到的靜音。

### 7.3 可以做到的事(不要低估現況)

| 對帳問題 | 資料夠不夠 | 依據 |
|---|---|---|
| 「放到尾盤」每筆損益 | **✅ 夠**(`d_close - price`,毫元差 = 元/張) | CLAUDE.md §4 已承認日 K 收盤是 13:20 的可接受代理 |
| T+1 開盤出場(Q4 拍板的實際出場) | **✅ 夠**(`t1_open - price`) | |
| 「鎖死」比率 | **✅ 可推導**:`upper = price × (1 + to_limit_pct/100)`,實測 151 列**全部**還原成整數毫元、零誤差;`d_close == upper` = 鎖漲停收盤代理(實測 12/102 = 11.8%),`d_high >= upper` = 當日鎖過 | 本輪實測 |
| 12:30 前濾網 | **✅ 夠**(`late == false`,與研究 09-07 勘誤後的口徑同源) | 研究 §8.2 勘誤 |
| 同檔一筆 | **✅ 夠**(`first_of_day`,但鍵是 (code, policy) —— 要「同檔一筆」得再按 (date, code) 去重) | |
| 族群增刪後重算 | **✅ 命中列夠**(`peers[]` 含每個同伴的 chg / touched / locked);**❌ 未命中事件不夠**(G-2) | |
| 時段切片 | **✅ 夠**(`tod` 五桶) | |
| 門檻敏感度 | **❌ 不夠**(G-2 + G-3) | |
| 對帳三桶(訊號有他有打 / 訊號有他沒打 / 他打了沒訊號) | **⚠️ 資料在但沒有 join 工具**:訊號 `data/signals/*.jsonl` + 成交 `data/audit/capital-*.jsonl`,兩邊沒有共同鍵,要按 (日期, 股號, 時刻) 手動對 | 研究 8.3 R2「每週對帳」明列此需求 |
| 進場滑價 | **❌ 不夠**:列上只有 `price`(當筆成交價)與 `sweep.qty`(簇的總張數),沒有當下委賣深度(TC4 硬限制:五檔不可回測) | CONTEXT「五檔」節 |
| 「我們那段沒在聽」 | **❌ 不夠**:盤中重啟 = detector 狀態全失、回補 tick 刻意不重放,jsonl 沒有斷點記號 | B06 已記 |

### 7.4 ⚠️ 第一週的初步數字:線上 P 與研究基準對不上

以 `first_of_day && !late` 的同檔一筆、每筆 1 張、未計手續費與證交稅,拿 `d_close - price`
(放到尾盤)與 `t1_open - price`(T+1 開盤出)算:

| 政策 | n(5 日) | 放到尾盤 中位 / 平均(元/張) | T+1 開盤 中位 / 平均 | 研究 §8.2 對應基準 |
|---|---|---|---|---|
| P | 23 | **0 / −2,822** | −1,100 / −9,661 | 排除 ALL IN 版 n=35(21 日) **+5,784/筆** |
| S | 46 | −75 / −941 | 0 / **+530** | S 全時段 n=99(21 日) **+1,433/筆** |
| B-b | 2 | −23,500 / −23,500 | −16,000 / −16,000 | — |

**這是 1/4 的樣本、未扣稅費、平均被少數高價股主導(研究 §109 自己記過同一個坑),
不是結論。** 但有兩件事現在就該被問:

1. **發生率差 2.7 倍**:研究 P(排除 ALL IN)42 筆 / 21 日 = 2.0/日;線上 P 27 筆 / 5 日 = 5.4/日。
   母體不同 —— 研究面板 90 檔中只有 27 檔有自選群組,線上自選 80 檔中有 75 檔有族群或在盤前篩選。
   **研究的每筆 +5,784 是在一個窄得多的母體上算出來的,不可直接移植到線上的寬母體。**
2. **B-b 的兩筆都重傷**(−23,500 / 張),與研究對「≥6% 不進」的疑慮同方向。

---

## 8. Findings

### F-01 「盤前篩選」群組不存在 → S 政策整天零列,零 log 零畫面訊號(**critical**)

**位置**:`copycat/server/signal_policy.py:113-116`、`copycat/server/signal_hub.py:736-745`

```python
# signal_policy.py:113
if name == screen_group:
    screen_member = True
    continue
```

`screen_member` 唯一的來源是「自選裡存在一個名字**逐字等於** `SCREEN_GROUP`("盤前篩選")
的群組,且 code 在它的 `codes` 裡」。

`_refresh_groups`(736-745)**只檢查 `policy_exclude_groups` 對不對得上組名,不檢查
`SCREEN_GROUP` 在不在**。所以:
- 盤前篩選 nightly task 失敗 / server 08:00 沒開 / user 手動刪了那一組
  → `screen_member` 對所有檔恆 False → **S 政策整天零列**;
- **實測 S 佔全部政策列 74%(111/151)、同檔一筆佔 67%(62/92)** —— 三分之二的政策列消失;
- rail 上只是「今天比較安靜」,log 裡沒有任何一行提到這件事。

**修法**:`_refresh_groups` 已經在算 `names = {g["name"] for g in self._groups}`,
多一行 `if self._screen_group not in names: logger.warning(...)`(同樣「集合變了才印」的節流)。
零契約、零行為改變、三行。

---

### F-02 排除組名逐字比對:改名 → ALL IN 靜默變族群(**high**,CLAUDE.md §4 已記)

**位置**:`copycat/server/signal_policy.py:117-118`、`signal_hub.py:736-745`

```python
if name in exclude:      # 逐字比對,不 strip、不 casefold
    continue
```

user 把自選的「ALL IN」改名成別的字而 `configs/signals.json` 沒跟
→ 該組**靜默變成族群**(研究 §8.2:ALL IN 當族群 = **−1,471/筆**、事件級 16 筆 −3,605)。

現況的防護是 `_refresh_groups` 的 WARNING(「排除組名 … 對不上任何自選群組」),
**已經正確實作**(整體 review F-03),且以「缺名集合變了才印」節流。

**但防護只有一行 log**:不進 `/api/health`、不進畫面、不進 jsonl。user 看不到。
另外它**只在 `_refresh_groups` 執行時比**(= 自選變更或開機),而改組名本身就是自選變更 → 會比到 ✅。

**實測現況安全**:prod 無 `configs/signals.json` → `exclude=("ALL IN",)` 預設;
自選確實有一組叫 `ALL IN`(6 檔)→ `missing = ()` → 不印 WARNING。✅

**修法建議**:把 `exclude_missing` 與 `screen_group_present` 兩個布林掛進
`/api/health` 的一個 `signals` 區塊(B06 F-16 已經要求加 hub 計量,這兩個順路)。

---

### F-03 `SCREEN_GROUP` 字面漂掉 = 雙重失效(S 母體歸零 **且** 32 檔變族群)(**high**)

**位置**:`copycat/server/screen_engine.py:52`(`SCREEN_GROUP = "盤前篩選"`)→
`signal_hub.py:336`(`screen_group: str = SCREEN_GROUP`)→ `signal_policy.py:113`

CLAUDE.md §4 記的症狀是「盤前篩選那 ~60 檔會被當族群、S 母體變空」。**本輪實測量化**:

```
現況(screen_group="盤前篩選")     全自選最大同伴數 = 10
若 screen_group 漂掉                全自選最大同伴數 = 40    ← 4 倍
```

(現況盤前篩選群組 32 檔;`peers.txt`。)後果是雙重的:S 整天零列 **且** P/B 的族群變成
一個 32 檔的雜燴 —— 兩者都零錯誤訊號。

現有防護:`tests/server/test_screen_engine.py::test_screen_group_name_parity_with_frontend`
釘住前端字面;後端 `SCREEN_GROUP` 是單一產生點,`signal_hub` 直接 import 它,
**內部不可能漂**。真正的風險是 user 手動把自選裡那一組改名(nightly 下次會重建一組新的,
舊的那 32 檔留在改名後的組裡 → 那一組變成 32 檔的族群)。F-01 的那一行 WARNING 也涵蓋不到
(盤前篩選組會被 nightly 重建,`missing` 為空)。

**修法**:與 F-01 同一處,另加「自選有一組成員數 > N(例如 25)且不是盤前篩選」的提示,
或更直接:nightly `replace_group` 之後比對「上一份盤前篩選成員是否整批跑到另一組去了」。
成本 / 收益偏低,**建議只記帳、不做**,除非影子期真的踩到。

---

### F-04 未命中事件不落族群快照 → 門檻敏感度分析結構上做不了(**high**,對帳)

見 §7.2 G-2。**證據**:`signal_hub.py:1101-1102`

```python
if not ctx.hits:
    return
```

**實測**:205 顆掃單簇事件中 73 顆(**36%**)零政策列 → 零族群快照。

研究 8.3 的實作要求是「jsonl 每則必記族群成員快照……因為 user 會增刪群組,事後才能重算」。
現行實作只在**命中**時記。

**修法**:把 `PolicyContext` 攤成一個 `policy_ctx` 欄加到 raw `sweep_cluster` 列上
(W1 允許「既有列只加欄不改欄」)。代價:每顆事件都要付 `peers_fn`
(現況 41 顆/日 → 仍是 41 顆/日,只是命中率 64% → 100%,增量 ≈ 15 顆 × 9 µs = 0.13 ms/日)
與 ≈ 290 KB/日 的檔案成長。

---

### F-05 門檻不在列上,影子期中途調參後對帳分不出前後(**high**,對帳)

見 §7.2 G-3。**證據**:政策列 34 鍵中沒有任何門檻欄;`format_policy_group_text` 的
`peer_up_pct` 是**參數注入**(`signal_hub.py:200, 210, 1508`),明文「列上不帶門檻」。

prod 現況**無 `configs/signals.json`**(實查 `configs/` 只有 correlation / fade / strategy /
trading_holidays)→ 全走預設,所以目前安全;但這是「沒踩到」不是「踩不到」。

**修法(擇一)**:
(a) 每列加 `thresholds: {peer_up_pct, max_chg_pct, push_end}`(只加欄,合 W1);成本 ≈ 60 bytes/列。
(b) hub 啟動時印一行固定字串 `政策門檻:peer_up=3.0 max_chg=6.0 push_end=12:30:00 exclude=['ALL IN']`,
    對帳時 `grep` 比對。零契約成本,但 log 輪替後就查不到。
**建議 (a)+(b) 都做**,(b) 先做(五分鐘)。

---

### F-06 B-a 四週後不會有樣本(**high**,方法論,不是 bug)

見 §7.2 G-1。**證據**:5 個交易日 B 候選 5 顆,`self.chg_pct` = [7.92, 8.31, 8.19, 6.86, 9.27],
**全部 ≥ 6.86%** → B-a 命中 0。外推 20 日:B-a 0–4 筆、B-b 12 筆(同檔一筆)。

這是「B-a 與 B-b 只差一個 `< 6%` 閘,而實際走到 leader + peers_up≥1 的情境幾乎都是
已經漲很多的股票」這個結構造成的,不是實作錯誤。

**這要 user 拍板**:四週後 B 系無結論是可接受的(P vs S 才是主軸),還是要現在就改
判準(例如把 B 的對帳改成「以 F-04 的全事件快照事後重算」)?

---

### F-07 回填視窗以「日檔數」計,滑出即永久 null 且靜音(**medium**)

**位置**:`copycat/server/signal_hub.py:1298-1310, 1384`

```python
dated.sort(reverse=True)
picked = sorted(dated[: self._cfg.policy_outcome_days])     # 5
...
logger.info("T+1/T+2 回填完成:共回填 %d 列(掃 %d 個日檔,%s..%s)", total, len(picked), start, end)
```

最後那行 log **不區分「沒東西可補」與「該補的已經滑出視窗」**。

**實測**:151 列中 49 列(09-11 整天)四欄全 null、38 列(09-10)`t2_open` null。
這些會在下一次 server 過 13:40 時補上 —— **只要中間不超過 5 個有訊號的交易日**。

**修法**:迴圈結束後多算一個「掃到的日檔裡仍有 n 列 t1/t2/d_close 是 null」與
「有 m 個 date < cutoff 的日檔沒被掃到(滑出視窗)」,兩個數字進同一行 log。
三行程式、零契約。判準隨即可 `grep`。

---

### F-08 `peers_up` / `peer_touched` 對「不知道」的同伴 fail-open(**medium**)

見 §3.3。**位置**:`signal_policy.py:146, 160-162`

「同伴沒報價」與「同伴沒動」在 `peers_up` 裡是同一件事;「鎖過未知」與「沒鎖過」在
`peer_touched` 裡是同一件事。兩者都讓 P / B **更容易命中**。

**實測量級**:69 列有同伴的政策列中,3 列含無報價同伴、3 列含鎖過未知同伴(**約 4%**)。
`peers[]` 快照有落檔,對帳可事後過濾。

**修法**:不改判定(改了就是改政策定義,要 user 拍板)。加兩個欄就夠對帳:
`peers_unquoted: int` 與 `peers_touch_unknown: int`(只加欄,合 W1),
或者至少在 hub 加一個每日計數 + 換日一行 WARNING(與現有 `_peers_fn_failures` 同款)。

---

### F-09 `_groups` 空表 = 全政策靜默停擺一整天(**medium**,已有部分防護)

**位置**:`signal_hub.py:726-735`

```python
if self._groups_fn is None:
    return
try:
    self._groups = self._groups_fn()
except Exception:
    logger.exception("群組結構讀取失敗,同群摘要與政策族群沿用上一份(%d 組;0 組 = 本日 P/B/S 全不評)", len(self._groups))
    return
```

「保舊值不清空」的處理是**對的**(docstring 自承代價)。但**開機那一次**若
`load_watchlist` 拋(檔案半寫入 / 磁碟錯),`self._groups` 停在 `[]` →
`resolve_groups` 對所有檔回 `([], [], False)` → `_emit_policies` 在 1071 行全部 return
→ **P / B / S 整天零列**。有一行 exception log,但沒有任何後續重試。

實務上 `load_watchlist` 對壞檔會拋 `json.JSONDecodeError`,而自選檔是 `atomic_write_text` 寫的,
半寫入機率低。**列出來是為了完整**:嚴重度中、機率低、有 log。

**修法(可選)**:`_refresh_groups` 在 `self._groups` 為空且 `self._watch` 非空時印一行
WARNING「群組結構為空,本日政策層不評」——把「配置態」講清楚(同 `request_basis` 的
「CDP 全域停用」那一行的做法)。

---

### F-10 `_emit_policies` 在 `_fanout` 的傘底下,政策列遺失只留一行泛用 log(**medium**)

**位置**:`signal_hub.py:640-644`

```python
for event in events:
    try:
        self._emit(event, slot.rule, state)
    except Exception:
        logger.exception("訊號 fanout 失敗(丟棄該則):%s / %s", code, _rule_tag(slot.rule))
```

`_emit` 先 publish raw 掃單簇列、再呼 `_emit_policies`。政策層任何例外
(`_publish` 拋、`evaluate_policies` 拿到畸形 quotes、`_enqueue` 拋)
→ 那顆事件的**部分或全部政策列消失**,而 raw 列還在、log 只說「訊號 fanout 失敗」
**不提政策**。對帳時看到的是「有掃單簇但沒政策」,與「評了但沒命中」**完全無法分辨**。

**修法**:`_emit_policies` 自己包一層 try/except,log 訊息點名政策層與 code,
並加一個 `policy_emit_failures` 計數(換日彙總,同 `_peers_fn_failures` 的形)。

---

### F-11 `resolve_groups` 的同伴去重是 O(同伴數²)(**low**,只記帳)

**位置**:`signal_policy.py:120-122`

```python
for member in g["codes"]:
    if member != code and member not in peers:     # list 線性掃
        peers.append(member)
```

**實測**:現況(12 組 / 80 檔 / 最大 10 同伴)= **1.62 µs**;
`WATCHLIST_LIMIT = 150` 的單一族群最壞 = **80.1 µs**(50 倍)。
一天 41 顆事件 → 最壞 3.3 ms/日。**不要動。**
理由:保序去重的語意靠這個 list 表達得最直接;換成 `set` + list 要多一個資料結構,
而收益是每天 3 ms。只有在政策層被拉到 tick 級時才重估。

---

### F-12 `policy_quotes` 每個同伴建一份完整 `_quote_payload` 只為了 `chg_pct`(**low**,B06 F-15 已記,本輪補實測)

**位置**:`stock_engine.py:792`

**實測**:`_quote_payload` 形狀 = 0.316 µs,`policy_quotes` 單檔 = 0.815 µs
→ 10 同伴 8.58 µs、149 同伴 127 µs。一天 41 顆 → **0.35 ms/日**。**不要動。**

它的存在理由是正確的(「`chg_pct` 一律走 `_quote_payload` 這個唯一定義,不自己再算一次」——
除權息日分母是 `meta.ref_milli` 不是昨收)。抽一個 `_chg_pct(code)` 才是正解,
但那要等 F-04 讓每顆事件都付這筆錢、或政策層上 tick 級時再做。

---

### F-13 `_refresh_groups` 在 event loop 上同步讀檔(**low**)

**位置**:`app.py:843` `groups_fn = lambda: load_watchlist(wl_path)["groups"]`
→ `signal_hub.py:729` `self._groups = self._groups_fn()`
→ 呼叫端 `on_watchlist` ← `stock_engine.set_watchlist`(event loop 上)

**實測**:`load_watchlist`(2798 bytes / 80 檔 / 12 組)= **81.4 µs**。
頻率 = 自選/群組變更次數(一天個位數)+ 開機一次。**0.5 ms/日,不要動。**
列出來是因為它是「loop 上的同步檔案 IO」這個模式的一個實例,規模放大時要記得。

---

### F-14 前端 `SignalMsg` 缺 `d_close` / `d_high`,且政策列無跨語言 parity 測試(**low**,契約)

見 §6.3。功能零影響(TS 對多餘 JSON 欄不報錯),但與 CLAUDE.md §4 其他契約的做法不一致
(`AVG_SOURCES` / `PositionKind` / `PARAM_SPECS` 都有 parity 測試直讀對面字面)。

**修法**:`signal-model.ts` 補兩個 optional 欄(兩行),並考慮加一支
`test_policy_row_keys_parity_with_frontend`(後端直讀 `signal-model.ts` 的欄名清單),
與既有 `test_screen_group_name_parity_with_frontend` 同款。

---

### F-15 id 含 `B-a` / `B-b` 兩個內嵌連字號,`split("-")` 對四條政策行為不一致(**low**)

見 §6.2。repo 內無此類解析;風險在**無版控的研究目錄離線腳本**。
**修法**:不改 id(那是契約),在 `_emit_policies` 的 docstring 補一句
「解析政策標記請讀 `row["policy"]`,不要拆 id」。

---

### F-16 影子期第一週的線上數字與研究基準對不上(**high**,方法論,要 user 看)

見 §7.4。**發生率 2.7×、放到尾盤平均 −2,822 vs 研究 +5,784。**

這不是程式缺陷,是**母體不同**:研究面板 90 檔中僅 27 檔有自選群組;
線上自選 80 檔中 75 檔有族群或在盤前篩選(只有 5 檔 ALL IN 純成員是盲區)。

**建議**:週對帳(研究 R2)第一次就把「發生率」當作首要檢查項,而不是等四週後才看每筆損益。
發生率差 2.7 倍意味著兩邊在算不同的東西,**每筆期望值不可比**。

---

### F-17 影子模式的隔離是結構性的,不要動(**反向 finding**)

見 §4。四個訊號模組對 `copycat.capital` 的引用數 = 0;前端訊號元件對 `/api/capital` 的
引用數 = 0。**不要為了「方便未來下單」在 `signal_hub` 引入任何 capital 相依。**
實單接線的正確形狀是新的 consumer 讀 jsonl / WS,不是在 `_emit_policies` 裡加分支。

---

### F-18 `signal_policy.py` 整檔不需要任何效能改造(**反向 finding**)

純函式、零 IO、無狀態、O(同伴數);一天 41 次呼叫、合計 < 0.3 ms。
測試 30+ 條含四條政策的邊界(`chg` 恰等 max 不命中 / leader 平手算最強 / 鎖過只看同伴 /
多組聯集 / exclude 預設 / 零組只評 S / 同伴無報價只評 S)。
**這是全庫少數「量測完之後結論是別碰」的模組。**

---

### F-19 Discord 政策卡的「不掛同群摘要」是對的,不要動(**反向 finding**)

`signal_hub.py:1506-1518`。CONTEXT.md「族群」節明文:同群摘要是**另一把尺**
(取群組序第一個含它的組,盤前篩選 / ALL IN **都不扣**),只是通知裝飾。
政策卡第三行已經是族群脈絡,再掛同群摘要會在同一張卡裡並列兩個口徑不同的「同群」。
`format_policy_group_text` 早退 return(1518)把這件事釘死了。

---

### F-20 `_CLOSE_FLUSH_TIMEOUT` == `LIFESPAN_SLACK_SECS`(**low**,B06/B10 已記,本輪確認)

`signal_hub.py:109` `_CLOSE_FLUSH_TIMEOUT = 5.0`;
`shutdown_budget.py:43` `LIFESPAN_SLACK_SECS = 5.0`,而那個 slack 還要涵蓋
TC4 lane 與 COM join 之外的**全部**其他收尾。訊號落檔在最壞情況下可以把整個 slack 吃光。
影子期的具體風險:關機當下佇列裡的政策列寫不完 → jsonl 缺列 → 對帳少幾筆而**零訊號**
(`close()` 有 timeout log,但那是在 server 關機的 log 尾端,不會有人看)。
量級:jsonl 佇列實測全日零丟、盤後關機時佇列通常是空的。**記帳,不急著改。**

---

## 9. 失效模式表(零錯誤訊號的優先標出)

| # | 失效 | 觸發 | 症狀 | 零訊號? | 現在怎麼發現 |
|---|---|---|---|---|---|
| 1 | 盤前篩選群組不存在 | nightly 失敗 / 08:00 沒開機 / user 刪組 | S 政策整天零列(**佔政策列 74%**) | **是** | 沒辦法 → 要加 F-01 那行 WARNING |
| 2 | 自選把「ALL IN」改名、設定沒跟 | user 改組名 | 該組變族群,研究 −1,471/筆 | 半(一行 WARNING) | `grep 排除組名` logs;jsonl `groups` 含該名 |
| 3 | 自選有一組名叫「盤前篩選」但被 user 改名 | user 改組名 | S 母體歸零 + 32 檔變族群(同伴上限 10→40) | **是** | jsonl `groups` 含「盤前篩選」事後看得出 |
| 4 | 未命中事件零快照 | 恆常(36% 事件) | 門檻敏感度分析做不了 | **是** | 沒辦法 → F-04 |
| 5 | 影子期中途改 `configs/signals.json` | user 建檔/調參 | 對帳混用兩組門檻 | **是** | 沒辦法 → F-05 |
| 6 | server 未在 13:40 開著 / 停機 > 5 個日檔 | 常態(user 手動開機) | t1/t2/d_close 永久 null | **是**(log 只印補了幾列) | 事後數 jsonl null 列 → F-07 |
| 7 | 同伴 `chg_pct` / `touched_upper` 為 None | 同伴 no_data / 尚未成交 / 缺 meta | P / B 偏向命中(fail-open) | 半(jsonl `peers[]` 有記) | 事後過濾 jsonl(4% 實測) |
| 8 | `peers_fn` 例外 | engine 異常 | 整顆事件降級成 S-only | 半(當日首次 traceback + 換日彙總) | `grep 政策行情快照` |
| 9 | `_groups` 開機讀檔失敗 | 自選檔壞 | P/B/S 整天零列 | 半(一行 exception) | `grep 群組結構讀取失敗` |
| 10 | `_emit_policies` 拋例外 | publish / 畸形 quotes | 政策列部分或全部消失 | 半(泛用 `訊號 fanout 失敗`,不提政策) | 對帳看到「有掃單簇無政策」但分不出原因 → F-10 |
| 11 | `_policy_touch` 沒歸零 | engine 日別停在昨日(空自選 / 零推播),`on_rollover` 不觸發 | 隔天所有政策列 `first_of_day=False` → **全部 notify=False**,Discord / toast 整天無聲 | **是**(rail 仍列出) | 比 `/api/health` 的 trade_date 與牆鐘 |
| 12 | ALL IN 純成員(5 檔)無政策 | 設計如此 | user 最看好的幾檔政策層永遠沉默 | **是** | 本輪實測才看得出 |
| 13 | 舊 dist 前端 | 部署前後端版本落差 | 政策 chip / 【標記】前綴消失,規則視窗「編輯」TypeError | 半(版本落差膠囊) | CLAUDE.md §4 已記 |
| 14 | 關機時政策列還在佇列 | 盤中關機 | jsonl 缺列 | **是**(只有關機尾端一行 timeout log) | 對帳少筆數 |
| 15 | 盤中重啟 | user 重啟 | detector 狀態全失、回補 tick 不重放 → 那段的掃單簇整段不發;jsonl 無斷點記號 | **是** | B06 已記,對帳分不出「沒事件」與「沒在聽」 |

---

## 10. 改造順序(每一步的量測判準)

> 原則:**先讓對帳成立,再談別的**。政策層沒有效能問題(§2.3),四週影子期的價值
> 完全取決於四週後的資料夠不夠回答問題。下面 1–5 都是「加欄 / 加 log / 加計數」,
> 零行為改變、合 W1 契約;6–8 才碰判定或架構。

| # | 做什麼 | 為什麼排這裡 | 工作量 | 量測判準 | 回退 |
|---|---|---|---|---|---|
| 1 | hub 啟動印一行固定字串 `政策門檻:peer_up=… max_chg=… push_end=… exclude=[…] screen_group=…` | 五分鐘、零風險、讓 F-05 的一半立刻可查;也順帶把 F-01 / F-02 的現況記進 log | S | 重啟後 `grep "政策門檻" logs/server-*.log` 恰一行且四個值 = 現行設定 | 刪一行 |
| 2 | `_refresh_groups` 補兩道檢查:`SCREEN_GROUP` 不在組名裡 → WARNING(F-01);`_groups` 空且 `_watch` 非空 → WARNING(F-09)。沿用「集合變了才印」的節流 | F-01 是唯一 critical 且**沒有任何現存訊號**的路徑;S 佔政策列 74% | S | 紅先行:造一份無「盤前篩選」組的自選 → 測試斷言恰一行 WARNING 且不重複;真環境 = 下一個交易日 `grep "盤前篩選"` 為 0(正常態) | 刪兩個 if |
| 3 | 回填結束多印「仍有 n 列 t1/t2/d_close null」「m 個日檔滑出視窗未掃」(F-07) | 影子期進行中,現在不加就是在累積不可回填的 null;實測已經有 87 列處在這條路上 | S | 13:40 log 出現該行;拿現況 09-10/09-11 當 fixture 斷言 n=87 / m=0;補完後次日該行 n=0 | 刪一行 |
| 4 | 政策列加 `thresholds` 欄;raw `sweep_cluster` 列加 `policy_ctx` 欄(F-04 + F-05)。**只加欄,不動既有欄與行尾** | 對帳的兩個結構缺口;越晚做,能重算的天數越少 | M | ①`tests/server/test_signal_outcome.py` 的 byte 比對仍綠(舊列不動)②新列 `set(row)` 測試更新 ③一天後 `data/signals/<日>.jsonl` 中 `kind=sweep_cluster` 的列 100% 帶 `policy_ctx`(現況 64% 才有族群資訊)④檔案成長 ≤ +50%(現況 ~290 KB/日) | 拿掉兩個鍵;舊列不受影響 |
| 5 | 加 `peers_unquoted` / `peers_touch_unknown` 兩個欄 + 換日彙總 WARNING(F-08);`_emit_policies` 自己包 try/except + 計數(F-10) | 讓 §3.3 的 fail-open 與政策列遺失從「事後才推得出」變成「當下看得到」 | S | 拿影子期 5 日 jsonl 重放 → 兩個計數 = 3 / 3;造一顆 publish 拋例外的事件 → log 點名政策層且 raw 列仍在 | 刪欄 / 刪傘 |
| 6 | **停等 user 拍板**:B-a 四週後無樣本怎麼辦(F-06);線上 P 發生率 2.7× 研究基準怎麼處理(F-16) | 這兩條決定「四週後要拿什麼跟什麼比」,是方向性抉擇不是實作 | — | user 拍板 | — |
| 7 | 寫一支對帳腳本(repo 內、有版控):讀 `data/signals/*.jsonl` + `data/audit/capital-*.jsonl`,輸出研究 §8.2 同形的表(同檔一筆 / `late==0` / 放到尾盤 = `d_close-price` / T+1 = `t1_open-price` / 鎖死 = `d_close==還原 upper`)與對帳三桶 | 研究 R2 要求每週對帳,而現況研究基準腳本是**無版控 7,306 行 + repo 外 971 MB 資料**;不搬進來,四週後沒有可重跑的比較基準 | M | 拿影子期 5 日跑出表,`d_close==還原 upper` 的還原誤差 = 0(本輪已實測 151/151 還原成整數毫元);三桶數字與人工抽查 5 筆一致 | 純新增腳本 |
| 8 | (**只在影子期真的踩到才做**)`resolve_groups` 的 peers 去重換 set(F-11);`_chg_pct(code)` 從 `_quote_payload` 抽出(F-12) | 兩者現況合計 < 4 ms/日;只有在 F-04 把政策層變成「每顆事件都評」且自選逼近 150 檔時才有意義 | S | 同一份 tick 流 replay,`resolve_groups` 在 150 檔單族群下從 80 µs 降到 < 10 µs;`copycat validate` 仍 PASS | git revert |

**不做的事**(明確劃掉):
- 不為政策層引入 numpy / polars / orjson(§2.3:一天 1.8 ms)。
- 不改四條政策的判定式(那是 2026-09-07 拍板,改了影子期就白做)。
- 不動 jsonl 的序列化器與行尾(CLAUDE.md §4 W1 + `grep '"kind": "policy"'` 判準依賴
  `json.dumps` 預設 separators 的空白)。
- 不動 `format_policy_group_text` 的四行卡與「不掛同群摘要」(F-19)。

---

## 11. 工具選型

| 工具 | 用在哪 | 為什麼 | 取捨 | 結論 |
|---|---|---|---|---|
| (無新套件)固定字串啟動 log | hub `__init__` / `start()` | F-05 的一半、F-01 / F-02 的現況快照 | 零 | **建議導入** |
| (無新套件)`_refresh_groups` 兩道檢查 | `signal_hub.py:736` | F-01(唯一 critical 且零訊號) | 零 | **建議導入** |
| (無新套件)只加欄:`policy_ctx` / `thresholds` / 兩個 unknown 計數 | `_emit` / `_emit_policies` | F-04 / F-05 / F-08 | W1 契約允許「只加欄」;檔案 +290 KB/日;`test_signal_outcome` byte 比對要確認舊列不動 | **建議導入** |
| (無新套件)repo 內對帳腳本 | 新檔 `scripts/` 或 `copycat/cli.py` 子命令 | 研究基準無版控、在 repo 外 | 要把研究 §8.2 的口徑抄一份進來(勘誤後的 `late==0` 版) | **建議導入** |
| `orjson` | 回填的逐行 `json.loads`(F-07 / B06 F-10) | 解析快 3–6× | **不可用於 jsonl 寫入**(空白 / 浮點字面 / byte 比對三條契約);讀側收益 = 每日 13:40 的 20–35 ms | 有條件(只讀);**現階段不值得**,先做 B06 F-10 的 to_thread 包裝 |
| `numpy` / `polars` / `pandas` | 政策層線上路徑 | — | 一天 41 次呼叫、每次 45 µs | **不建議** |
| `pandas` / `polars` | **離線對帳腳本**(第 7 步) | 151 列 → 四週 ~600 列的表格運算 | 不進 runtime 相依(`pyproject` `dependencies = []` 不變),只是開發腳本;**但本專案 .venv 現在一個都沒裝** | 有條件:純 stdlib(`csv` + `statistics`)就夠 600 列,**建議先不裝** |
| `msgspec` | 政策列 struct 化 | 型別安全 | 政策列 34 鍵、前端鏡像、W1 離線讀者全部是逐字契約 | **不建議** |
| Prometheus / OpenTelemetry | hub 計量 | F-01/02/07/08/10 的計數 | 新 runtime 相依 + 一個要顧的 endpoint;本專案沒有 DB、沒有 metrics 基礎設施 | **不建議**;`/api/health` 加一個 `signals` 區塊就夠(B06 F-16 同結論) |

---

## 12. 不要動的地方

1. **`signal_policy.py` 整檔**(F-18):純函式、零 IO、與 CONTEXT.md 逐字對得上、
   30+ 條測試含所有邊界。效能上一天 < 0.3 ms。
2. **四條政策的判定式與 `POLICIES` 固定序**:2026-09-07 拍板,影子期進行中。
   改任何一個閘(含把 `peer_touched` 的 None 語意改掉)= 影子期前幾週的資料作廢。
3. **`鎖過閘只看同伴、自己鎖過不擋`**(`signal_policy.py:15-17` docstring):
   review F-01 拍板沿 spec 字面,列上 `self.touched_upper` 有記可事後過濾。
4. **`chg` 的 `round(..., 2)`**(`signal_hub.py:1091`):與同伴的 `_quote_payload` round 2
   是同一把尺,`leader` 的比較才不是兩把尺(review F-01,有測試)。
5. **`policy_quotes` 的「每一檔要求的 code 都在回傳字典裡」**(`stock_engine.py:768-770`):
   整檔缺席會讓「族群有幾檔」跟著行情波動。
6. **`_policy_touch` 在 publish 之後才記**(`signal_hub.py:1163-1165`,spec review F-04)。
7. **Discord 政策卡不掛同群摘要**(F-19)+ `format_policy_group_text` 的
   「至少一列政策列」早退(review F-10)。
8. **回填的「只重寫被補的列、其餘位元組逐字保留、行尾原樣」**(`signal_hub.py:1327-1381`):
   離線讀者契約 + `tests/server/test_signal_outcome.py` byte 比對釘住。
9. **`_refresh_groups` 讀檔失敗保舊值不清空**(`signal_hub.py:730-735`)。
10. **`_emit_policies` 是同步內聯、零 await、零 IO**:快照是 engine 記憶體讀。
    這是「政策層不拖慢熱路徑」的根據,改成 async 會把 await 點引進 `_emit`。
11. **影子模式的零 capital 相依**(F-17)。

---

## 13. 開放問題

1. **B-a 四週後無樣本怎麼辦?**(F-06)接受無結論,還是改成「全事件快照 + 事後重算」?
2. **線上 P 發生率是研究基準的 2.7 倍、初步每筆為負** —— 母體不同已經確定,
   那影子期的成功判準要不要跟著改?(研究 Q6b 拍板「不設事前標準,四週後只寫成績」,
   但「成績」拿什麼當對照?)
3. **ALL IN 純成員(現況 5 檔)政策層永遠沉默,是接受還是要有第二條路?**
   (例如:ALL IN 成員自動享有 S 政策的對待?)這會改政策定義,要拍板。
4. **`policy_ctx` 加到 raw 掃單簇列會讓每顆事件都付 `peers_fn`** —— 成本實測可忽略
   (+0.13 ms/日),但它改變了「`peers_fn` 只在命中時被叫」這個測試釘住的性質
   (`test_p_hit_full_row_schema` 的 `assert wl.peers_calls == 1`)。要不要改?
5. **研究基準腳本(`Documents\copycat-trading-review\scripts\combo_wlpolicy.py` 等 40+ 支、
   無版控)要不要搬進 repo?** 不搬的話四週後的對帳沒有可重跑的比較基準。
6. **`data/audit/capital-*.jsonl` 與 `data/signals/*.jsonl` 的 join 鍵是什麼?**
   現況只有 (日期, 股號, 時刻) 可對。對帳三桶要人工還是要工具?
7. **影子期若中途改自選群組(已經發生過:memory 記 09-08 依 Excel 族群表重排)**,
   那前後兩段的族群定義不同 —— 對帳是分段比還是用 `peers[]` 快照統一重算?
   (後者做得到,但需要 F-04 補齊未命中事件。)

---

## 附:量測可重跑

```
cd C:\side-project\copycat
PYTHONUTF8=1 .venv\Scripts\python.exe <scratchpad>\order-signal-scan\bench_policy.py
```

真實資料統計的一次性腳本內容見 `shadow_stats.txt` / `coverage.txt` / `peers.txt` 的產生指令
(全部是 `.venv\Scripts\python.exe -c` 的唯讀 glob + `json.loads`,不寫 repo)。
