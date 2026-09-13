# S1-detector-core — 訊號偵測器核心演算法(`copycat/live/signal_state.py`)

掃描日期:2026-09-13 · 範圍:`copycat/live/signal_state.py`(855 行,整檔讀完)
+ 邊界檔 `copycat/signals_config.py`、`copycat/signal_rules.py`、
`copycat/server/signal_hub.py`(`_make_slot` / `on_tick` / `on_book` / `_distribute` / `_context`)、
`copycat/server/stock_engine.py:1316-1367`(掛點)、`tests/fixtures/sweep_cluster_golden.json`。

**所有數字都在 repo 的 `.venv`(CPython 3.13.13 / Windows 11)實跑**,腳本留在同目錄:
`bench_s1.py`(逐 kind / 窗長 / 記憶體 / golden 重放)、`bench_parts.py`(逐段拆解,延遲預算來源)、
`bench_dead.py`(死工)、`bench_agg.py`(以 `logs/` 真實 tick 數回推聚合量)。
真實資料來源:`logs/server-2026091*.log` 的 `stock backfill <code>: N ticks` 行、`data/signals/*.jsonl`
(09-01~09-11 共 10 個交易日)。**未改動 repo 任何檔案、未啟動 server、未下任何單。**

---

## 0. 三句話結論

1. **演算法本身大致正確**:六種 kind 的滑動窗全部是 `deque` + 單向剪裁(amortized O(1)),
   掃單簇與 CONTEXT.md 的定義**逐字相符**,golden fixture 三個股票日重放 4/4、5/5、2/2 全中。
   唯一的 O(n) 是 `_eval_volume` 的 `sum()`。
2. **但這一段的成本有 73% 是架構死工**:prod 7 條規則 = 7 顆 detector,實測 24.63 µs/tick;
   同一份工作用單顆六 kind 全開的 detector 做只要 **6.65 µs/tick**。死工是固定的
   **2.76 µs/tick/顆**(與窗長無關,已實測三個窗長都一樣)。
3. **聚合起來目前不是延遲問題,但完全量不到**:以 09-11 開盤真實 tick 數回推,
   09:00–09:05 訊號層佔 event loop **0.52%**(1,548 ms / 300 s);單一 callback 最壞 ~128 µs,
   遠低於 Windows 15.6 ms 的抖動地板。**真正的缺口是儀器**:
   `SignalEvent` 與 jsonl 每一列都**沒有「伺服器何時發出」**,
   `now − tick.time`(= feed 延遲)兩個值都在手上卻從來沒有人相減 ——
   一套要下實單的系統,無法事後回答「這則訊號當時遲了多久」。

---

## 1. 現況地圖:一筆 tick 怎麼走過偵測器

```
stock_engine._handle_quote(quote)            ← event loop 單執行緒
  └ state.ingest(tick) 為真
       └ hub.on_tick(code, tick, state)                      signal_hub.py:598
            ├ ctx = _context(state, tick.cum_vol)            (每 tick 一次,全規則共用)
            └ for slot in self._slots.values():              ← N = 7(prod)
                 slot.detector.evaluate(code, tick, ctx, slot.enabled)
```

`SignalDetector.evaluate`(`signal_state.py:292-332`)的內部順序,**每一段的歸屬要看清楚**:

| # | 段 | 條件 | 是否無條件付 |
|---|---|---|---|
| 1 | `now = self._now_fn()` + `_in_session(now)` | 09:00 ≤ now < 13:30 | 無條件 |
| 2 | `tick.trade_date != ctx.trade_date` | 舊日 snapshot gate | 無條件 |
| 3 | `mono = _mono(now)`;`key = tick.time or _clock_key(now)` | — | 無條件 |
| 4 | **`_eval_sweep`**(311) | 在「首 tick 只初始化」gate **之前** | **無條件**(含 deque 維護) |
| 5 | 首 tick 初始化 → return | `code not in self._prev` | — |
| 6 | window append + 剪裁(318-323) | — | **無條件** |
| 7 | `_eval_cdp`(326) | `basis` 空即早退 | 有 basis 就無條件跑滿 |
| 8 | `_eval_surge`(327) | `enabled` **先**檢查 ✔ | 早退 |
| 9 | `_eval_pullback`(328) | `enabled` 檢查在 **615 行** | **無條件跑完整台狀態機** |
| 10 | `_eval_volume`(329) | `enabled` **先**檢查 ✔,再 15 分鐘閘 | 早退 |
| 11 | `_eval_limit_tick`(330) | latch 轉移在 802/805 無條件 | **無條件** |

這個「狀態推進無條件、`enabled` 只 gate 事件產出」是 design R2 的**刻意設計且正確**
(關掉爆拉不影響共用窗的爆量、停用期間 latch 照轉、重開不補發)。
問題不在這個語意,而在**它被放在「一規則一顆 detector」的架構下**:
`_make_slot`(`signal_hub.py:455-463`)給每條規則一顆全新 detector 且
`enabled = frozenset({rule["kind"]})`,於是 `limit_lock` 那顆 detector 的掃單簇 / 回檔 / 窗
狀態**在結構上永遠不可能被任何人讀到**。

### 1.1 prod 的真實形狀(實測,不是推論)

`data/signal_rules.json` 磁碟上仍是 **v1 / 4 條**(2026-08-15),
`load_rules` 每次啟動跑 `_migrate_v1→v2→v3` 得到 **7 條**(實跑驗證):

```
cdp_cross       enabled=True  notify=False  cd=600   rearm_ticks=5  rearm_dwell=300
surge_crash     enabled=True  notify=True   cd=1800  pct=2.0  window=300
vol_burst       enabled=True  notify=False  cd=1800  ratio=3.0 window=300 min_elapsed=15
limit_lock      enabled=True  notify=True   cd=600
surge_pullback  enabled=True  notify=True   cd=60    surge_pct=2.0 window=300 pct=1.0
surge_pullback  enabled=True  notify=True   cd=60    surge_pct=2.0 window=300 pct=2.0
sweep_cluster   enabled=True  notify=False  cd=60    cluster=30 min_sweeps=2 min_levels=2 up=0.3 up_win=60
```

自選 `data/stock_watchlist.json` = **80 檔**(含「盤前篩選」32 檔)。
**七條規則只有兩種窗長**:`surge_window_secs` 全是 300、`sweep_up_window_secs` 60。
去重率 7 → 2,這是 §5 合併方案的關鍵前提。

### 1.2 真實 tick 率(從 `logs/` 的回補行回推)

`stock backfill <code>: N ticks` 記的是 server 起動時該檔「當日已發生」的 tick 數。
起動時刻決定它涵蓋多長的窗:

| 來源 | 涵蓋 | 檔數 | 總 tick | 每檔 median | p90 | max |
|---|---|---|---|---|---|---|
| `server-20260908-1838.log` | 全日 16,200 s | 86 | 335,407 | 1,883 | 11,513 | 34,696 |
| `server-20260911-0905.log` | 09:00–09:05(300 s) | 83 | **49,368** | 309 | 1,774 | **3,368** |
| `server-20260910-0905.log` | 09:00–09:06(360 s) | 95 | 50,942 | 263 | 1,264 | 5,280 |

→ **開盤 5 分鐘的聚合 tick 率 = 164.6 筆/秒**(83 檔),單檔最熱 11.2 筆/秒;
全日平均 20.7 筆/秒、單檔 median 0.116 筆/秒。
開盤 5 分鐘吃掉全日 tick 的 ~15%。

**`surge_window_secs = 300` 讓「09:05 當下的窗長」恰等於「該檔 09:00 以來的全部 tick」** ——
所以上表的 09:00–09:05 那一列**就是窗長分佈本身**,不必推估:median 309、p90 1,774、max 3,368。

---

## 2. 端到端延遲預算(逐段可加總;`bench_parts.py` 實測)

單顆 detector、窗長 1,771(= 開盤 p90)、`tick.time` 非空:

| 段 | 位置 | 成本 | 基礎 | 備註 |
|---|---|---|---|---|
| `now_fn()` | 301 | 0.064 µs | 實測 | 每顆各叫一次 → ×7 |
| `_in_session(now)` | 366 | 0.097 µs | 實測 | `now.time()` 比較 |
| 舊日 gate | 304 | ~0.02 µs | 實測 | 字串比較 |
| `_mono(now)` | 305 | 0.202 µs | 實測 | timedelta + total_seconds;×7 |
| `_eval_sweep` 全段 | 311/686-779 | **0.753 µs** | 實測 | 含 `tick_secs` 0.281、lookback append+trim、群比對、`round()` |
| window append + 剪裁 | 318-323 | 0.082 µs | 實測 | **amortized O(1),與窗長無關** |
| `_eval_cdp`(有 basis) | 326/382 | **1.659 µs** | 實測 | `tick_size_milli` + `_advance_rearm`(5 線)+ `_advance_sides`(5 線、2 個 list) |
| `_eval_cdp`(無 basis) | 391 | ~0.05 µs | 實測 | dict.get + falsy 早退 |
| `_eval_surge`(停用) | 523 | 0.081 µs | 實測 | `enabled` 先檢查 ✔ |
| `_eval_pullback`(無條件) | 328/556 | 0.258 µs | 實測 | `enabled` 在 615 才檢查 |
| `_eval_volume`(停用) | 647 | 0.093 µs | 實測 | `enabled` 先檢查 ✔ |
| `_eval_volume`(啟用,窗長 1,771) | 658 | **49.9 µs** | 實測 | 其中 `sum()` 51.3 µs(單獨量) |
| `_eval_limit_tick`(無條件) | 330/783 | 0.375 µs | 實測 | 2 個 4-tuple + `_locked_up/_down` |
| **evaluate 包裝** (list/extend/try) | 292-332 | ~0.7 µs | 推估(差額) | 6 次 `events.extend` + hub 的 `list()` + try/except |
| **單顆死工小計**(enabled=∅) | — | **2.76 µs** | 實測 | 三個窗長(35 / 1771 / 3361)量到同一個值 |
| **停用的 cdp 規則死工** | — | **4.62 µs** | 實測 | `_distribute` 不看 `enabled`,basis 照分發 |
| `evaluate_book`(latch 全 False) | 334-362 | **2.344 µs** | 實測 | 其中 `_clock_key` **1.765 µs = 75%**,產出恆 `[]` |
| `_latch.get()`(短路候選) | — | 0.043 µs | 實測 | 短路後的替代成本 |

### 2.1 合計(prod 7 顆,逐窗長實測)

| 窗長(= 該檔 tick 率 × 300 s) | prod 7 顆 | 單顆 6-kind 全開 | vol_burst 15 分鐘閘擋著時的 7 顆 |
|---|---|---|---|
| 35(全日 median 0.116 筆/s) | **24.63 µs** | **6.65 µs** | 23.4 µs |
| 1,771(開盤 p90 5.9 筆/s) | **77.81 µs** | 60.71 µs | — |
| 3,361(開盤 max 11.2 筆/s) | **127.52 µs** | 102.26 µs | **35.24 µs**(09:02 實跑) |

**最後一欄是關鍵**:`vol_burst` 的 `min_elapsed_min = 15` 閘(`signal_state.py:651`)
在 09:00–09:15 擋在 `sum()` **之前**,所以**一天中 tick 最密的 15 分鐘,最貴的那一段根本沒付**。
上一輪報告推的「開盤 13.8 ms/秒 loop 佔用」據此**應予修正**:那個數字假設 `sum()` 在開盤就在跑。

### 2.2 聚合到整個系統(`bench_agg.py`,以 09-11 開盤真實 tick 數加總)

```
09:00–09:05 這 300 s 的訊號偵測層 CPU:
   現況(vol_burst 15 分鐘閘擋著)     1,548 ms / 300 s = 0.516 % loop
   若閘拿掉(= 09:15 之後同節奏)      3,483 ms / 300 s = 1.161 % loop
   合併成單顆 6-kind(閘開)          2,542 ms / 300 s = 0.847 % loop
   合併 + running sum(推估 ~7 µs)     346 ms / 300 s = 0.115 % loop
最熱單檔(11.2 筆/s、窗長 3,368):09:15 後每 tick 127.7 µs × 11.2/s = 1.43 ms/s
單一 event-loop callback 最壞:~128 µs(= 一則 quote × 7 顆)
```

**誠實結論:偵測器核心今天不是延遲瓶頸。**
單次 callback 128 µs 遠低於 Windows timer 的 15.6 ms 抖動地板,聚合 0.5–1.2% loop。
但它是**可以被 REST 一鍵引爆的**(見 F-06),而且**完全量不到**(見 F-01)。

### 2.3 簿路的未知數(唯一量不出來的一格)

`on_book`(`stock_engine.py:1366`)對**每一則** watched quote 無條件呼叫,每顆 detector 2.344 µs
× 7 = **16.0 µs/quote**,其中 12.4 µs 是七次 `_clock_key` 的 strftime,而 `limit_open`
**一天全自選 0–9 則**(實測 09-01~09-11:0,2,4,6,9,2,2,5,1,0)。
`logs/` 完全沒有 quote 計數(只有 tick 計數),所以 quote:tick 比**量不出來**。
以「TWSE 逐筆撮合下,純委託簿變動事件約為成交的 2–5 倍」推估,開盤聚合 330–820 quote/s
→ **5.3–13.1 ms/s(0.5–1.3% loop),與 tick 路同級或更大**。
這是本區塊第一個該補的探針(§7)。

---

## 3. 六種 kind 逐一拆解

### 3.1 `cdp_cross` — CDP 五線穿越

- **演算法**:per (code, level) 存 `(線價, 側別 −1/0/+1)`;側別相反 = 穿越。
  `price == 線價` 是「線上」:不觸發也不改側別(`_advance_sides`,463-510)。
  另有兩道抑制:per (code, level) cooldown 600 s,以及 `_suppressed` 的
  「距離 + 駐留」重武裝(`_advance_rearm`,433-461)—— 要**連續**待在
  `|price − 線價| ≥ rearm_ticks × tick_size_milli(price)` 外滿 `rearm_dwell_secs`(300 s)才解除。
- **資料結構**:`_basis: dict[code, dict[level, milli] | None]`、
  `_side: dict[(code, level), (int, int)]`、`_suppressed: dict[(code, level), float | None]`、
  `_cooldown` / `_touch: dict[(code, kind, level), …]`。
- **複雜度**:O(線數)= O(5),與窗長無關。
- **每 tick 成本**:**1.659 µs**(有 basis)/ ~0.05 µs(無 basis 早退)。
  兩個 list(`below`/`above`)每 tick 新配置;`_sign()` 呼叫 2×5 次。
- **狀態大小**:每檔 5 線 × (side tuple 64 B + suppressed float 24 B + cooldown/touch 各一格)
  ≈ **1.0 KB/檔**,與時間無關。
- **產量**(實測 09-01~09-11):**每日 78–299 列,佔全部訊號列的 43%** ——
  而它 `notify_discord = False`(spec #192 起,組合回測每筆為負)。
  **全庫最貴的無條件狀態推進,服務的是價值最低的 kind。**
- **一個細節**:`gap` 用**當筆價**的檔距,線價卻是固定的。價格在檔距分界
  (10/50/100/500/1000 元)附近來回時 gap 會跳 5 倍 → `_advance_rearm` 的駐留計時可能
  被反覆歸零。影響是「重武裝比預期慢」,零錯誤訊號,量級小。

### 3.2 `surge` / `crash` — 爆拉爆跌

- **演算法**:共用窗 `_window[code]`(`(mono, price, qty)` 三元組 deque),
  `_window_change_pct(window, price)` = 窗最舊點到現價的漲跌幅,`≥ ±surge_pct`(2%)即發。
  **冷卻桶 surge / crash 共用**(`(code, "surge_crash", "")`,1800 s),`touch_count` 分開計。
- **複雜度**:O(1)(窗頭一格 + 現價)。剪裁 amortized O(1)(實測 append+popleft 0.082 µs)。
- **每 tick 成本**:0.081 µs(停用早退)/ ~0.3 µs(啟用未命中)。
- **狀態大小**:窗本身(見 §6),另加 2 格 cooldown/touch。
- **產量**:surge 20–92、crash 22–56 列/日。
- **已知盲點(檔內自承,`signal_state.py:579`)**:0 價 tick 會進共用窗,成為窗頭時
  `_change_pct(0, price)` 回 None → 該段窗靜默不判。

### 3.3 `surge_pullback` — 爆拉回檔

- **演算法**:`_pullback[code] = (armed, peak, fired_at, rearm_base)`。
  未武裝 → surge 同式(共用 `_change_pct`,`signal_state.py:151-159` 是**唯一算式**)判武裝;
  武裝後追峰值;`(peak − price) × 100 / peak ≥ pullback_pct` 即發並消耗本波;
  重武裝兩條路:創新高(嚴格 >),或自 `rearm_base` 重跑 surge 同式。
- **複雜度**:**每 tick O(1)**;只有發訊那一刻 `snap = next(p for ts,p,_q in window if ts >= mono)`
  是 O(窗長),一波一次。這是 review F-02 從「每 tick 掃窗」改過來的,**寫得對**。
- **每 tick 成本**:0.258 µs(無條件全跑,`enabled` 檢查在 615 行)。
- **狀態大小**:每檔一個 4-tuple ≈ 88 B。
- **產量**:兩張卡(1% / 2%)合計 **56–220 列/日,第二多**。
- **已知且接受的代價**(pr-177 F-01,2026-09-02 拍板):同波 V 型反彈自發訊價 +2%
  即構成重武裝 → 近重複的第二則。

### 3.4 `vol_burst` — 爆量(**全庫唯一的 O(n) per-tick 運算**)

```python
# signal_state.py:649-659
open_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)   # 每 tick 新配置一個 datetime
elapsed_min = (mono - _mono(open_dt)) / 60
if elapsed_min < self._cfg.vol_min_elapsed_min:      # 15 分鐘閘 —— 在 sum() 之前 ✔
    return []
avg_per_min = ctx.day_volume / elapsed_min           # ctx.day_volume = tick.cum_vol
window_vol = sum(qty for _ts, _price, qty in window) # ← O(窗長)
ratio = window_vol / (avg_per_min * window_min)
```

- **複雜度**:O(窗長)。實測 `sum()` **27–31 ns/筆**,線性到 18,000 筆都成立:

  | 窗長 | 35 | 213 | 309 | 643 | 1,774 | 3,368 | 18,000 |
  |---|---|---|---|---|---|---|---|
  | `sum()` | 1.10 µs | 5.84 | 8.43 | 17.47 | 49.49 | **94.90** | 484.21 |

- **但 15 分鐘閘救了最糟的那一段**:09:00–09:15 是全日 tick 最密的窗,而那段 `sum()` 不付。
  實測 09:02 起、窗長 3,361 時 `vol_burst` 只要 **3.28 µs/tick**(vs 09:15 後的 97.94 µs)。
- **狀態大小**:借用共用窗,零額外狀態(2 格 cooldown/touch)。
- **產量**:5–56 列/日。
- **一個真正的量化問題(不是效能問題)**:分母 `avg_per_min = 當下累積量 ÷ 自 09:00 的分鐘數`
  是**移動中的尺**。開盤集合競價那一筆巨量在 09:15 佔 15 分鐘均量的很大比例 → ratio 被壓低;
  時間越晚、均量被中午的清淡稀釋越多 → 同樣的窗量越容易過門檻。
  **實證**(09-10 + 09-11 兩日 kind × 小時):

  ```
  vol_burst   09h: 5    10h: 10   11h: 14   12h: 31   13h: 26
  cdp_cross   09h: 379  10h: 72   11h: 43   12h: 61   13h: 32
  ```

  **tick 率在 09h 最高、事件卻最少;12–13h tick 最少、事件最多。**
  「爆量」的門檻在一天之內不是同一把尺 —— 早上嚴、下午鬆,而且是單調的。
  對影子期對帳來說這是系統性偏差,不是雜訊。

### 3.5 `limit_lock` / `limit_open` — 鎖漲跌停與打開

- **演算法**:`_latch[(code, direction)]` 布林 latch。
  tick 路 `_eval_limit_tick`(783-811):`locked and not latched` → 上鎖發訊;
  `latched and opened` → 打開發訊。簿路 `evaluate_book`(334-362):只處理打開
  (尾盤解鎖無成交也抓得到,design §3.5b)。
  鎖定判定是複合簽名(`_locked_up`,813-818):價 = 漲停 **且** 賣側限價空
  **且**(買側首檔是市價佇列 `price == 0` **或** 最佳限價買 = 漲停)——
  第三項排除「首攻吃光賣盤」的假陽性,**寫得對**。
- **複雜度**:O(1)。**每 tick 成本 0.375 µs(無條件)**;簿路 2.344 µs(見 3.5b)。
- **狀態大小**:每檔 2 格 latch + 最多 4 格 cooldown/touch ≈ 0.4 KB。
- **產量**:limit_lock 5–10、limit_open 0–9 列/日。**全部六種 kind 裡最稀有的。**
- **3.5b — `evaluate_book` 的早退鏈(本區塊最便宜的一筆改動)**:

  ```python
  def evaluate_book(self, code, ctx, enabled):
      now = self._now_fn()                      # 0.064 µs
      if not self._in_session(now): return []   # 0.097
      mono = _mono(now)                         # 0.202   ← 只在發訊時用得到
      key = _clock_key(now)                     # 1.765   ← 只在發訊時用得到(75% 的成本)
      for direction, limit_milli, reopened in ( (...), (...) ):   # 2 個 3-tuple 字面
          if limit_milli is None or not reopened: continue
          if not self._latch.get((code, direction), False): continue
          ...
  ```

  **早退之前付掉的**:`now_fn` + `_in_session` + `_mono` + `_clock_key` + 兩個 tuple 字面
  = **2.344 µs/顆 × 7 顆 = 16.0 µs/quote**,而產出在 99.99…% 的 quote 上恆 `[]`。

  **latch 旗標短路的等價性證明**:
  1. `evaluate_book` 產出事件的**唯一**路徑是 `self._latch.get((code, direction), False)` 為 True。
  2. 本方法的**唯一**寫入是 358 行 `self._latch[(code, direction)] = False`,
     而它在同一個 `if latch is True` 分支之內;`_cooldown` / `_touch` 的寫入只在
     `_limit_event`(825-855),也只由該分支可達。
  3. `now` / `mono` / `key` 是純計算,不寫任何狀態。
  ∴ 維護一個 `self._latched: set[str]`(在 `_eval_limit_tick` 上鎖時 `add(code)`、
  打開時 `discard`,`reset_day` / `drop_code` 清)並在開頭 `if code not in self._latched: return []`,
  **與現況逐案例精確等價**,成本 2.344 → ~0.06 µs(集合查找)。
  7 顆合計 16.0 → **~0.4 µs/quote(砍 97.5%)**。

### 3.6 `sweep_cluster` — 掃單簇(spec #192)

**CONTEXT.md 定義 vs 實作,逐句對照**:

| CONTEXT.md 定義 | 實作 | 相符? |
|---|---|---|
| 同一檔**相鄰且同毫秒**的一群成交 | `group.time_key != key` → 開新群(`729-733`);`key = tick.time`(TC4 PreciseTime) | ✔ |
| 首筆外盤(成交價 ≥ 賣一,賣一可得且 > 0) | `outer = ask is not None and ask > 0 and price >= ask`(727) | ✔ 逐字 |
| 群內出現高於首價的成交 | `if price <= group.first_milli: return []`(740) | ✔(見下註) |
| 層數 =(群高 − 首價)÷ **首價檔距**,四捨五入,≥ 2 | `round((high - first) / tick_size_milli(group.first_milli))`(738) | ✔ 逐字 |
| 30 s 內 ≥ 2 個掃單 | `sweeps` deque 剪到 `[s − cluster_window, s]`,`len(sweeps) ≥ min_sweeps`(746-752) | ✔ |
| 60 s 漲幅 ≥ 0.3% | `(high / base[1] - 1) * 100`,base = 時刻 ≤ s − 60 的**最後一筆**(718-722, 751) | ✔ |
| 窗前無成交 → 0 | `if base[0] <= cutoff else 0.0`(751) | ✔ |
| 60 s 去重 | 規則 cooldown 60 s(`sweep_cooldown_secs`,`COOLDOWN_MIN = 60` 恰等於研究值) | ✔ |
| 線上採「群內首次達標即發」 | `qualified` / `fired` 兩旗標,群內每筆重算直到發訊(736-760) | ✔ |

註:`price <= first` 的檢查看的是**當筆價**而不是 `group.high`。這兩者等價 ——
`high` 只在 `price > high ≥ first` 時成長,所以「high 第一次超過 first」必定發生在某一筆
`price > first` 上;`levels` 隨 `high` 單調成長,不會漏。

**deque 剪裁正確性(逐條驗)**:
- `sweeps`:`while sweeps and sweeps[0] < window_start: popleft()`(747)。
  定義是**閉區間** `[s − 30, s]`,剪裁用**嚴格小於** → `ts == window_start` 的掃單留著。✔ 正確。
- `lookback`:`while len(lookback) >= 2 and lookback[1][0] <= cutoff: popleft()`(722)。
  停在「`lookback[0]` 是最後一個 ts ≤ cutoff 的點」。**刻意保留窗前最後一筆當漲幅基準**,
  不是每次重掃 list。✔ 正確,amortized O(1)。
- 兩條 deque 都只從左端剪、只從右端 append,**單向**。

**golden fixture 真實重放**(`bench_s1.py sweep`,直接跑線上 `SignalDetector`):

```
6715 2026-08-17:500 tick  事件 4/4  3.04 us/tick  lookback 終長 2  sweeps 1
1727 2026-08-05:920 tick  事件 5/5  3.08 us/tick  lookback 終長 2  sweeps 1
8103 2026-08-19:752 tick  事件 2/2  2.81 us/tick  lookback 終長 10 sweeps 1
```

與 `expected_prefix` 逐案例相等。**定義沒有漂。**

- **複雜度**:O(1) 攤提。**每 tick 成本 0.753 µs**(無條件付,含 `tick_secs` 0.281)。
- **狀態大小**:`_sweep_group`(一個 6 欄 dataclass,~120 B)+ `_sweeps`(研究實證
  每股票日僅 ~4.6 個合格掃單 → deque 幾乎恆空)+ `_lookback`(60 s 的 tick,
  開盤最熱 673 筆 × 88 B ≈ 59 KB)。
- **產量**:16–51 列/日;它是政策層**唯一**的觸發源(政策列 12–49/日)。
- **一個細節**:`0 價 / 0 量 tick 整段跳過`(712)在群比對**之前**,
  與研究 loader「分群前就濾掉」同語意,**不打斷群的相鄰性**。✔ 正確。

---

## 4. CDP 基準暖機與 `api.lock`;基準分發的正確性

### 4.1 鏈路

```
hub.request_basis(80 檔)  → _basis_jobs(**唯一的無界佇列**)
  → _basis_worker(單工序列)
      → _resolve_basis → engine.daily_bars(code, 25)
          → asyncio.to_thread(stock_source.fetch_daily_bars)   ← 共用預設 executor(20 workers)
              → TC4 `_req` → **`api.lock.acquire(timeout=lock_timeout)`**  ← tc4.py:562
                 與主圖回補 / K 線 route / overlay 共用同一條 stock session 的同一把鎖
      → compute_cdp(前一完成日 high/low/close) → _basis_cache[code] = (date, cdp)
      → _distribute(code)
      → await sleep(basis_gap_secs = 0.2)   ← 讓位給主圖回補
```

- **`api.lock` 是 per-session 的序列化點**:`fetch_daily_bars` 內部是輪詢
  `GETHISDATA`,每次 REQ 都取一次 `api.lock`;tc4-market-facts 實測 `tf=D` 單次 **1.1 s**。
  80 檔 × (1.1 s + 0.2 s gap) ≈ **104 s 最壞、~16 s 最佳(全 cache 命中)**。
- **`_fetch_outcome_bars`(13:40 T+1/T+2 回填)走同一把鎖** —— 這正是
  「開盤前起動不跑回填」(CLAUDE.md §4)的理由,**設計正確**。
- **0.2 s gap 是刻意的禮讓,不是效能缺陷,不要動。**

### 4.2 成功路徑零 log —— CDP 暖機完成時刻不可觀測

`grep 基準 logs/server-2026091*.log` = **0 命中**(三個交易日全查)。
`_resolve_basis` 只在**失敗**時 log(逾時 WARNING / 例外 exception / 無已完成日 K WARNING)。
所以:

- 「80 檔的 CDP 什麼時候全部備妥」**沒有任何紀錄**。
- 盤中重啟(09-11 實際發生過:00:36 起一台、09:05 再起一台)之後,
  CDP 有 ~16–104 s 是全站盲的,而**唯一的症狀是「那條規則這段時間都沒發」**。
- `_basis_jobs` 是全 hub **唯一的無界佇列**(`signal_hub.py:394`),
  現況上界 = 自選檔數 × 2 + 有限重試(`_BASIS_MAX_RETRIES = 2`),不會真的爆。

### 4.3 `_distribute` 的正確性

```python
# signal_hub.py:972-990
def _distribute(self, code):
    entry = self._basis_cache.get(code);  if entry is None: return
    basis_date, cdp = entry
    if basis_date != self._trade_date_fn(): logger.warning(...); return   # 日別 guard ✔
    for slot in self._slots.values():
        if slot.rule["kind"] != "cdp_cross": continue        # ← 只看 kind,不看 enabled
        slot.detector.set_basis(code, _filter_levels(cdp, slot.rule["cdp_levels"]))
```

- **日別 guard 在四個呼叫點之外再判一次** —— 正確(review A6(5));漏掉的失效樣態是
  「昨天的基準當今天用一整天」,零訊號。
- **`_filter_levels` 回 `None`(全空)時 `_eval_cdp` 的 `if not basis` 早退** —— 正確。
- **過濾只看 `kind` 不看 `enabled`**:一條**停用的** `cdp_cross` 規則仍會拿到 basis,
  於是每 tick 付滿 `_advance_rearm` + `_advance_sides`(實測 **4.62 µs vs 2.76 µs**,+67%),
  而 `_eval_cdp` 在 399 行才因 `enabled` 回 `[]`。純死工。
  現況 prod 的 cdp 規則是 enabled,所以這條**今天沒有損失**;它是「使用者在規則視窗
  按了停用之後,效能反而沒省到」的陷阱。
- `set_basis` 每次以 dict comprehension 重建 `_side` 整表(222-223)——
  O(全表);盤前 sweep 80 檔 × 400 筆 = 32k 次比較,**一天一次 < 10 ms,不要動**。

---

## 5. 記憶體:每檔 × 每規則的狀態大小

直接量(`sys.getsizeof`,含 deque block overhead):**窗一筆 = 96 B**
(3-tuple 64 + float 24 + deque block 8.4);lookback 一筆 = 88 B(2-tuple 56 + float 24 + 8)。

`tracemalloc` 實測單顆 detector 單檔:

| 情境 | 窗長 | lookback | 單顆單檔 |
|---|---|---|---|
| 全日 median 0.116 tick/s | 35 | 8 | **8.5 KB** |
| 開盤 p90 5.9 tick/s | 1,771 | 355 | **196 KB** |
| 開盤 max 11.2 tick/s | 3,361 | 673 | **244 KB** |

**以 09-11 真實資料算 09:05 當下的全系統峰值**(`bench_agg.py`;
窗長 = 該檔 09:00 以來全部 tick,因為 `surge_window_secs = 300`):

```
全自選窗內總筆數(單顆 detector)= 49,368 筆
× 7 顆 detector                = 345,576 筆
→ 窗:345,576 × 96 B  = 33.2 MB
→ lookback(60 s ≈ 1/5)≈ 69,100 × 88 B = 6.1 MB
→ 合計 ≈ 39 MB(峰值,約 09:05);合併成單顆後 ≈ 5.6 MB
```

非窗狀態(`_side` / `_suppressed` / `_cooldown` / `_touch` / `_latch` / `_pullback` /
`_sweep_group` / `_sweeps`)每檔每顆 ≈ 1.5 KB → 80 檔 × 7 顆 ≈ **840 KB**,可忽略。

**150 檔上限下的外推**:若 150 檔都有 80 檔的平均熱度,峰值窗 ≈ 73 MB。
仍不是危險量級,但**它是 7 倍於必要值**,而且成長軸是「規則數 × 自選檔數 × 行情熱度」
三者相乘 —— `MAX_RULES = 30` 的情況下就是 39 MB × 30/7 = **167 MB**。

---

## 6. Findings

> 嚴重度是以「這是一個要下實單的系統」為準繩定的。
> 頻率標註:`每 tick`(prod 開盤 164.6/s)、`每則 quote`(未知,推估 330–820/s)、
> `每則訊號`(~700/日)、`每日一次`。

### F-01 訊號層零延遲記帳:`now − tick.time` 兩個值都在手上,從來沒有人相減(critical,可觀測性)

`SignalEvent`(88-105)只有 `time` / `time_key` = **tick 時刻**;
`_emit` 寫進 jsonl 的列(實證 09-11 政策列全 28 欄)**沒有任何伺服器側時刻**。
而 `evaluate` 的第一行就拿到了 `now = self._now_fn()`(301),`key = tick.time`(307)。

後果:**影子期四週對帳完全無法區分「這個訊號沒有價值」與「這個訊號晚了 2 秒」。**
對一個下一步要下實單的系統,這是這一層最重要的缺口 —— 而且它是永久性的:
歷史 jsonl 已經沒有這個欄,補不回來。

**反向證據(證明這個量不是零)**:09-11 有 4 則 `vol_burst` 的 `time = 13:30:00`,
而 `_in_session` 的右界是 13:30 **end-exclusive**(牆鐘)——
**tick 時刻領先牆鐘**才可能發生。兩把時鐘的偏差已經大到會改變 gate 結果,卻沒有被量。

**修法**:`SignalEvent` 加一欄 `emitted_mono`(或由 hub 在 `_emit` 補
`"emitted_at": _clock_key(now)`),jsonl **只加欄不改欄**(W1 契約允許)。
每分鐘一行 INFO 印 `now − tick_secs(time_key)` 的 p50/p95/p99。

---

### F-02 一規則一 detector:73% 的 per-tick 成本與 6/7 的記憶體是結構性死工(high,熱路徑)

`_make_slot`(`signal_hub.py:455-463`)為每條規則建一顆完整 `SignalDetector`,
`enabled = frozenset({rule["kind"]})`;`evaluate` 卻無條件跑掃單簇軸、窗維護、
回檔狀態機、鎖板 latch。

**實測**:
- 死工 = **2.76 µs/tick/顆**(窗長 35 / 1,771 / 3,361 三點量到同一個值 —— 死工與窗長無關)。
- prod 7 顆 = **24.63 µs/tick**(窗長 35)vs 單顆六 kind 全開 = **6.65 µs/tick**。
  **把七顆合成一顆、六個 kind 全開,比現在快 3.7 倍。**
- 記憶體:09:05 峰值 39 MB → 5.6 MB。

**prod 七條規則只有兩種窗長**(surge 300 ×4、sweep lookback 60),去重率 7 → 2。

**修法**(架構級,**要 user 拍板**,因為它推翻 signal-rules design 的
「一條規則 = 一顆未改動的 detector」):拆兩層 ——
(a) per-code **市場狀態**(窗 + running sum + lookback + sweep group + prev + side),
    以 `window_secs` 去重、每 tick 每檔算一次;
(b) per-rule **門檻判定 + cooldown/touch/latch**,吃 (a) 的結果只做比較。
這同時吃掉 F-03(`sum()` 只維護一份)、F-04(`now()` 只叫一次)、F-08(`tick_secs` 只解析一次)。

**契約風險**:掃單簇定義由 `tests/fixtures/sweep_cluster_golden.json` 釘住
(線上必須與 `expected_prefix` **集合相等**)—— 重構後這三支必須仍綠;
另有 `tests/live/test_signal_state.py` 全套。

---

### F-03 `_eval_volume` 的 `sum()` 是全庫唯一成本隨單檔 tick 率線性放大的 per-tick 運算(high,熱路徑)

`signal_state.py:658`。實測 **27–31 ns/筆**,線性到 18,000 筆:
窗長 3,368 → **94.9 µs**;18,000 → 484 µs。

**但要誠實**:`min_elapsed_min = 15` 的閘在 `sum()` **之前**(651),
所以 09:00–09:15 這段最密的 tick **完全沒付**(實測 09:02 起、窗長 3,361 時
vol_burst 只 3.28 µs)。事件分佈也印證:09h 只有 5 則 vol_burst。
**上一輪報告的「開盤 13.8 ms/秒」應予修正。**

實際暴露面是 09:15 之後的熱門股:窗長 ~600–2,000 → 17–55 µs/tick,
單檔最壞 1.43 ms/s 的 loop 佔用。**今天不痛,但它是 F-06 那顆炸彈的引信。**

**修法**:窗改成 `(deque, running_sum)`,`append` 時 `+= qty`、`popleft` 時 `-= qty`。
`evaluate`(318-323)是**唯一**的 append/popleft 點,改動面積 = 一個 `self._window_qty: dict[str, int]`。
**等價性**:`qty` 是 `int`,整數加減精確可逆,無浮點累積誤差;
`_eval_volume` 只在 `evaluate` 剪裁完之後被呼叫,兩者恆一致。O(窗長) → O(1)。

---

### F-04 `evaluate_book` 的 `_clock_key` 每則 quote × 每條規則無條件付 strftime(high,熱路徑)

`signal_state.py:348`。實測 `_clock_key` = **1.765 µs**,佔 `evaluate_book` 總成本
2.344 µs 的 **75%**;7 顆 = **16.0 µs/quote**。
產出:`limit_open` 實測 **0–9 則/日**(09-01~09-11)。

`on_book` 是 `stock_engine.py:1366` **無條件**對每一則 watched quote 呼叫的
(不判簿是否真的變了)。quote 頻率量不出來(§2.3),推估比 tick 高 2–5 倍
→ 這條的總量**可能比 F-03 還大**。

**修法**:§3.5b 的 latch 旗標短路(等價性已證),`evaluate_book` 2.344 → ~0.06 µs;
或把 `key` 改成 lazy(只在 `_limit_event` 要建事件時才算)。零契約風險、零行為改變。
**這是本區塊投報率最高的一筆改動:三行、砍 97.5%。**

---

### F-05 `vol_burst` 的基準是一把在一天之內單調變鬆的尺(high,quant-gap)

`avg_per_min = ctx.day_volume / elapsed_min`(654),
`ctx.day_volume = tick.cum_vol` = 自 09:00 的累積量,`elapsed_min` = 自 09:00 的分鐘數。
這是一個**自 09:00 起的累積平均**,不是平穩基準:
開盤集合競價那一筆巨量在 09:15 佔分母很大比重、到 13:00 已被稀釋。

**實證**(09-10 + 09-11 合計,kind × 小時):

```
tick 率 :  09h 最高(開盤 5 分鐘 = 全日 15%)  →  13h 最低
vol_burst:  09h  5     10h 10    11h 14    12h 31    13h 26     ← 完全相反
```

同一組參數在早上幾乎不發、下午一小時發 31 則。
**對影子期對帳來說這是系統性偏差**:vol_burst 的樣本被時間加權過,
「爆量訊號沒用」與「爆量訊號的門檻在有用的時段太嚴」分不開。

**修法**(要 user 拍板,是**策略決定**不是效能決定):
把分母改成固定回看窗的均量(例:前 20 分鐘)或前 N 日同時段均量。
**不要**只調 `ratio` —— 那只是把偏差整體平移。

---

### F-06 `MAX_RULES 30` × `window_secs ≤ 3600`:從規則視窗按得出來的 event-loop stall(high,風險)

`signal_rules.py:54, 74-79`:`vol_burst.window_secs` 值域 `(10, 3600)`,規則上限 30 條。
`signal_rules.py:53` 的註解自己講對了一半(「熱路徑是 per-tick N × evaluate」),
但**只擋了規則數,沒擋單條規則的成本**。

**推估(以實測 27–31 ns/筆線性外推)**:

| tick 率 | window_secs=3600 的窗長 | 單條規則 sum() | 30 條 |
|---|---|---|---|
| 1.03/s(開盤 median) | 3,708 | 104 µs/tick | 3.1 ms/tick |
| 5.9/s(開盤 p90) | 21,240 | 595 µs/tick | 17.8 ms/tick |
| 11.2/s(開盤 max) | 40,320 | 1,129 µs/tick | **33.9 ms/tick** |

33.9 ms/tick **單筆就超過 Windows 15.6 ms timer 精度兩倍**,而同一條 loop 還要送 WS、
回 REST、處理 TC4 回應、**以及在 §7 階段之後可能要處理下單回報**。
記憶體同時爆:40,320 × 96 B × 30 = 116 MB/檔。

**修法**:**做 F-03 的 running sum,這個問題直接消失**(成本與窗長無關)。
不做 F-03 才需要收窄 `PARAM_SPECS`,而那是跨檔契約
(`tests/fixtures/signal_param_specs.json` + 前端 `signal-params.ts`,CLAUDE.md §4)。
**建議走 F-03,不動契約。**

---

### F-07 收盤撮合 13:30:00 那一筆會偷過 session gate 並產生假 `vol_burst`(medium,正確性 + 零訊號)

**實證**(09-11):

```
2344 vol_burst ratio=4.0  id=...-13:30:00.000
2408 vol_burst ratio=3.5
2327 vol_burst ratio=3.5
3037 vol_burst ratio=3.4
```

機制:`_in_session` 用**牆鐘**(`366-367`,`< 13:30` end-exclusive),
`SignalEvent.time` 用 **tick 時刻**;試撮窗是 `13:25:00–13:30:00` end-exclusive
(`stock_models.py:28-31`)所以 13:30:00.000 的收盤撮合那筆**不是** trial、`ingest` 收下。
只要 TC4 的 tick 時刻略微領先本機牆鐘,這筆巨量就會進 300 s 窗並觸發 vol_burst。

**零訊號的部分**:09-10 完全沒有這種列,09-11 有 4 則 —— **同一個事件在不同日子會隨機
出現或不出現**,取決於兩個時鐘的瞬時偏差。這對四週影子期的統計是一個不可重現的雜訊源。
而且這 4 則吃掉了該檔 1,800 s 的 vol_burst cooldown(跨不到隔天,影響有限)。

**修法**:tick 路的 session gate 改成「同時看 tick 時刻」
(`tick_secs(key) < 13:30:00` 一起判),或明確把收盤撮合那一筆排除。
**要 user 拍板**:收盤撮合的量是不是一個有效訊號,是策略問題。

---

### F-08 每顆 detector 各自叫 `now()` / `_mono()` / `tick_secs()`(medium,熱路徑)

`signal_state.py:301, 305`(tick 路)、`345, 347`(簿路)、`714`(`tick_secs`)。
7 顆 × (0.064 + 0.202 + 0.281) = **3.8 µs/tick**,簿路再 7 × 0.266 = 1.9 µs/quote。

除了浪費,還有一個語意瑕疵:**七顆 detector 的 cooldown 軸各差幾微秒**,
而它們在語意上本來就該是同一個時刻(同一則 quote)。

**修法**:hub 在 `on_tick` / `on_book` 算一次 `now` / `mono` / `key` / `secs`,
經參數傳進 `evaluate(..., now=, mono=, key=)`。
**注意**:`now_fn` 注入是測試與盤後重放的唯一入口(`signal_hub.py:457` 明文
「漏帶 `now_fn` 的那一顆會偷用真實時鐘」),簽名改動要一起改 `_make_slot`
與所有 detector 單元測試。F-02 做完後自然消失。

---

### F-09 `_distribute` 只看 `kind` 不看 `enabled`:停用的 CDP 規則仍付全額狀態推進(medium,熱路徑)

`signal_hub.py:985-988`。停用的 cdp 規則實測死工 **4.62 µs/tick vs 2.76 µs**(+67%),
其中 1.66 µs 是 `_advance_rearm`(5 線)+ `_advance_sides`(5 線 + 2 個 list 配置)。

prod 現況 cdp 規則是 enabled,所以**今天沒有損失**。
它是一個陷阱:使用者在規則視窗按「停用」之後,以為省下了成本,實際沒有 ——
而唯一的症狀是 CPU 曲線沒有變化,零錯誤訊號。

**修法**:`if slot.rule["kind"] != "cdp_cross" or not slot.enabled: continue`。
但要留意 design R2 的語意:停用期間狀態照推進是刻意的 ——
所以正確的修法是**在 `_eval_cdp` 開頭就早退**,而不是不分發 basis
(不分發會讓「重開後首筆假發一則穿越」的 review C-1 問題回來)。
安全做法:F-02 拆層後,per-code 市場狀態只算一份,問題消失。

---

### F-10 三條種子規則的 `rule_id` 每次啟動都變,`_event_id` 的決定性保證在 prod 是破的(medium,正確性 + 零訊號)

`_event_id`(`signal_hub.py:1688-1695`)的 docstring 寫著
「**決定性鍵:不依賴 process 記憶 → 重啟後同一事件同 id**」。

**實證(`data/signals/*.jsonl` 逐日統計 rule_id)**:

```
09-10: r-1785975520-00{0,1,2,3}(v1 檔上的四條,穩定)
     + r-1788965322-00{4,5,6} ← epoch 2026-09-09 22:48:42(那一台)
     + r-1789002367-00{4,5,6} ← epoch 2026-09-10 09:06:07(重啟後那一台)
09-11: + r-1789058168-00{4,5,6} ← 00:36:08 起的那台
     + r-1789088717-00{4,5,6} ← 09:05:17 重啟後那台
```

根因:磁碟上的 `data/signal_rules.json` 仍是 **v1**,`load_rules` **載入時不回寫**
(刻意的回退窗,`signal_rules.py:513-514`),於是 `_migrate_v2` / `_migrate_v3` 每次啟動
都用 `epoch = int(time.time())` 重新配 id 給
**surge_pullback ×2(-004/-005)與 sweep_cluster(-006)**。

後果:
1. `_event_id` 含 `rule_id` → **盤中重啟後同一事件不再同 id**,前端去重失效。
2. **政策列的 id**(`<日>-<規則id>-<代號>-policy-<標記>-<時刻鍵>`,CLAUDE.md §4 契約)
   帶著一個每天都不一樣的段 → **四週影子期的對帳鍵不穩定**,
   而掃單簇正是政策層唯一的觸發源。
3. 跨日以 `rule_id` 聚合 surge_pullback / sweep_cluster 的分析全部做不到。

零錯誤訊號:畫面、log、測試都不會報。**只要在規則視窗編輯任何一條規則
(觸發 `upsert_rule` → `save_rules` 落 v4),這個問題就永久消失** —— 也就是說
它是「從來沒有人動過規則」這個事實的副作用。

---

### F-11 盤中重啟 = 偵測器狀態全失,而 jsonl 沒有斷點記號(medium,正確性)

`reset_day` / 建構子把所有狀態清空,而回補 tick **刻意不重放進 detector**
(`apply_backfill` 不經 `on_tick`,SC-5)。重啟後的具體後果,逐 kind:

| kind | 重啟後 |
|---|---|
| surge / crash / vol_burst / pullback | 窗空 → **靜默 300 s**(門檻永遠達不到) |
| cdp_cross | `_side` 空 → 首筆退回 `prev` 推定;`_suppressed` 空 → **已抑制的線可以馬上再發一次** |
| limit_lock | `_latch` 空 → 已鎖住的檔在第一筆成交**重發一則 `limit_lock`** |
| sweep_cluster | `_sweeps` / `_lookback` 空 → 60 s 漲幅基準 = 0 → **靜默 ~60 s** |
| 全部 | `_touch` 歸零 → 前端「第 n 次」重新從 1 算 |

09-11 實際發生過(09:05:17 重啟),jsonl 裡**看不出任何痕跡**。
影子期對帳時,那一天的樣本與其他天不可比,而沒有人會知道。

**修法**:hub 啟動時往當日 jsonl 寫一列 `{"kind":"_restart", ...}` ——
**但 W1 契約明文「不新增列型」**(離線讀者逐列讀 `s["kind"]` 無防禦)。
所以要嘛改成 log 一行固定字串供 `grep`,要嘛先改離線讀者。**要 user 拍板。**

---

### F-12 `_eval_pullback` / `_eval_limit_tick` 的 `enabled` 檢查在函式**內部**,與 `_eval_surge` / `_eval_volume` 不一致(low-medium,架構)

`_eval_surge`(523)與 `_eval_volume`(647)第一行就檢查 `enabled`;
`_eval_pullback` 在 **615**、`_eval_limit_tick` 在 **835**(`_limit_event` 內)。
兩種寫法都「對」(design R2 允許狀態推進無條件),但**同一個檔裡四種 kind 兩種寫法**,
讀者無法從呼叫點看出哪一條會早退 —— 這正是 F-02 的量級被低估的原因。

成本:0.258 + 0.375 = 0.633 µs/tick/顆 × 7 = 4.4 µs/tick(prod 有 2 條 pullback、
1 條 limit_lock 是「真的要跑」,其餘 4–6 顆是死工)。

**修法**:把「狀態推進」與「事件產出」在**函式簽名層**分開
(`advance_*(…) -> State` / `emit_*(state, enabled) -> Event | None`),
`enabled` 只出現在後者。F-02 拆兩層時自然做到。

---

### F-13 `_eval_volume` 每 tick 新配置一個 `datetime`(low,熱路徑)

`signal_state.py:649`:`open_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)`
+ `_mono(open_dt)`(timedelta + total_seconds)。當日常數,每 tick 重算。
成本 ~0.3 µs/tick(僅在 `vol_burst` 那一顆)。快取成 `(date, mono_of_open)` 即可。
**量級小,只在 F-02/F-03 動到這個函式時順手收。**

---

### F-14 `_advance_rearm` 的 gap 用當筆價的檔距而非線價的檔距(low,正確性)

`signal_state.py:396`:`gap = cdp_rearm_ticks × tick_size_milli(price)`。
價格在 10/50/100/500/1000 元的檔距分界附近來回時,gap 會跳 5 倍
(例:99.9 元 → 0.5 元;100.5 元 → 2.5 元),駐留計時因此可能被反覆歸零。
影響 = 「重武裝比設定的 300 s 慢」,零錯誤訊號,量級小。
線價是固定的,用 `tick_size_milli(basis[name])` 才是「離這條線 N 個檔」的本意。
**但改它會動到 CDP 的發訊集合 → 要紅先行 + 影子期對照,不建議在效能批次裡順手改。**

---

### F-15 `_sweeps` 的剪裁只在「本群已合格」時發生(low,已驗證無害)

`signal_state.py:740-748`:`while sweeps[0] < window_start` 的剪裁在
`if not group.qualified: … return []` 之後。
若一檔早上出現 2 個掃單、之後整天沒有新的合格掃單,deque 會留著那 2 個 float 到收盤。
**不影響正確性**(`n_sweeps` 只在剪裁**之後**被讀),記憶體可忽略
(tc4-market-facts 實證:1,883 股票日 8,757 個合格掃單 = **每股票日 4.6 個**)。
**記帳用,不要動。**

### F-16 不要為這一層引入任何新套件(反向 finding)

- `numpy`:per-call overhead ~1–5 µs > 整個 `_eval_surge`(0.081–0.3 µs)。
  上一輪已在 `stock_state._apply`(1.96 µs/tick)駁回過同一個提案,這裡形狀更不利
  (每 tick 一個標量、分支重、狀態跨 tick 累積)。
- `polars` / `pandas`:無立足點。
- `numba` / `Cython` / Rust:狀態機是 dict/deque 物件圖,JIT 沒得發揮;
  Windows 編譯鏈與 `dependencies = []` 的 stdlib-only 哲學衝突;
  80 檔 × 7 規則遠未到需要它的量級。
- `orjson`:這一層不碰序列化(那是 hub 的事),且 jsonl 寫入有三條硬契約禁止換。
- `uvloop`:**不支援 Windows**,本專案後端必須 Windows + TC4 常駐。

**純 Python 的 F-02 + F-03 + F-04 就有 3.7 倍(tick 路)與 40 倍(簿路),
而且零新相依、零契約。** 這一層不需要任何套件。

---

## 7. 改造順序(每一步的量測判準)

| # | 做什麼 | 為什麼排這裡 | 量測判準 | 回退 |
|---|---|---|---|---|
| 1 | **加儀器**:`on_tick` / `on_book` 耗時 histogram(`perf_counter_ns` + 固定桶)、quote 與 tick 計數、`now − tick_secs(time_key)` 的 feed 延遲分佈;每分鐘一行 INFO | **先量後改**;§2.3 的 quote:tick 比是唯一量不出來的一格,而它決定 F-04 的優先序 | 盤後 `grep` 拿到 p50/p95/p99 + 每秒次數;quote:tick 比第一次有數字;feed 延遲 p99 有數字 | 純新增 log,移掉即可 |
| 2 | **jsonl 每列加 `emitted_at`**(只加欄,W1 允許) | F-01;影子期還在跑,**每晚一天就永久少一天的資料** | 次日 jsonl 每列有 `emitted_at`;`tests/server/test_signal_outcome.py` 的 byte 比對仍綠(回填只碰被補的列) | 移欄;舊列缺欄讀者視為 None |
| 3 | **`evaluate_book` latch 短路**(`self._latched: set[str]`) | 等價性已證(§3.5b)、三行、零契約、投報率最高 | `bench_parts.py` 的「evaluate_book(latch 全 False)」2.344 → ≤ 0.1 µs;新增紅先行:latch True 時仍發 `limit_open`;`tests/live/test_signal_state.py` 全綠 | 單一 `if` 移除 |
| 4 | **`vol_burst` running sum** | F-03;同時拆掉 F-06 的引信 | `bench_s1.py kind` 的 vol_burst 那一列在窗長 35 / 1,771 / 3,361 三點差 **< 1 µs**(現況 4.49 / 61.56 / 97.94);新增 property test:`running_sum == sum(window)` 逐 tick;既有 vol_burst 案全綠 | 一個 dict 移除 |
| 5 | **收盤撮合 tick 的 session gate**(F-07) | 影子期資料品質;要 user 先拍板「13:30:00 那筆算不算」 | 次日 jsonl 無 `time >= 13:30:00` 的列;新增測試:tick 時刻 13:30:00 + 牆鐘 13:29:59 → 零事件 | 單一條件移除 |
| 6 | **把 `data/signal_rules.json` 落成 v4**(F-10) | 一次 `upsert` 即可;修好之後 `_event_id` 的決定性保證才成立 | `data/signal_rules.json` 的 `_cache_version == 4`;重啟兩次後 jsonl 的 rule_id 集合完全相同 | 檔案有備份即可 |
| 7 | **detector 拆兩層**(F-02 + F-08 + F-09 + F-12) | 要 user 拍板(推翻 signal-rules design 核心決定);前五步做完它的收益才乾淨可量 | 7 顆 24.63 → **≤ 8 µs/tick**;窗總量 ÷ 7(側車 `sum(len(w) …)`);**golden fixture 三案仍 4/4 5/5 2/2**;全套訊號測試綠;**同一份 tick 流改前改後重放,jsonl 事件集合逐列相同** | 分支回退;golden 是安全網 |
| 8 | **`vol_burst` 基準改固定回看窗**(F-05) | 策略決定,要 user 拍板;放最後因為它會**改變事件集合**,與 7 的「集合不變」判準衝突 | 事件的 kind × 小時分佈不再單調偏向下午(以 09-01~09-11 的歷史 tick 重放對照) | 參數旗標可切回舊式 |
| 9 | **重啟斷點記號**(F-11) | 需要先決定要不要改離線讀者(W1「不新增列型」) | 重啟後 log 有固定字串可 grep;或 jsonl 有斷點列且研究讀者不炸 | 移除 |
| 10 | **`_advance_rearm` 用線價檔距**(F-14) | 會改變 CDP 發訊集合 → 要紅先行 + 影子期對照,不能混進效能批 | 以歷史 tick 重放,CDP 事件差集逐筆人工核 | 分支回退 |

---

## 8. 不要動的地方(已經寫對了)

1. **掃單簇的兩條滑動窗**(`signal_state.py:718-748`):
   `lookback` 的 `while len(lookback) >= 2 and lookback[1][0] <= cutoff` **刻意保留窗前最後一筆**
   當 60 s 漲幅基準;`sweeps` 的 `< window_start`(嚴格小於)對上閉區間 `[s−30, s]` 定義。
   兩條都是 amortized O(1)、單向剪裁,實測 0.753 µs/tick、golden fixture 三案全中。
   **上一輪的判斷成立,本輪逐條複驗確認。不要動。**
2. **`_advance_sides` 的「線上點保留上一側別」與混向 WARNING**(463-510):
   碰線點透明讓「逐 tick 走過線價」算一次穿越、「貼線來回」不算;
   混向不變式破掉時以 `_sign(price − prev)` 保單一方向、`price == prev` 時**兩邊都不發**
   (寧可少發,不擲硬幣)。這是難寫對的一段,不要動。
3. **`_eval_pullback` 的 O(1) 重武裝基線**(`rearm_base`,596-604):
   review F-02 從「每 tick 掃窗」改成「發訊當下掃一次存下」,
   且 tie 邊界(同 mono 批次)與舊掃描語意逐案例等價。註解把等價性寫清楚了。不要動。
4. **`_locked_up` / `_locked_down` 的複合簽名**(813-823):
   第三項(市價佇列 `price == 0` 或最佳限價買 = 漲停)排除「首攻吃光賣盤」的假陽性。
   這是 TC4 鎖停行為實測換來的,不要動。
5. **`_change_pct` 單源**(151-159):surge 偵測與回檔武裝共用同一支,
   「沿 surge 偵測同式」由此成為機驗事實而非註解對齊。不要拆。
6. **`(peak − price) × 100.0 / peak`**(607)而不是 `/peak*100`:
   讓「恰好整除」的門檻值浮點精確(邊界含)。不要「順手簡化」。
7. **CDP 基準 worker 的 0.2 s 逐檔 gap**(`signal_hub.py:834-838`):
   刻意讓位給共用 `api.lock` 的主圖回補與 K 線 route,不是效能缺陷。不要動。
8. **`set_basis` 一律清該檔側別**(222-223):擋的是「盲窗之後同線價回來」的假穿越
   (review C-1)。O(全表)但一天一次 < 10 ms。不要為了複雜度改它。
9. **毫元整數運算 / `tick_size_milli`**:上一輪已駁回改 float。Decimal 是截斷、float 是
   banker's rounding,tick 邊界會分岔。不要碰。
10. **「狀態推進無條件、`enabled` 只 gate 事件產出」這個語意本身**(design R2):
    要改的是它被複製 7 份,不是語意。

---

## 9. 開放問題

1. **`on_book` 的真實頻率是多少?**(quote:tick 比)——
   決定 F-04 是 high 還是 critical。`logs/` 只記 tick 數,沒有 quote 計數。步驟 1 的探針就是為它。
2. **detector 拆兩層要不要做?** 它推翻 signal-rules design 的
   「一條規則 = 一顆未改動的 detector」明文決定。收益 3.7× CPU、7× 記憶體,
   並讓 `MAX_RULES = 30` 第一次有意義。**方向性抉擇,要 user 拍板。**
3. **收盤撮合 13:30:00 那一筆算不算訊號?**(F-07)—— 策略問題。
4. **`vol_burst` 的基準要不要換?**(F-05)—— 策略問題;換了影子期的 vol_burst 樣本要重跑。
5. **重啟斷點要不要進 jsonl?**(F-11)—— 撞 W1「不新增列型」契約,要先決定改不改離線讀者。
6. **`data/signal_rules.json` 何時落成 v4?**(F-10)——
   落檔之後 v3→v4 的「cdp_cross / vol_burst 通知翻 false」就不再每次啟動重跑,
   使用者才可能持久地把通知開回來。這同時是行為決定,不只是技術債。
7. **訊號要不要擴到期貨 / 夜盤?** `_in_session` 硬編 09:00–13:30(63-64)且是第一道 gate
   (不在窗內連狀態都不推進)。要擴就得先把 session 參數化。
