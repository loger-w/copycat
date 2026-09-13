# Q1 — 量化系統落差分析(copycat)

> 掃描基準:`master` @ `caca1d30`(2026-09-13)。所有行號以該版為準,漂移後以符號名重找。
> 本報告**跳出效能**,用「量化交易系統的標準架構」對照這套系統缺什麼。
> 效能面的 finding 留給其他分片,本報告只在「補落差會不會撞到效能改造」一節交叉。

---

## 0. 一句話結論

**copycat 現在是一套非常成熟的「即時看盤 + 手動下單」系統,但它不是量化交易系統 —— 因為它的訊號產生路徑與它的驗證路徑是三份不同的 code,而且真正在用的那一份不在版本控制裡。**

具體:

| 量化系統標準構件 | copycat 現況 | 落差等級 |
|---|---|---|
| 單一策略核心(live / backtest 共用) | **三份獨立實作**(`engine/`、`live/signal_state.py`、repo 外 `combo_events.py`) | **critical** |
| 事件時間語意一致 | 六種 kind 裡**只有 1 種**用交易所時刻,其餘 5 種用本機牆鐘 | **critical** |
| 重啟恢復 | 訊號狀態全失且回補 tick **刻意不重放**進 detector | **critical** |
| 延遲可觀測性 | tick 抵達時刻**根本沒被記下來**;全庫零 `perf_counter` | high |
| 帳戶級風控 | 只有單筆閘,且預設「不限」 | high |
| 下單冪等 | 只有平倉有 inflight 去重;新單零 dedup、審計無 request_id | high |
| 資料清洗層 | 無;0 價判定散在 7 處各寫一次 | high |
| 參數可重現性 | 訊號列只帶 `rule_id`/`rule_name`,不帶生效門檻;規則檔就地覆寫無歷史 | high |
| lookahead 防護 | 純靠註解 + 人工紀律,零機械閘 | medium |
| 交易日誌 / 績效歸因 | 無(靠 repo 外手動對帳) | medium |

反過來,**已經做得比多數自建量化系統好**的地方也不少(§8「不要動」),尤其是:
`backtest/simulate.py` 的悲觀成交時序、下單審計的 shield + 「結果未知勿重送」、
訊號 id 的決定性鍵、以及整套 CLAUDE.md §4 跨檔契約 + golden fixture parity 機制 ——
**那套 parity 機制正是補齊上面落差時該沿用的工具,不要繞過它另造一套。**

---

## 1. 架構地圖:三條互不相通的「策略」路徑

```
                     ┌──────────────────────────────────────────────┐
                     │  A. repo 內離線路徑(replay)                 │
                     │  data/1k/*.json ─► copycat/data/store.py     │
                     │      └► replay/runner.py                     │
                     │            ├► engine/lock_quality.LockTracker│
                     │            └► engine/t1_open.T1Tracker       │
                     │      └► replay/report.py ─► out/<wl>/…       │
                     │      └► replay/validate.py(golden gate)     │
                     │  消費者:CLI `python -m copycat replay`       │
                     │  **server/ 零 import**(grep 實證)            │
                     └──────────────────────────────────────────────┘

                     ┌──────────────────────────────────────────────┐
                     │  B. repo 內線上路徑(live)                   │
                     │  TC4 ZMQ ─► live/tc4.py::_listen_loop(thread)│
                     │      └► call_soon_threadsafe                 │
                     │      └► server/stock_engine.py::_handle_quote│
                     │            ├► live/stock_state.StockDayState │
                     │            └► server/signal_hub.SignalHub    │
                     │                 └► live/signal_state.        │
                     │                      SignalDetector × N 規則 │
                     │                 └► server/signal_policy.py   │
                     │      └► WS publish / data/signals/*.jsonl    │
                     │  **與 A 零共用 code**                         │
                     └──────────────────────────────────────────────┘

                     ┌──────────────────────────────────────────────┐
                     │  C. repo 外研究路徑(真正決定政策的那份)     │
                     │  C:\Users\USER\Documents\copycat-trading-    │
                     │  review\scripts\ ── 48 支 .py / 7,306 LOC    │
                     │    combo_events.py::find_sweeps / group_feats│
                     │    combo_search.py / combo_eval.py / bt.py … │
                     │  data/ 971 MB(ticks/、combo/、*.csv)        │
                     │  **not a git repository**(實測 git 回 fatal)│
                     │  唯一與 repo 的接點:                          │
                     │    tests/fixtures/record_sweep_cluster_      │
                     │    golden.py(手跑,逐字抄 combo_events.py)  │
                     └──────────────────────────────────────────────┘
```

**資料流(線上,量級標註)**

| 段 | 頻率 | 說明 |
|---|---|---|
| ZMQ recv → `handle_raw` | 開盤 ~數百則/s(150 檔自選) | `tc4.py:1243` 單執行緒 recv,`_last_msg` 記時鐘 |
| `call_soon_threadsafe` → `_handle_quote` | 同上 | `stock_engine.py:1150` |
| `state.ingest` + `_apply` | 同上(試撮 / 重複量被短路) | `stock_state.py:189` 起 |
| `signal_hub.on_tick` | 同上 × **每條規則**(上限 30) | `stock_engine.py:1352` → `signal_hub.py:607` |
| `_eval_sweep` 等六軸 | 同上 | `signal_state.py:306` 起 |
| 掃單簇命中 → `_emit_policies` | 一天數十顆(09-11 實錄 686 列/日,含 raw+policy) | `signal_hub.py:1042` |
| `policy_quotes(peers)` | **只在掃單簇事件時** | `stock_engine.py:763` |
| jsonl 落檔 | 有界佇列 + worker thread | `signal_hub.py:1186` |
| 下單 | 人工,一天個位數 | `capital/client.py:865` |

---

## 2. 問題 1:回測與實盤的一致性(最致命)

### 2.1 證據:`copycat/engine/` 只有一個消費者,而它不是 server

```
$ grep -rn "copycat.engine\|LockTracker\|T1Tracker" --include=*.py .
./copycat/engine/lock_quality.py:62:class LockTracker:
./copycat/engine/t1_open.py:68:class T1Tracker:
./copycat/replay/runner.py:14:from copycat.engine.lock_quality import LockTracker
./copycat/replay/runner.py:15:from copycat.engine.t1_open import EventContext, T1Tracker, gap_bucket_label
(tests/ 另兩支)
```

`copycat/engine/__init__.py` 的 docstring 寫著:

```python
"""評分引擎 — 逐 bar 餵入的狀態機,零 IO,無 lookahead 為結構保證."""
```

形狀完全正確(零 IO、狀態機、可注入 config),**但 `server/` 一次都沒有 import 它**。
線上跑的六種訊號在 `live/signal_state.py`(38,600 bytes)+ `server/signal_hub.py`(86,889 bytes)
+ `server/signal_policy.py`,與 `engine/` 零交集。

### 2.2 更嚴重:現在線上跑的政策,原始碼在 repo 外且無版本控制

`signal_policy.py` 的 module docstring 自己寫明:

```python
"""…定義沿研究 `combo_events.py::group_feats`(`_up3` / `_leader` /
`_locked_before`)與 HANDOFF §8 拍板…"""
```

`tests/fixtures/record_sweep_cluster_golden.py` 更明確:

```python
- **研究真值**(逐字沿 `C:\Users\USER\Documents\copycat-trading-review\scripts\combo_events.py`
  的 `find_sweeps` + 主迴圈 sweepc 段)
TICKS_ROOT = Path(r"C:/Users/USER/Documents/copycat-trading-review/data/ticks")
```

實測那個目錄:

```
$ cd /c/Users/USER/Documents/copycat-trading-review && git rev-parse --is-inside-work-tree
fatal: not a git repository (or any of the parent directories): .git
$ ls scripts/*.py | wc -l   → 48
$ wc -l scripts/*.py | tail -1 → 7306 total
$ du -sh data → 971M
```

**含義**:四週影子期結束要決定 P/B-a/B-b/S 是否接實單時,拿來對照的研究基準是一份
無版本控制、與 repo 無自動關聯、隨時可被就地改掉的 7,306 行腳本 + 971 MB 資料。
這在量化系統是最致命的單點 —— 因為它讓「我當初測到 +X 元/筆」這句話不可驗證。

### 2.3 現有的唯一 parity 機制,涵蓋率 1/6

`tests/fixtures/sweep_cluster_golden.json` + `tests/test_signal_rules.py` 釘住的是
**只有 `sweep_cluster` 這一個 kind**,而且是三個股票日的樣本:

```python
CASES: tuple[tuple[str, str], ...] = (
    ("6715", "2026-08-17"), ("1727", "2026-08-05"), ("8103", "2026-08-19"),
)
```

其餘五種(cdp_cross / surge / crash / surge_pullback / vol_burst / limit_lock)
**完全沒有任何研究↔線上的一致性驗證**,也沒有離線回測。它們是「憑經驗寫的 UI 提醒」,
不是經過統計驗證的訊號 —— 這點 user 在 09-06 拍板時其實已經承認(「唯一正基準 = 掃單簇」),
但 code 裡沒有任何東西把這個事實表達出來(六種 kind 在 `RULE_KINDS` 裡地位平等)。

### 2.4 統一方案(具體到檔案)

**新建 `copycat/strategy/` 套件**,作為 live / backtest / research 三邊的唯一核心:

```
copycat/strategy/
├── clock.py        # EventClock:tick 時刻是唯一時間軸(見 §3)
├── tape.py         # TapeEvent(統一的輸入事件型別:trade / book / meta)
├── detectors/
│   ├── sweep.py    # 從 live/signal_state.py::_eval_sweep 搬出,零改動語意
│   ├── surge.py    # 從 _eval_surge / _eval_pullback 搬出
│   ├── volburst.py
│   ├── cdp.py
│   └── limitlock.py
├── policy.py       # = 現 server/signal_policy.py(它已經是純函式,直接搬)
└── replay.py       # 離線 harness:tape → 同一組 detector → 事件清單
```

步驟(expand–contract,每步單獨綠、單獨 commit;這是 🔵 + 🔴 混合,**必須分開**):

1. 🔵 `signal_policy.py` 整檔搬進 `strategy/policy.py`,`server/signal_policy.py` 留 re-export。
   零行為改動,現有測試全綠 = 驗證。
2. 🔵 `live/signal_state.py` 的六個 `_eval_*` 抽成 `strategy/detectors/*.py` 的純函式
   (狀態以 dataclass 顯式傳入傳出),`SignalDetector` 變成薄組合層。
   **這一步會撞到 CLAUDE.md §4「掃單簇參數 parity 走既有 fixture」** —— `PARAM_SPECS`
   的產生點不動(仍在 `signal_rules.py`),只動 detector 內部,fixture 照舊釘得住。
3. 🟢 `strategy/replay.py`:吃 tape(見 §9)跑同一組 detector,輸出與線上 jsonl 同形狀的事件列。
4. 🟢 為 cdp_cross / surge / vol_burst 各補一份 golden fixture,沿
   `record_sweep_cluster_golden.py` 的雙 oracle 格式(research 版 + prefix 版)。
5. 🔴(要 user 拍板)把研究目錄 `scripts/` 收斂為 `copycat/strategy/` 的呼叫端,
   或至少把 48 支腳本 git init + 把 `combo_events.py` 的核心函式改為 import 自 repo。

---

## 3. 問題 2:時間語意 —— 五分之四的規則用「本機到達牆鐘」,回測不可重現

### 3.1 證據

`live/signal_state.py:302-322`:

```python
        now = self._now_fn()
        if not self._in_session(now):
            return []
        if tick.trade_date != ctx.trade_date:
            return []
        mono = _mono(now)                      # ← 本機牆鐘秒數
        price = tick.price_milli
        key = tick.time or _clock_key(now)     # ← 交易所時刻(fallback 牆鐘)
        sweep_events = self._eval_sweep(code, tick, key, mono, enabled)
        …
        window = self._window.setdefault(code, deque())
        window.append((mono, price, tick.qty))  # ← 窗以牆鐘為軸
        cutoff = mono - self._cfg.surge_window_secs
```

模組 docstring 明說這是刻意的:

```
- **零 IO、時鐘可注入**:窗判定、elapsed、cooldown、rearm 全部讀 `now_fn()`
  (台北牆鐘,恆單調);`SignalEvent.time` 只放 tick 時刻,純顯示用。兩條時間軸
  混用會讓「盤後補推的舊 snapshot」把 cooldown 推到未來,故單一化(design R11)。
```

而 `_eval_sweep`(`signal_state.py:718` 起)用的是另一把尺:

```python
        secs = tick_secs(key)          # ← 交易所時刻,自午夜秒數
        lookback.append((secs, price))
        cutoff = secs - cfg.sweep_up_window_secs
        …
        window_start = secs - cfg.sweep_cluster_window_secs
```

**所以:`sweep_cluster` 用交易所時刻(因為要與研究對得起來),其餘五種用本機到達時刻。**

### 3.2 為什麼這是量化問題而不是風格問題

三個具體後果:

1. **離線不可重現**。同一份 `data/signals/20260911.jsonl` 的 tick 序列,離線重放產生的
   surge / vol_burst 事件集合**不會**與線上相同 —— 因為線上的窗長度取決於當天 event loop
   的排隊延遲。這讓「爆量規則要不要調 ratio」這種問題無法用歷史資料回答。
2. **回補 burst 會製造假訊號**。`stock_engine` 的回補 worker 落地後,一批 tick 會在
   毫秒內連續進 `_handle_quote`(雖然 `apply_backfill` 那條不走 hub,但**訂閱恢復後的
   即時追趕流會**)。牆鐘窗在追趕時被壓縮 → `_window[0]` 的基準價變成幾秒前而不是 5 分鐘前
   → `surge` 的 pct 被放大。反之 GIL 卡頓會拉長窗、低估 pct。
3. **時鐘偏移零監測**。`live/stock_models.py:_taipei_time` 把 TC4 的 UTC `PreciseTime`
   硬 +8 轉台北;全庫 grep `時鐘偏移|clock_skew|drift` **零命中**。若 TC4 或交易所時戳
   與本機差到秒級,「同毫秒群」的掃單判定與牆鐘窗會靜默分岔,而兩邊的數字都看起來對。

### 3.3 lookahead 防護現況

做得好的一塊:

- `backtest/simulate.py` 的時序語意寫得比多數自建回測嚴謹:
  ```python
  進場 = 觸發 bar close + slippage tick(cap 在漲停價);停損自觸發 bar 下一根起評估。
  鎖死 bar(low ≥ limit − limit_eps)凍結全部停損、S1 計時與外盤窗(D9)。
  同 bar 優先序:停損 > 時間出場 > 留倉;多重停損取最差成交價。
  ```
  而且 `excluded_unfillable`(觸發 bar 本身鎖死 → 進不了場)這種悲觀判定是對的。
- `engine/t1_open.py` 明確區分 lookahead 與非 lookahead:
  ```python
  無 lookahead 修正:auction_tell 分母用 adv20(09:00:06 可知),
  研究版 ÷全日量 只在 finalize 出現、僅供 golden 對照(spec §4c)。
  ```

做不到的一塊:**這全是註解與命名紀律,零機械閘**。`T1OpenSignals` 同一個 frozen dataclass
裡 `auction_share_adv20`(合法)與 `auction_share_dayvol`(lookahead)並列,型別相同,
任何下游拿錯一個都不會有任何訊號。CLAUDE.md 記的「T+1 又鎖續抱是 lookahead 別再引」
這條教訓**只存在 memory / handoff,repo 裡沒有對應的斷言**。

### 3.4 建議

- **短期(不改行為)**:`SignalEvent` 加一欄 `t_src`(`"exchange"` / `"wall"`),
  `_emit` 把它寫進 jsonl。這樣影子期對帳時至少知道哪些列的時間軸不可回放。
  加欄合乎 CLAUDE.md §4「T+1/T+2 回填原地補欄 + 離線讀者契約」W1 的「既有列只加欄不改欄」。
- **中期(🔴 行為改動,要走 /mod + 影子對照)**:把 `mono` 換成 `tick_secs(key)`,
  牆鐘只留給簿路(`evaluate_book` 沒有 tick 時刻)與 cooldown 的 fallback。
  必須做影子對照(同時跑兩軸,jsonl 記兩組),不能直接切。
- **時鐘偏移監測**:`tc4.py:1249`(`self._last_msg = time.monotonic()` 那行)旁邊,
  每 N 則比一次 `tick.time` 與本機牆鐘,差超過門檻印 WARNING。成本是每 N 則一次減法。
- **lookahead 機械閘**:`EventContext` / `T1OpenSignals` 的 lookahead 欄改用
  `typing.NewType` 包一層(例如 `Finalized = NewType("Finalized", float)`),
  讓 pyright 在「拿 finalize 值餵盤中判定」時就紅。零 runtime 成本。

---

## 4. 問題 3:延遲可觀測性 —— tick 抵達時刻根本沒被記下來

### 4.1 現況實測

```
$ grep -rn "perf_counter" --include=*.py copycat/   → 0 hit
$ grep -rni "latency|elapsed_ms|took_ms|duration_ms" --include=*.py copycat/
copycat/capital/client.py:429: # `tests/capital/test_fill_latency.py` 用它分辨兩種推播…
```

`time.monotonic()` 有 30 處,但用途全是 timeout / backoff / debounce / watchdog,
**沒有一處是在量端到端延遲**。唯一的真延遲量測在下單側:

`capital/client.py:678-687`:
```python
        logger.info(
            "balance 鏈: " + what + "(自成交回報到達起 %.0f ms)",
            *args, (time.monotonic() - self._fill_seen_at) * 1000,
        )
```

以及 `client.py:434-437`:
```python
                logger.info(
                    "成交樂觀套用部位: seq=%s stock=%s (%.1f ms)",
                    rec.seq_no, rec.stock_no, (time.monotonic() - t0) * 1000,
                )
```

這兩支量的是「成交回報進 handler → 部位落地」,**不是** order→ack,更不是 tick→signal。

### 4.2 結構性障礙:`StockTick` 沒有本機接收時戳

`live/stock_models.py:46-60`:
```python
@dataclass(frozen=True)
class StockTick:
    code: str
    price_milli: int
    qty: int
    cum_vol: int
    time: str          # 台北 HH:MM:SS.fff(parse 層已 +8)← 交易所時刻
    trade_date: str
    side: str
    is_trial: bool
    bid_milli: int | None = None
    ask_milli: int | None = None
```

沒有 `recv_ns`。所以就算想事後算 tick→signal,原始資料也不存在。

### 4.3 怎麼加(不影響效能的寫法)

1. **`live/tc4.py:1243-1250`**,`raw = sock.recv()` 之後那行:
   ```python
   self._last_msg = time.monotonic()
   self.handle_raw(raw)
   ```
   改成把 `recv_ns = time.perf_counter_ns()` 一起帶進 `handle_raw` → `parse_stock_realtime`。
   成本:每則一次 `perf_counter_ns()`(Windows 上約 30–60 ns),相對於 JSON parse 可忽略。
2. **`StockTick` 加 `recv_ns: int = 0`**(有 default,既有建構點零改動 —— 這個檔案的
   `bid_milli` / `ask_milli` 就是這樣加的,註解裡有前例)。
3. **`SignalEvent` 加 `emit_ns: int = 0`**,`signal_hub._emit`(`signal_hub.py:1012`)
   算 `lat_us = (emit_ns - tick.recv_ns) // 1000` 寫進 payload 一欄 `lat_us`。
   **合 W1 契約(只加欄)**,離線讀者不受影響。
4. **order→ack**:`capital/client.py:886-891` 的 `fut` 建立時記 `t_submit`,
   `_execute_write` 回傳前把 `ack_ms` 塞進 `_record()`(`client.py:335-342`,
   那個 dict 現在只有 ts/env/action/req/blocked/result)。
5. **彙總**:不要每則印 log(那會自己變瓶頸,`signal_hub` 已經有 `_DROP_LOG_EVERY` 的教訓)。
   做一個固定大小的 ring buffer(`collections.deque(maxlen=4096)`),13:40 的
   `_policy_outcome_worker`(`signal_hub.py:1250`)順手算 p50/p95/p99 落一行 jsonl。

---

## 5. 問題 4:狀態持久化與重啟恢復 —— 最容易被忽略的 critical

### 5.1 訊號側:回補 tick **刻意不重放**進 detector

`server/stock_engine.py:1349-1352`:
```python
            if self._signal_hub is not None:
                # 掛在 `ingest` 為真的分支內:試撮與重複 tick 已被短路,訊號層天然
                # 不必重複判(回補重放走 `apply_backfill`,不經過這裡 — SC-5)
                self._signal_hub.on_tick(code, tick, state)
```

而回補走的是 `stock_engine.py:1688`:
```python
                state.apply_backfill([t for t in ticks if t.trade_date == self._trade_date])
```
—— 直接進 `StockDayState`,**不經過 hub**。

同時,detector 的全部狀態都在記憶體(`signal_state.py:260-273`):
```python
    def reset_day(self) -> None:
        self._basis.clear();  self._prev.clear();  self._window.clear()
        self._suppressed.clear();  self._side.clear();  self._cooldown.clear()
        self._touch.clear();  self._latch.clear();  self._pullback.clear()
        self._sweep_group.clear();  self._sweeps.clear();  self._lookback.clear()
```
hub 的政策計數同理(`signal_hub.py:367` / `:672`):
```python
        self._policy_touch: dict[tuple[str, str], int] = {}
```

### 5.2 盤中 10:30 重啟會發生什麼(逐項)

| 項目 | 結果 |
|---|---|
| 分時圖 / 逐筆 | ✅ 回補補回來(`apply_backfill`) |
| 斷線那 2 分鐘內本該發的訊號 | ❌ **永久遺失**,且 jsonl 沒有任何「這段沒判」的記號 |
| `surge` / `vol_burst` 的 5 分鐘窗 | ❌ 從重啟後第一筆重新累積 → 之後約 5 分鐘內 pct 被**低估**(窗頭離現在太近) |
| `_lookback`(掃單簇 60 s 漲幅基準) | ❌ 同上,重啟後 60 s 內 `base[0] <= cutoff` 恆假 → `up_pct = 0.0` → **掃單簇 60 s 內一定不發** |
| `_cooldown` / `_touch` | ❌ 清空 → 冷卻中的規則立刻可再發,`touch_count` 從 1 重數 |
| `_policy_touch`(`first_of_day`) | ❌ 清空 → 同檔同政策**再推一次** Discord,且 jsonl 上兩列都標 `first_of_day: true` |
| CDP `_side` / `_suppressed` | ❌ 清空 → 穿越側別重新初始化,可能補發一則假穿越 |
| CDP `_basis` | ✅ hub 的 `_basis_worker` 會重抓 |
| 部位 / 委託 | ✅ 群益 `ConnectByID` 重播當日 backlog(見 §5.3) |

**對影子期對帳的傷害**:`first_of_day` 是政策列 `notify` 閘的一半
(`signal_hub.py:1121-1123`)。四週影子期裡任何一次盤中重啟,都會在 jsonl 留下
兩列同檔同政策的 `first_of_day: true`,而離線對帳腳本無從分辨。

### 5.3 部位側:靠券商重播,且聚合非冪等

`capital/store.py:1-14`:
```python
重啟後靠 SKReplyLib_ConnectByID 的當日 backlog 重播重建,無需持久化。

注意:聚合**非冪等** — 同一筆回報事件只能 apply 一次(目前唯一來源
ConnectByID 啟動重播 + 即時推送,天然唯一)。未來若加回報斷線重連,
重播前必須先 clear(),否則成交量會重複累計。
```

`grep "write_text|json.dump|atomic" copycat/capital/store.py` → **零命中**,確認純記憶體。

風險:
- 群益重播若**亂序**,`_RANK`(store.py:65 起「狀態只進不退」)擋得住降級,但
  **成交量的累加沒有等價保護** —— 同一筆 D 事件重播兩次就是兩倍。
- 跨日部位靠 OI 快照 + `_stale_fut_positions()`,證券靠庫存段。這在「持倉過夜」的
  情境下可用,但沒有本地權威帳可以與券商快照**對帳並告警**。

### 5.4 建議

1. **🟢 新增 detector 暖機模式**:`SignalDetector.warmup(code, ticks)` —— 逐筆跑
   `evaluate()` 的狀態推進段但**丟棄回傳事件**。掛點:`stock_engine.py:1688`
   `apply_backfill` 之後,若 `self._signal_hub is not None` 就把同一批 ticks
   餵 `signal_hub.warmup(code, ticks, state)`。這一步同時修好「重啟後 5 分鐘窗冷啟」
   與「斷線段窗空洞」。**注意**:這是行為改動(🔴),因為窗值會變 → 走 /mod。
2. **🟢 啟動時從當日 jsonl 重建 `_policy_touch` 與 `_cooldown`**。
   `signal_hub.today_signals()`(`:1421`)已經能讀到當日全部列,而 `id` 是決定性鍵
   (`trade_date-rule_id-code-kind-…-time_key`),重建所需資訊全在。
   加在 `SignalHub.start()`(`:533`)。
3. **🟢 jsonl 加一列「斷點標記」**:啟動時寫一列 `{"kind":"_session_start", …}` ——
   **但這會撞 CLAUDE.md §4「研究目錄離線讀者逐列讀 `s["kind"]` 無防禦 → 不新增列型」**。
   替代:寫到**另一個檔** `data/signals/_sessions.jsonl`,離線讀者不碰。
4. **🟢 fills 落 append-only jsonl 當本地真相源**,啟動以它重建 store 並與券商
   `ConnectByID` 重播結果**對帳、差異告警**(而不是二選一)。
   落點:`capital/store.py::_append_fill_locked`。

---

## 6. 問題 5:風控層 —— 只有單筆閘,且預設不限

### 6.1 現況(`capital/safety.py` 全檔已讀)

```python
@dataclass(frozen=True)
class SafetyConfig:
    order_enabled: bool = False
    max_qty: int | None = None      # None = 不限(單筆張/口)
    max_amount: float | None = None # None = 不限(單筆名目金額)
```

四支閘:`check_stock_order` / `check_future_order` / `check_cancel` /
`check_correct_price` / `check_decrease`。全部是**單筆、無狀態**的純函式。

做得好的細節(這些不要動):
- NaN 顯式擋(`_bad_price`:「NaN 對任何比較都是 False,會無聲穿過兩道閘」)。
- `remaining <= 0` 的改價顯式擋,不留給券商兜底。
- `daytrade_sell + buy` 組合顯式擋。
- `check_master` 先於一切,審計 blocked 才反映真原因。

### 6.2 量化系統標準風控 vs 現況

| 標準構件 | 現況 |
|---|---|
| 單筆數量上限 | ✅ `max_qty`(但預設 `None` = 不限) |
| 單筆金額上限 | ✅ `max_amount`(同上) |
| **單日虧損上限 / kill switch** | ❌ 無。`CAPITAL_ORDER_ENABLED` 是手動總開關,沒有自動翻 false 的路徑 |
| **總曝險上限** | ❌ 無 |
| **單一標的曝險上限** | ❌ 無。可以對同一檔連下 100 張 ×10 次,每筆都過閘 |
| **送單頻率閘(rate limit)** | ❌ 無 |
| **重複下單防護** | ⚠️ 只有平倉有(`client.py:1122-1163` `_close_inflight`,key = `股號:種類`);新單零防護 |
| **冪等 key** | ❌ 無。`_record()`(`client.py:335-342`)只有 ts/env/action/req/blocked/result,**沒有 request_id** |
| **異常行情熔斷** | ❌ 無。緩撮 / 鎖停 / TradeStatus 異常只在 UI 標示(`_observe_trade_status` 明說「只記錄不判定」),不擋單 |
| 環境隔離 | ✅ `capital/factory.py:96-110`,`CAPITAL_ENV` 未知值不默認正式 + prod banner 末 4 碼 |
| 審計 | ✅ `server/audit.py` append-only + 送單前後兩段 + late 補行 |
| 超時處置 | ✅ `client.py:892-898` 回「結果未知,勿重送」+ `shield` 不 cancel 底層 fut |

### 6.3 建議(具體到檔案)

**新增 `copycat/capital/portfolio_gate.py`** —— 吃 store 快照的帳戶級閘:

```python
@dataclass(frozen=True)
class PortfolioLimits:
    max_position_value: float | None = None      # 總曝險
    max_symbol_value: float | None = None        # 單一標的
    max_daily_loss: float | None = None          # 單日虧損(已實現;未實現另議)
    max_orders_per_minute: int | None = None
    halt_on_daily_loss: bool = True              # 觸發即翻 order_enabled=False

def check_portfolio(req, *, positions, today_pnl, recent_order_ts, limits) -> GateResult: ...
```

掛點 = `capital/client.py:876`(`_execute_write` 的第一段),接在
`check_stock_order` 之後、`_audit_blocked` 之前。
**store 已經有需要的資料**:`store.positions()` 給曝險、`Position.pnl_base` 給損益基底、
`FillRecord` 給今日成交。

**冪等**:`StockOrderBody` / `FutureOrderBody` 加 `client_order_id: str | None`,
client 以 `dict[str, OrderResult]`(當日,換日清)記已送出的 id;
重放同 id 直接回上次結果並審計一行 `action="order_replay"`。
這會動到 `server/capital_api.py:294` / `:310` 的 body schema → **前端同動**
(前端 `lib/close-order.ts` 系列已有送 body 的既有形狀,加選配欄不破相容)。

**異常行情熔斷**:`_observe_trade_status`(`stock_engine.py:1373`)現在只 log。
第二段做「per-code 偵測」時,把「緩撮中」的 code 加進一個 set,
`portfolio_gate` 讀它擋新單。**這會撞 CLAUDE.md §4 沒有登記的新契約** —— 要新增一條。

---

## 7. 問題 6:資料品質 —— 沒有集中清洗層,0 價判定散在 7 處

### 7.1 現況:同一個「0 價」問題被七個地方各自處理一次

| 位置 | 處置 |
|---|---|
| `live/stock_state.py:189` | `if tick.price_milli <= 0: return False`(鎖停市價佇列) |
| `live/signal_state.py:581` | `if price <= 0:` 跳過峰值/回檔判定(「否則 (peak−0)/peak 是一記假 100% 回檔」) |
| `live/signal_state.py:712` | `if price <= 0 or tick.qty <= 0: return []`(掃單軸整段跳過) |
| `live/aggregate.py:71` | 「foreign / stale / spot 同價 / spot 0 價皆 False」 |
| `live/stock_models.py:155` + `_best_limit_price` | 鎖停側別補判 |
| `server/signal_hub.py:1061` | `if ref is None or ref <= 0 or price <= 0: return`(政策層) |
| 前端 `lib/futures-overlay.ts` | `usable()` 0 價閘(CLAUDE.md §4 明列為「差異白名單」) |

CLAUDE.md §8 已經記過「四處被同一個 0 打穿的事故」,而 `signal_hub.py:66-68` 的註解
也承認這件事:

```python
# 私有名刻意共用:鎖停時 TC4 在第一檔推「市價單佇列」價格欄為 0,而過濾規則寫成兩份
# 就會漂移(CLAUDE.md §8 已記四處被同一個 0 打穿的事故)。這裡要的正是消費端那把尺。
from copycat.live.stock_models import StockTick, _best_limit_price
```

### 7.2 其他資料品質維度的現況

| 維度 | 現況 |
|---|---|
| 重複 tick | ✅ `cum_vol` 單調去重(`stock_state.ingest`) |
| 試撮 | ✅ 時間窗判定,dedup 前短路 |
| 跳號偵測 | ✅ 前端 `seq` 跳號 → refetch(CLAUDE.md §4 有契約);但**後端不記帳** |
| 0 價 | ⚠️ 散落 7 處 |
| 0 量 | ⚠️ 只有掃單軸判(`signal_state.py:712`) |
| 價格跳動異常(fat finger tick) | ❌ 無偵測 |
| 交易所回補資料與即時流的一致性 | ⚠️ `apply_backfill` 是 reset + 重放,不比對 |
| 缺漏統計 | ❌ 無。TC4 零推播自癒(`tc4.py:629` 起)只管「有沒有推」,不管「推的內容有沒有洞」 |

### 7.3 建議

**新增 `copycat/live/quality.py`**:

```python
@dataclass(frozen=True)
class TickFlags:
    zero_price: bool
    zero_qty: bool
    market_queue: bool      # 鎖停市價佇列(bid/ask == 0)
    out_of_session: bool
    stale_cum: bool         # cum_vol 未前進
    price_jump: float | None  # 相對前一筆的跳動幅度

def classify(tick: StockTick, prev: StockTick | None) -> TickFlags: ...
```

**不是**要改變任何消費者的行為(那是 🔴),而是:
1. 各處的判斷改為讀 `TickFlags` 的對應欄(🔵 純重構,行為逐字不變);
2. `stock_engine` 每日彙總 flags 落一行 jsonl → 第一次有「今天資料品質如何」的量。

這一步對效能是**正向**的:現在同一筆 tick 的 `price <= 0` 在 detector 裡被判了兩次
(`:581` 與 `:712`),× 30 條規則 = 每 tick 60 次冗餘比較。

---

## 8. 問題 7:策略/參數的版本化與可重現性

### 8.1 現況分三層,一層比一層弱

**層 1 — dataclass config(最好)**:`SignalsConfig` / `StrategyConfig` / `CorrConfig` /
`BacktestConfig` 全是 `frozen dataclass` + `configs/*.json` 逐鍵覆寫 + **未知鍵 raise**。
這比大多數量化系統的 YAML 亂塞好。

**層 2 — 規則 CRUD(弱)**:`data/signal_rules.json` 是**單一可就地覆寫的快照**。
實測 repo 內的 dev 檔:
```json
{ "_cache_version": 1, "rules": [ {"id":"r-1785975520-000","name":"CDP 穿越","kind":"cdp_cross",
  "enabled":true,"notify_discord":true,"cooldown_secs":600,"params":{"rearm_ticks":5.0},…} ] }
```
`_cache_version`(`signal_rules.py:58` = 4)是 **schema 版**,不是內容版。
`upsert_rule`(`signal_hub.py:468`)直接 `save_rules(path, list(merged.values()))` 覆寫,
**零歷史**。

**層 3 — 訊號列(最弱)**:`signal_hub._emit`(`:1015-1033`)寫進 jsonl 的欄位:
```python
"id","rule_id","rule_name","kind","code","name","price","time",
"levels","direction","pct","touch_count","notify"
```
實測 09-11 的政策列:
```json
{"id":"2026-09-11-r-1789058168-006-2305-policy-S-09:02:27.000",
 "rule_id":"r-1789058168-006","rule_name":"掃單簇","kind":"policy","policy":"S",
 "code":"2305","price":40400,"pct":1.0000000000000009,
 "sweep":{"n30":2,"levels":2,"qty":13,"up_pct":1.0000000000000009},
 "self":{"chg_pct":4.94,…},"peers":[],"peers_up":0,…}
```

**含義**:一則訊號**無法回溯它當時生效的門檻**。如果四週影子期裡任何一刻
(a)動過 `signal_rules.json` 的 `params`、(b)動過 `configs/signals.json` 的
`policy_peer_up_pct` / `policy_max_chg_pct` / `policy_push_end`、或
(c)動過自選群組(= 動過族群定義,`signal_policy.resolve_groups`),
離線對帳都分不出來。而(c)**幾乎一定會發生** —— CONTEXT.md 明寫「user 增刪群組就是在調族群」。

值得肯定的一半:政策列有記 `groups` / `peers` / `screen_member` 快照,
所以「族群當時是誰」**是**可回溯的。缺的只有門檻那一半。

### 8.2 順帶發現:浮點字面污染

`"pct": 1.0000000000000009` —— 這是 `(group.high/base - 1) * 100` 的浮點噪音直接落檔。
`up_pct` 同值重複兩次(`pct` 與 `sweep.up_pct`)。
不是 bug,但離線 diff 會被這種噪音干擾;而
CLAUDE.md §4「回填原地補欄」契約明說「回填改成整檔 dumps → 舊列鍵序 / 浮點字面變動,
對帳 diff 整檔紅」—— 也就是說這些字面值已經被當成契約的一部分,**不能隨手 round**。

### 8.3 建議

1. **🟢 `Rule` 加 `rev: int` + `params_hash: str`**(`signal_rules.py` 的 `Rule` TypedDict)。
   `upsert_rule` 每次改 rev +1;`_emit` 把 `rule_rev` / `rule_hash` 寫進列。
   **撞 CLAUDE.md §4「訊號規則參數契約前後端同表」**:`PARAM_SPECS` / `INT_PARAM_KEYS`
   不動(rev 不是 param),但前端 `signal-params.ts` 的 Rule 型別要同動,
   `tests/fixtures/signal_param_specs.json` 不受影響(它只裝 specs/int_keys/cooldown)。
2. **🟢 `save_rules` 改 append-only 歷史**:除了覆寫 `signal_rules.json`,
   同時 append 一行到 `data/signal_rules_history.jsonl`(rev / ts / 完整 rules 快照)。
3. **🟢 啟動 + 每日首列記 config 指紋**:`configs/*.json` 與 `signal_rules.json` 的
   sha256 寫進 `/api/health`(已有 `git_sha`,加 `config_sha`)+ 每日
   `data/signals/_sessions.jsonl` 的 session 列。
4. **🔵 `replay/runner.py:meta`** 現在記 `config_path` 字串(`runner.py` 的 `meta` dict),
   改記 config 的 sha256 + 完整內容。**低成本,立刻做**。

---

## 9. 問題 8:與效能改造的關係(衝突 vs 協同)

### 9.1 協同(補落差順便讓它更快)

| 落差 | 效能面的副作用 |
|---|---|
| 集中資料清洗層(§7) | **正向**:現在同一筆 tick 的 `price<=0` 在 30 條規則裡各判 2 次 = 60 次冗餘比較/tick |
| 抽 `copycat/strategy/` 純函式核心(§2.4) | **正向**:同 kind 的多條規則目前**各自維護一份 `_window` deque**(`signal_hub._make_slot` 每條規則一顆完整 `SignalDetector`)。抽核心後窗可共用,150 檔 × 30 規則的 deque 數從 4,500 降到 kind 數 × 檔數 |
| 統一時間軸到 tick 時刻(§3) | **中性偏正向**:省掉每 tick 一次 `self._now_fn()` + `_mono()`(datetime 減法);`tick_secs()` 是字串 split + int,更便宜 |
| tick recv_ns(§4) | **輕微負向**:每則多一次 `perf_counter_ns()`(~30–60 ns),相對 JSON parse 可忽略 |
| 帳戶級風控(§6) | **無影響**:下單一天個位數,不在熱路徑 |
| detector 暖機(§5.4) | **負向但一次性**:重啟時多跑一輪回補 tick;可用 batch 模式(跳過 event 組裝) |

### 9.2 衝突(要先拍板順序)

1. **「抽 strategy 核心」與「換上 numpy/polars 做向量化」方向相反**。
   線上是逐 tick 串流,向量化幫不上;離線回測才用得到。
   建議:`copycat/strategy/` 保持 stdlib 純函式(線上),
   `[research]` extra 裝 polars 只給離線對帳用。**不要讓 runtime 相依 polars。**
2. **「統一時間軸」是 🔴 行為改動,會讓既有的四週影子期資料半途改尺**。
   建議順序:影子期跑完 → 對帳 → 再改時間軸;或雙軸並記(jsonl 兩欄),
   對帳時選一軸。**這題必須 user 拍板**。
3. **detector 暖機會改變窗值 → 改變事件集合**。同上,不能在影子期中途上。

---

## 10. 不要動的地方(反向建議)

1. **`copycat/backtest/simulate.py` 的時序語意** —— 悲觀成交、鎖死 bar 凍結、
   同 bar 停損優先序、`excluded_unfillable`。這比 backtrader / vectorbt 的預設語意嚴謹得多。
   **不要換成通用回測框架** —— 換了會丟掉這些台股特化的正確性。
2. **訊號 id 的決定性鍵**(`signal_hub` SC-7):
   `trade_date-rule_id-code-kind-levels|direction-time_key`。這是重啟安全的基礎,
   任何「改用 uuid」的提議都是倒退。
3. **下單審計的 shield + 「結果未知,勿重送」**(`client.py:889-898`)。
   這是真錢路徑上最難寫對的一段,已經寫對了。
4. **兩條佇列不合併**(jsonl 真相源 vs Discord 可丟路,`signal_hub` CC-5)。
5. **`configs/*.json` 的「未知鍵 raise」**。
6. **CLAUDE.md §4 的跨檔契約 + golden fixture parity 機制**。
   這是整套系統最像量化工程的部分 —— 所有改造都應該**沿用**這個機制
   (新契約寫進 §4 + 加 fixture),不是繞過它。
7. **`copycat/engine/` 的 `LockTracker` / `T1Tracker` 本身**。
   形狀正確(零 IO 狀態機、config 注入、finalize 與盤中查分離)。
   要做的是「讓 live 也用它」,不是重寫它。
8. **`server/verify.py` + `VERIFY_BREADTH_FAIL` 失效注入通道**。這是好東西,擴大用,別刪。
9. **TC4 零推播自癒 / sparse 腿 / heal gate 三把不同的鐘**。
   看起來冗餘,但 CLAUDE.md §4 已逐條說明三個消費者的語意不同,合併會壞。

---

## 11. 量測方法(要證明上面的判斷)

### 11.1 一致性(§2)

```
# 1. 用 repo 外研究 tick 檔 + 現有 golden 腳本,把 case 從 3 個擴到 30 個
.venv\Scripts\python tests\fixtures\record_sweep_cluster_golden.py
# 2. 對其他五種 kind 各寫一支同款 record 腳本(沿雙 oracle 格式)
# 3. 判準:expected_research 事件時刻集合 ⊆ expected_prefix,且線上 detector == expected_prefix
```

### 11.2 時間軸不可重現(§3)

```
# 拿 data/signals/20260911.jsonl 的 surge / vol_burst 列,
# 用同日的研究 tick 檔離線重放 SignalDetector(now_fn 注入 = tick 時刻)
# 判準:事件集合的 Jaccard 相似度。預期 < 1.0 —— 差多少就是這個問題的量級。
```

### 11.3 延遲(§4)

```
# 加 recv_ns / emit_ns 之後,盤中 09:00–09:30 收 ring buffer,盤後:
#   tick→signal p50 / p95 / p99(μs)
#   分開統計「有規則命中」與「零命中」兩群(後者是純 gate 成本)
# 基準值猜測(待實測):零命中 p50 應 < 200 μs;命中 p95 可能 > 2 ms(政策層 peers 快照)
```

### 11.4 重啟恢復(§5)

```
# 用 tape replay(見下)在 fake source 上重放一天,
# (a) 一次跑完 → 事件集合 E0
# (b) 在 10:30 處中斷、重啟、繼續 → 事件集合 E1
# 判準:E0 \ E1 = 遺失的訊號;E1 \ E0 = 重複/假訊號。兩者現在都預期非空。
```

### 11.5 tape 錄製(所有上述量測的前置)

**新增 `copycat/live/tape.py`**:`tc4.py:1243` 的 `sock.recv()` 之後,
把 `(recv_ns, raw)` append 到當日 gz jsonl(背景 thread + 有界佇列,
沿 `signal_hub` 的 drop-oldest 模式)。

- 成本估算:開盤 ~300 則/s × 每則 ~500 B → ~150 KB/s → 一天 ~2.7 GB 未壓縮 / ~300 MB gz。
- 這是把「研究目錄 971 MB 的 tick 檔」變成 repo 內可重放資產的唯一路。
- 有了 tape,§11.1 / §11.2 / §11.4 才真的做得起來。

### 11.6 風控(§6)

```
# hypothesis(dev extra)對 portfolio_gate 寫 property test:
#   隨機產生 order 序列 + 部位快照,斷言「任何通過的序列,總曝險 ≤ 上限」
```

---

## 12. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 結論 |
|---|---|---|---|---|
| **自建 `copycat/strategy/`(stdlib)** | live + backtest + research 共用核心 | §2 三份實作 | 一次性搬遷 + 影子對照 | **建議導入** |
| **自建 tape recorder + replay(stdlib gzip)** | `live/tape.py` + `strategy/replay.py` | §11 全部量測的前置 | 每日 ~300 MB gz | **建議導入** |
| `polars` | **只在** `[research]` extra,離線 jsonl 對帳 | 8,789 列 → 幾十萬列時的 groupby | 不進 runtime;與 stdlib-only 哲學的妥協要明說 | **有條件導入**(runtime 不碰) |
| `msgspec` | jsonl 讀寫(離線對帳腳本) | `json.loads` 逐行 × 數十萬列 | 多一個相依 | **有條件導入**(dev/research only) |
| `hypothesis` | dev extra,風控閘 property test | §6 的帳戶級不變量 | 只在 dev | **建議導入** |
| `pyarrow` / `duckdb` | 研究資料集查詢 | 971 MB tick 檔的 ad-hoc 查詢 | 大相依;現有 CSV/JSON 流程已跑得動 | **不建議**(現階段沒被卡住) |
| `backtrader` / `vectorbt` / `zipline` | 回測引擎 | — | **會丟掉 `simulate.py` 的台股特化時序語意**(鎖死凍結、悲觀成交、漲停 cap) | **不建議** |
| `redis` / `kafka` | 事件匯流 | — | 單機單 process,加了只是多一個會死的元件 | **不建議** |
| OpenTelemetry | 延遲追蹤 | §4 | 對單機單 process 過重;jsonl + ring buffer 就夠 | **不建議** |
| `numpy` | 線上訊號計算 | — | 逐 tick 串流,向量化無用武之地;`np.float64` 標量運算比 Python float **更慢** | **不建議**(線上);離線隨 polars 進來即可 |

---

## 13. Findings 索引(詳見 structured output)

| id | 嚴重度 | 標題 |
|---|---|---|
| Q1-01 | critical | 訊號邏輯三份實作,真正在用的那份在 repo 外且無版本控制 |
| Q1-02 | critical | 六種訊號裡五種用本機牆鐘窗,離線不可重現 |
| Q1-03 | critical | 盤中重啟 = 訊號狀態全失,回補 tick 刻意不重放進 detector |
| Q1-04 | high | 零延遲量測:tick 抵達時刻沒被記錄,全庫零 `perf_counter` |
| Q1-05 | high | 風控只有單筆閘且預設「不限」,缺帳戶級與熔斷 |
| Q1-06 | high | 新單無冪等 key,審計無 request_id |
| Q1-07 | high | 無集中資料清洗層,0 價判定散在 7 處 |
| Q1-08 | high | 訊號列不帶生效門檻,規則檔就地覆寫無歷史 |
| Q1-09 | medium | lookahead 防護純靠註解,零機械閘 |
| Q1-10 | medium | 回填 worker 用日 K 代理研究的 13:20 出場價,對帳換了尺 |
| Q1-11 | medium | 政策與研究的四條已知差異只有一條有 golden 釘住 |
| Q1-12 | medium | 訊號 → 下單之間沒有 seam,影子期結束無處接 |
| Q1-13 | medium | 部位/委託零本地權威帳,全靠券商重播且聚合非冪等 |
| Q1-14 | medium | 線上零 config 指紋;replay meta 只記路徑不記內容 |
| Q1-15 | medium | 交易所時鐘與本機時鐘零偏移監測 |
| Q1-16 | medium | 無市場資料錄製→重放管道,所有一致性量測都做不起來 |
| Q1-17 | medium | 每條規則一顆完整 detector,同 kind 的窗重複維護 |
| Q1-18 | low | 六支 engine 無統一骨架(已有盤點),加資料面就重刻 lifecycle |
| Q1-19 | low | 無 trade journal / 績效歸因,影子期結束只能手動對帳 |
| Q1-20 | low | jsonl 浮點字面噪音,且已被契約凍結不能隨手 round |

---

## 14. Open questions(需要 user 拍板,不自行決定)

1. **影子期四週結束後,政策是「直接接實單」還是「人工照政策下單」?**
   這決定 §6 的 execution 層要做到什麼程度(前者要完整風控 + 冪等 + 熔斷;後者只要告警)。
2. **研究目錄 `copycat-trading-review` 要不要納版控?**(48 腳本 / 7,306 LOC / 971 MB data)
   若是,data/ 要不要 LFS 或只納 scripts/?這是回測可重現性的根。
3. **時間軸統一(牆鐘 → tick 時刻)是 🔴 行為改動,要在影子期中途改還是等結束?**
   建議等結束或雙軸並記,但這是 user 的決策。
4. **`StockTick` 加 `recv_ns` 欄可以嗎?**(frozen dataclass,加 default 欄不破既有建構點,
   但會動到 parse 鏈與序列化形狀 —— 若進 WS payload 會撞前端契約)
5. **單日虧損上限的口徑:已實現還是含未實現?** 含未實現要接 `pnl_base` 的平移基底,
   而 `avg_source` 的兩種語意(broker 含買費 / fill 純成交價)會讓兩個口徑差一筆手續費。
6. **tape 錄製一天 ~300 MB gz,保留幾天?** 30 天 ≈ 9 GB。
7. **有沒有第二台機器?** 現在前後端 + TC4 同機,tape 錄製與重放同機跑會互相干擾量測。
