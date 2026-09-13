# S2-rules-config —— 訊號:規則層、設定與前後端契約

**掃描日**:2026-09-13 ｜ **repo**:`C:/side-project/copycat` @ master `caca1d30`
**範圍**:`copycat/signal_rules.py`(640 行,整檔讀完)、`copycat/signals_config.py`(77)、
`configs/signals.json`(**不存在**)、`tests/fixtures/signal_param_specs.json`(35)、
`copycat/server/signal_hub.py` 規則段(289-530、598-680、980-1040)、`copycat/server/app.py`
(234-258 `RuleBody`、1409-1625 routes)、`copycat/live/signal_state.py`(855,整檔讀完);
前端 `frontend/src/lib/signal-params.ts`(81)、`components/stock/SignalRulesDialog.tsx`(573)、
`hooks/useSignalRules.ts`(105)、`lib/signal-param-parity.test.ts`(127)、`lib/signal-model.ts` 去重段。

**實測環境**:專案 `.venv`(Python 3.13.13,Windows 11)。所有標「實測」的數字都是在這台、
這個 venv 上跑出來的;腳本留在本目錄(`bench_rules.py` / `bench_slots2.py` / `bench_shared.py` /
`bench_micro.py` / `bench_day.py` / `bench_open.py` / `bench_mem.py` / `bench_seed.py` / `bench_edit.py`)。
**repo 零改動,server 未啟動,零下單。**

---

## 0. TL;DR — 這一輪新挖到的五件事

| # | 事 | 證據等級 |
|---|---|---|
| 1 | **種子規則的 `rule_id` 每次開機重生**。`data/signals/20260911.jsonl` 同一天同時存在 `r-1789058168-006` 與 `r-1789088717-006` 兩個「掃單簇」—— `_event_id` 的「重啟後同一事件同 id」在 prod 被違反,影子期四週的離線對帳沒有穩定 join key | **prod 資料實證** |
| 2 | **磁碟 v1(4 條)/ 記憶體 v4(7 條)已分離 29 天**,遷移鏈每次開機重跑(prod log 三次開機各一輪)。這不是「工作樹與 prod 分岔」—— 是同一個檔,`load_rules` 刻意不回寫 | **prod log + 實測 load** |
| 3 | **編輯規則(連改個名字 / 勾「通知」都算)= 靜默清空該規則所有 per-code 狀態**,鎖漲跌停與 CDP 穿越會在第二筆 tick 重發一則、`touch_count` 歸 1。而編輯的動機通常正是「把通知打開」→ 重發那則直接進 Discord | **實測復現** |
| 4 | **`MAX_RULES = 30` 量化後是空頭支票**:以 09-10 開盤 300 s 的真實 tick 分佈重放,7 條規則 178.8 µs/tick(2.42% 一核)、30 條 **1367 µs/tick(18.5% 一核)**;而且全在 **event loop 執行緒**上(`_handle_quote` 走 `call_soon_threadsafe`)。記憶體 38.7 MB → **149 MB**;把 `window_secs` 調到契約上界 3600 → 穩態外推 **~2 GB** | **實測** |
| 5 | **parity 只釘了一半**:`PARAM_SPECS` / `INT_PARAM_KEYS` / `COOLDOWN_MIN,MAX` 有 golden fixture 兩邊各一條(今天跑過,全綠);但 **`MAX_RULES`、`CDP_LEVELS`、錯誤碼三個字面鏡像零 parity 測試** —— 而它們漂掉的樣態與 N055 修掉的那個一模一樣 | **程式碼 + 測試清單** |

**另外兩件量化面的硬傷**:規則 CRUD **零 log、零審計**(影子期中途調參事後查不出來);
掃單簇 golden fixture 釘的是「拍板參數下的定義」,**使用者在規則視窗改參數後測試照樣全綠而 prod 已偏離研究基準**。

---

## 1. 現況地圖:規則層實際怎麼運作

### 1.1 四層與它們的分工

```
configs/signals.json (不存在 → 全預設)
   └─ signals_config.SignalsConfig  frozen dataclass,33 欄
        │  「全域門檻」+「政策層參數」+「接線層參數」三類混在同一顆
        ▼
data/signal_rules.json (磁碟 v1,4 條)
   └─ signal_rules.load_rules()  三態 + 遷移鏈 v1→v2→v3→v4(**不回寫**)
        │  記憶體 7 條:CDP 穿越 / 爆拉爆跌 / 爆量 / 鎖漲跌停 / 爆拉回檔 1% / 2% / 掃單簇
        ▼
signal_hub._make_slot(rule)  每條規則 → 一顆 _RuleSlot
        │  rule_config(rule, base) → per-rule SignalsConfig(dataclasses.replace)
        │  SignalDetector(per_rule_cfg, now_fn=...)   ← **一條規則一顆完整狀態機**
        │  enabled = frozenset({kind}) if rule["enabled"] else frozenset()
        ▼
on_tick / on_book:for slot in self._slots.values(): slot.detector.evaluate(...)
        │  **在 event loop 執行緒上同步跑**(stock_engine.py:1150 call_soon_threadsafe
        │  → _handle_quote:1352 → hub.on_tick)
        ▼
_fanout → _emit → _publish(WS 同步)+ _enqueue(jsonl / Discord 兩佇列)
```

`signal_rules.py` 的模組 docstring 把設計意圖寫得很清楚:
> 一條規則 = 一顆未改動的 `SignalDetector` 的參數來源:`rule_config()` 把規則攤成
> per-rule `SignalsConfig`,所以「調參數」永遠只是換一份 config,detector 本身零改動。

這個決定讓規則層極度簡單(`signal_rules.py` 零 IO 之外只有一支 `save_rules`,
`normalize_rule` 是純函式、冪等、有 188 條測試),代價全部落在 **N 條規則 = N 份完整市場狀態**。
這一輪的工作就是把那個代價量出來。

### 1.2 規則 CRUD 的完整流程(問題 1)

**前端(`SignalRulesDialog.tsx`)**

1. `blankForm()` / `toForm(rule)` → `FormState`,**數字欄一律以字串存**(`:50-60` 的註解說明:
   存 number 時「清空重打」會在中途變成 0 / NaN)。
2. `changeKind()` 換種類 = 整組換 `paramDefaults(kind)` + levels(`:209-215`)。
   **不沿用舊 kind 的 params** —— 沿用的話後端會以「多鍵 / 缺鍵」拒收,而畫面看不出是哪一格。
3. `patchParam()` 走 functional updater(`:220-222`),避免同一輪連改兩欄互蓋。
4. `submit()`(`:243-295`)本地驗證,順序是刻意的:
   冷卻「非整數」→「出界」→ 逐欄「整數鍵非整數」→「出界」→ 最後才是泛用 `bad`。
   出界訊息精確到欄名與界(`${field.label}須在 ${field.min}–${field.max} 之間`)。
   `cdp_levels` 以 `CDP_LEVELS.filter()` 送**固定序**,不用點擊序。
5. `useSaveRule()`:有 id → `PUT /api/stock/signals/rules/{id}`,無 id → `POST`。
   `encodeURIComponent(id)`。`onSuccess` 一律 `invalidateQueries` **不 setQueryData**
   (POST 的 id 由後端配、PUT 會被正規化)。

**後端**

6. `RuleBody`(`app.py:234-258`):**每個欄位都宣告成 `object` 且預設 None**。
   這是為了守住 `{"detail": {"error": code}}` 的全站錯誤契約 —— 宣告成 `bool`/`int` 會讓
   pydantic 寬鬆轉型、宣告成必填會回 422 + list 形 detail。**這是本區塊寫得最好的一段,不要動。**
7. `_save_rule` → `hub.upsert_rule(body.payload(), rule_id=...)`;
   `OSError` 在這裡就轉 500 `RULE_SAVE_FAILED`(不轉的話全域 handler 會收成 502 TC4_DOWN,
   排查被帶去反方向)。
8. `upsert_rule`(`signal_hub.py:468-505`)順序(R17):
   `async with self._rules_lock` → 配 id / `RULE_NOT_FOUND` → `normalize_rule(others=排除自身)`
   → `_make_slot` → **`await asyncio.to_thread(save_rules, ...)`** → 同一個**不含 await 的同步區塊**
   內 swap `_slots` + `_seed_slot(slot)`。
   落檔失敗 → 記憶體零變更、例外往外拋。**記憶體不得先於落檔更新**這條紀律是對的。
9. `_seed_slot`(`:517-529`):只對 `cdp_cross` 有效,把 hub 手上的當日基準逐檔補進新 detector。
   註解自陳:「沒有這一步,盤中編輯規則等於把該規則的 CDP 停到隔天 —— 而畫面只會顯示
   『這條規則今天都沒發』,沒有任何錯誤訊號」。**這半邊做對了;另外半邊(cooldown / latch /
   suppressed / 波狀態 / touch_count)沒有人補 —— 見 §4 的 F-03。**
10. **廣播**:沒有。規則變更**不經 WS**,只靠前端自己 `invalidateQueries` 重抓。
    其他瀏覽器分頁 / 其他機器上的畫面要等下一次 window focus 才會更新。
    （`useSignalRules` 沒有 `refetchInterval`,唯一呼叫點 `StockPage.tsx:95`。）

**每一段的成本 / 失敗處理**見 §2 的延遲預算表。

### 1.3 規則檔的三態與遷移鏈

`load_rules(path)` 三態(`:502-563`):

- 缺檔 → `None` → hub 走 `default_rules(cfg, legacy_flags)` 生成種子並**落檔**。
- 合法(**含空陣列**)→ list。「空陣列 ≠ 缺檔」是刻意的:使用者刪光規則後重啟不得復活預設。
- 壞檔 / 驗證失敗 / 版本不符 / 超過 `MAX_RULES` → **raise** → `_boot` 傘 → hub None →
  signals routes 503。靜默套預設會在盤中無預警改變推播行為,所以這裡大聲是對的。

遷移鏈 v1→v2(補 `rearm_dwell_secs`)→ v3(append 兩張 `surge_pullback` 種子卡)→
v4(append 掃單簇種子卡 + `cdp_cross`/`vol_burst` 通知翻 false)。
**載入時不回寫檔案** —— docstring 說這段就是回退窗。這個設計在「升級當天」是對的,
在「跑了 29 天」就變成 §4 的 F-01 / F-02。

### 1.4 prod 現況(實測)

`data/signal_rules.json` 修改時間 **2026-08-15 20:21**,`_cache_version: 1`,4 條規則。
`.gitignore` 第 7 行 `/data/` —— 不進版控。

```
$ .venv/Scripts/python -c "... load_rules('data/signal_rules.json') ..."
disk version 1 rules 4
rule_config on RAW disk rule: KeyError 'rearm_dwell_secs'
after load_rules: 7 rules; cdp params {'rearm_ticks': 5.0, 'rearm_dwell_secs': 300.0}
rule_config after load_rules: OK -> 300.0
```

**任務敘述裡的兩個前提要修正**:
- 「`rule_config()` 會 KeyError」:**只有繞過 `load_rules` 直接拿原始 dict 時才會**。
  走正常路徑(hub 唯一的路徑)遷移鏈會補上鍵,7 條規則全部可用。
- 「工作樹與 prod 的規則檔分岔」:**沒有分岔,是同一個檔**。
  prod log `logs/server-2026091*.log` 裡的遷移行點名的是 `r-1785975520-000`,
  正是這個檔裡的 id;`data/signals/20260911.jsonl` 的 `rule_id` 也對得上。
  真正的事實是 **磁碟(v1 / 4 條)與記憶體(v4 / 7 條)分離了 29 天**,因為 `load_rules` 不回寫、
  而且**從 2026-08-15 起沒有人做過任何一次 upsert**(有 upsert 就會以 v4 落檔)。

prod log 實證(三次開機各跑一輪完整遷移):

```
2026-09-10 09:06:07,374 訊號規則檔 v1→v2:規則 'r-1785975520-000' 補 rearm_dwell_secs=300.0
2026-09-10 09:06:07,374 訊號規則檔 v2→v3:append 種子卡 '爆拉回檔 1%' ...
2026-09-10 09:06:07,375 訊號規則檔 v3→v4:規則 'r-1785975520-000'(cdp_cross)通知改為 false ...
2026-09-10 09:06:07,375 訊號規則檔 v3→v4:append 種子卡 '掃單簇' ...
2026-09-11 00:36:08,456 (同一輪,再一次)
2026-09-11 09:05:17,528 (同一輪,再一次)
```

---

## 2. 端到端延遲預算

### 2.1 A 段:規則 CRUD(**每次編輯一次,一天最多幾次** —— 這不是效能問題,是正確性問題)

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| A1 | 前端 `submit()` 本地驗證 | `SignalRulesDialog.tsx:243-295` | < 10 µs | 推估(純同步、最多 5 欄) | 出界 / 非整數在此就攔下,不打網路 |
| A2 | fetch → vite proxy → uvicorn → route + `RuleBody` 解析 | `app.py:234-258, 1602-1616` | ~0.3–1 ms | 推估(本機 loopback,無 middleware) | `app.user_middleware == []`,無 timing 可查 |
| A3 | `_rules_lock` acquire | `signal_hub.py:479` | ≈ 0 | 推估 | 只與其他 CRUD 競爭;**不擋 tick** |
| A4 | `normalize_rule` | `signal_rules.py:199-244` | **2.48 µs** | 實測 | `cdp_cross`,`others={}`;名稱唯一性是 O(N),N ≤ 30 |
| A5 | `rule_config` + `SignalDetector()` | `signal_rules.py:582`、`signal_hub.py:459` | **5.41 µs** + ~1 µs | 實測 | `dataclasses.replace` 是 A5 的全部成本 |
| A6 | **`await to_thread(save_rules)`** | `signal_hub.py:495` | **0.56–0.79 ms** 磁碟 + **0 … 20 s 佇列等待** | 磁碟實測 / 佇列上界推估 | ⚠ 走 loop 預設 ThreadPoolExecutor(20 workers),鄰居是**不可中斷的 TC4 歷史取數**;等待期間 `_rules_lock` 持有中 |
| A7 | slots dict copy + swap | `signal_hub.py:497-500` | < 5 µs | 推估(N ≤ 30 的 dict copy) | swap 是整顆替換,熱路徑讀得到的永遠是完整一致的快照 |
| A8 | **`_seed_slot`(只有 `cdp_cross`)** | `signal_hub.py:517-529` | **0.38 / 1.19 / 3.05 ms**(50 / 90 / 150 檔) | 實測 | **二次式**:`set_basis` 內 `self._side = {k:v for ...}` 是 O(全部 `_side` 條目),外層再乘檔數。在 event loop 上、鎖內 |
| A9 | 回應 + `invalidateQueries` → `GET /rules` | `useSignalRules.ts:92, 60-66` | ~1–3 ms | 推估 | `rules()` 本身 7 × `_copy_rule`,µs 級 |

**A 段合計**:健康路徑 **~1–5 ms**(150 檔自選時由 A8 主導);
**最壞 ~20 s**(A6 排在一趟 TC4 歷史取數後面)。使用者體感 = 按「儲存」轉圈 20 秒。

### 2.2 B 段:規則層**造成**的 per-tick 成本(這才是真預算)

量測方法:以 `logs/server-20260910-0905.log` 的 backfill 行還原 09:00–09:06 的 **95 檔 / 50,942 筆**
真實 tick 分佈,依各檔速率在 300 s 市場時間上灑點、暖機 300 s 讓窗填滿後計時
(`bench_open.py` / `bench_shared.py`)。這相當於 **135 ticks/s 的開盤尖峰**。

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| B1 | 每 slot 的共用狀態推進(`_window` append + trim、`_prev`、dispatch) | `signal_state.py:317-331` | **4.16 µs/tick/slot**(窗 1501) | 實測 | **每條規則各維護一份一模一樣的 300 s 成交窗**;`limit_lock` 規則也維護一份它永遠不讀的窗 |
| B2 | `cdp_cross` 的 `_advance_rearm` + `_advance_sides`(5 線) | `signal_state.py:396-398, 433-510` | **+1.72 µs/tick/slot** | 實測(5.88 停用 vs 4.16 無基準) | **在 `enabled` gate 之前無條件跑** —— 停用的 CDP 規則照付 |
| B3 | **`_eval_volume` 的 `sum()`** | `signal_state.py:658` | **+43.3 µs/tick/slot**(窗 1501) | 實測 | 全庫唯一 **O(窗長)** 的 per-tick 運算;窗長 = `window_secs × tick 率` |
| B4 | 其餘 kind 的 gate(surge / pullback / sweep / limit) | `signal_state.py:326-331` | +0.1 … +0.7 µs/tick/slot | 實測 | `sweep_cluster` 4.30 vs 停用 4.20;`limit_lock` 4.86 |
| B5 | **開盤尖峰合計:prod 7 條規則** | `signal_hub.py:607-610` | **178.8 µs/tick ／ 2.42% 一核** | 實測 | 全部在 **event loop 執行緒** |
| B6 | 開盤尖峰:7 條**全部停用** | 同上 | **62.2 µs/tick ／ 0.84% 一核** | 實測 | **35% 的成本與 enabled 無關** |
| B7 | 開盤尖峰:**1 顆共用 detector、六 kind 全開**(等價功能的反事實) | — | **67.9 µs/tick ／ 0.92% 一核** | 實測 | 與現況同功能,**省 62%** |
| B8 | 開盤尖峰:1 顆共用 detector、**關掉 vol_burst** | — | **9.3 µs/tick ／ 0.13% 一核** | 實測 | 證明 B3 佔了 86% |
| B9 | **開盤尖峰:`MAX_RULES` 30 條** | — | **1367 µs/tick ／ 18.5% 一核** | 實測 | 單筆 tick 阻塞 loop **1.37 ms** |
| B10 | 開盤尖峰:30 條中 23 條停用 | — | **492 µs/tick ／ 6.6% 一核** | 實測 | 停用 77% 的規則只省掉 64% 的成本 |
| B11 | **全日均速**(09-10 全日 89 檔 / 51,203 筆 ≈ 3 ticks/s) | — | 7 條 48.1 µs/tick ／ **0.01% 一核**;30 條 201 µs/tick ／ 0.06% | 實測 | **平均起來完全不是問題** —— 問題全在開盤那 6 分鐘 |
| B12 | 記憶體:開盤 300 s 穩態 | — | 7 條 **38.7 MB**;30 條 **149 MB** | 實測(tracemalloc) | 283,423 / 1,214,670 個 window 條目 = 7 / 30 份同樣的窗 |
| B13 | 記憶體:`window_secs` 調到契約上界 3600 | `PARAM_SPECS` `(10, 3600)` | 穩態外推 **~2 GB** | 推估(12 × B12 的 30 條數字) | 從規則視窗按得出來的 OOM |
| B14 | Windows timer 地板 12.43 ms | — | **不適用** | — | 本段全在同步 `call_soon` 回呼內,零 sleep、零 await |
| B15 | 規則層對下單路徑的間接延遲 | — | 現況 p50 +0 / p99 **+0.18 ms**;30 條 p99 **+1.37 ms** | 推估(由 B5/B9 的阻塞塊大小推) | 下單純 Python 段 p50 ≈ 1.0 ms —— 30 條規則時訊號層可以把它翻倍 |

**怎麼讀這張表**:規則層在**平均**上便宜到不值一提(B11),在**開盤尖峰**上是 event loop 的
第二大同步佔用者(B5),而 `MAX_RULES` 允許使用者把它推到 18.5% 一核 + 1.37 ms 的單筆阻塞(B9)。
B7/B8 說明:同樣的功能,拆兩層(共用狀態 + per-rule 門檻)可以只花 38%,再修掉 B3 只花 5%。

---

## 3. 失效模式表(★ = 零錯誤訊號)

| # | 失效 | 觸發 | 症狀 | ★ | 位置 | 嚴重度 | 現在怎麼發現 |
|---|---|---|---|---|---|---|---|
| M-01 ★ | 種子規則 id 每次開機重生 | 任何一次重啟(prod 每天 1–3 次) | 同一條邏輯規則在 jsonl 裡有 N 個 `rule_id`;離線對帳 group-by 會裂開 | ★ | `signal_rules.py:456-461` `_append_seed` 的 `epoch = int(time.time())` | **high** | 現在:無。加判準 `python -c "..." | jq` 對 `data/signals/*.jsonl` 的 `(rule_name, rule_id)` 做基數檢查,> 1 即中 |
| M-02 ★ | 磁碟 v1 / 記憶體 v4 長期分離 | `load_rules` 不回寫 + 零 upsert | 規則視窗顯示 7 條、磁碟只有 4 條;「回退窗」在無人知情下開了 29 天;v3→v4 翻旗每次開機重跑 | ★ | `signal_rules.py:502-522` | medium | 現在:比對 `_cache_version` 與 `GET /rules` 筆數。應加:hub 啟動時 `logger.warning("規則檔磁碟版本 %d 落後記憶體 %d,已遷移 N 天")` |
| M-03 ★ | **編輯規則 → 該規則 per-code 狀態全清** | 任何 upsert(改名 / 勾通知 / 勾啟用 / 調參數) | 鎖漲跌停、CDP 穿越在第二筆 tick **重發一則**、`touch_count` 歸 1;在飛的爆拉回檔波**漏發** | ★ | `signal_hub.py:493` `_make_slot` 建全新 `SignalDetector` | **high** | 現在:無。加判準 = 每次 upsert 記一行 audit,盤後比對「upsert 時刻 ±10 s 內是否有同檔同 kind 重發」 |
| M-04 ★ | 停用的規則仍付 35% 成本 | 規則 `enabled=false` 但 slot 仍在迴圈裡 | 沒有症狀 —— 只是白燒 62 µs/tick(開盤) | ★ | `signal_hub.py:607`(不看 `slot.enabled` 就早退)、`signal_state.py:311, 396-398` | medium | 現在:無 loop lag 探針。加 `perf_counter` 取樣 + `/api/health` 的 `signal_eval_us_p99` |
| M-05 ★ | `MAX_RULES` 前後端漂移 | 後端調低(例如發現 30 太貴改成 12) | 前端「新增規則」按到第 13 條才拿到一句泛用 `INVALID_RULE`,畫面 title 還寫著「上限 30」 | ★ | `signal_rules.py:54` vs `useSignalRules.ts:29` | medium | 現在:**零 parity 測試**。加進 `signal_param_specs.json` 的 `max_rules` |
| M-06 ★ | `CDP_LEVELS` 前後端漂移 | 後端增減線 | 加線 → 規則視窗少一個 checkbox、使用者永遠設不到那條線;減線 → 送出即 `INVALID_RULE` | ★ | `signal_rules.py:51` vs `useSignalRules.ts:26` | low | 現在:**零 parity 測試**。同上加 `cdp_levels` |
| M-07 ★ | 影子期中途調參,事後查不出來 | 使用者在規則視窗改門檻 | jsonl 的事件母體從某一刻起換了定義,但沒有任何記號;研究 §8.2 的對照基準悄悄失效 | ★ | `signal_hub.upsert_rule` **零 logger 呼叫** | **high** | 現在:無。加一行 INFO(含 before/after diff)+ 往 `data/signals/<日>.jsonl` 寫一列 `kind="rules_changed"`(⚠ 這會違反 W1「不新增列型」,要改走獨立 `rules_audit.jsonl`) |
| M-08 ★ | 掃單簇 golden 與 prod 參數脫鉤 | 使用者改掃單簇任一參數 | `tests/live/test_signal_state.py::TestSweepClusterGolden` 照樣全綠(它讀 fixture 裡的參數),而 prod 已用別的門檻 | ★ | `test_signal_state.py:764-775` 從 fixture 讀 params | medium | 現在:無。加一條測試:prod 規則檔(若存在)的 `sweep_cluster` params == fixture params,否則 skip 並印 WARNING |
| M-09 | 規則落檔卡在共用 executor | A6 排在 TC4 歷史取數後 | 「儲存」轉圈最長 ~20 s;期間 `_rules_lock` 持有,其他 CRUD 一起卡 | 否(看得到轉圈) | `signal_hub.py:495` | medium | 現在:無 timing。加 `_save_rule` 的 elapsed log,> 1 s 印 WARNING |
| M-10 ★ | 規則變更不廣播 | 兩個分頁 / 兩台機器 | B 分頁的規則視窗顯示舊規則,照著編輯 → 撞名 `INVALID_RULE` 或覆蓋 A 剛存的 | ★ | 無 WS 廣播;`useSignalRules` 無 `refetchInterval` | low | 現在:無。低成本修法 = `refetchOnWindowFocus` 已是預設,加 `staleTime: 0` 即可;要即時就走 WS |
| M-11 | 規則檔壞掉 → 訊號層整個 503 | 斷電時 `atomic_write_text` 無 `fsync`;或手改壞 JSON | signals routes 全 503,規則視窗印「規則載入失敗」 | 否(大聲,設計如此) | `fileio.py:21-24`、`signal_rules.py:528-539` | low | 已有:`logger.error` + 前端 `rulesError` 分流空態。**這是做對的地方** |
| M-12 ★ | 30 條 + 3600 s 窗 → OOM | 從規則視窗按得出來 | process 慢慢吃到 GB 級,最後 MemoryError / 換頁抖動 | ★ | `PARAM_SPECS["vol_burst"]["window_secs"] = (10, 3600)` × `MAX_RULES=30` | **high** | 現在:無。加 `/api/health` 的 `rss_mb` + 規則存檔時的「預估窗長」提示 |
| M-13 ★ | `_seed_slot` 二次式 | 自選擴到上限 150 檔後編輯 CDP 規則 | 編輯當下 event loop 阻塞 3 ms(150 檔);若自選上限再放寬則 O(N²) | ★ | `signal_state.py:223` `self._side = {k:v for ... if k[0] != code}` | low | 現在:無。同 M-09 的 elapsed log |
| M-14 ★ | v3→v4 翻旗每次開機重跑 | M-02 的衍生 | 使用者在規則視窗把 CDP / 爆量的「通知」打開 → 那次 upsert 會落 v4 檔 → 之後黏住;但**如果只用 HTTP 直接改別的規則再改回來**,翻旗仍可能在下次開機重跑 | ★ | `signal_rules.py:483-491`、`load_rules:548` | low | 文件已知(整體 review F-30),prod 實務上零訊號。判準 = `grep "通知改為 false" logs/server-*.log`,還在印就代表磁碟還沒 v4 |
| M-15 | 種子卡撞名 / 滿 30 條被跳過 | 使用者自建同名規則,或已有 30 條 | 掃單簇種子沒進去 = **影子期零政策列** | 否(WARNING 且帶後果句) | `signal_rules.py:435-464` `_append_seed` | low | 已有:`logger.warning(... skip_note="掃單簇是政策層唯一的觸發源:種子沒進去 = 影子期零政策列")`。**這是做對的地方** |

---

## 4. Findings

### F-01 種子規則的 `rule_id` 每次開機重生(**high**,零錯誤訊號,prod 資料實證)

**位置**:`copycat/signal_rules.py:456-461`(`_append_seed`)、`:247-249`(`new_rule_id`)

```python
epoch = int(time.time())          # ← 每次 load_rules 走遷移鏈時的牆鐘
seq = len(out)
rule_id = new_rule_id(epoch, seq)  # f"r-{epoch}-{seq:03d}"
```

因為 `load_rules` **載入時不回寫**(`:513-514`),而 prod 從 2026-08-15 起沒有任何一次 upsert,
磁碟永遠是 v1;**每次開機都重跑 `_migrate_v2` / `_migrate_v3`,三張種子卡每次都拿到新的 epoch**。

**prod 實證**(`data/signals/20260911.jsonl`,同一個交易日):

```
r-1785975520-000  CDP 穿越        295   ← 磁碟上的 id,穩定
r-1785975520-001  爆拉爆跌        102
r-1785975520-002  爆量             30
r-1785975520-003  鎖漲跌停          6
r-1789088717-004  爆拉回檔 1%      90   ← 09:05 那次開機配的
r-1789088717-005  爆拉回檔 2%      49
r-1789088717-006  掃單簇           80
r-1789058168-004  爆拉回檔 1%      15   ← 00:36 那次開機配的(同一天、同一條邏輯規則)
r-1789058168-005  爆拉回檔 2%       5
r-1789058168-006  掃單簇           18
```

**影響**:
1. `_event_id`(`signal_hub.py:1690-1697`)的 docstring 寫著「決定性鍵:不依賴 process 記憶 →
   重啟後同一事件同 id」。**這個承諾在 prod 對 3/7 條規則是假的。**
2. 政策列 id `f"{trade_date}-{rule['id']}-{code}-policy-{policy}-{event.time_key}"`(`:1126`)
   同樣不穩定 —— 而政策列正是影子期四週要拿去跟研究基準對帳的那一批。
3. 離線讀者(研究目錄的 `nosig.py` 等)若以 `rule_id` 分群,同一條規則會裂成 N 桶。
   目前只能退而用 `rule_name` 當 join key —— 但名稱是使用者可改的自由文字。
4. 不會造成畫面上的重複列(`mergeSignals` 以 id 去重,而回補 tick 刻意不重放進 detector,
   所以同一顆 tick 事件不會被發兩次)。**這正是它零訊號的原因。**

**修法(三選一,依侵入性遞增)**:
- (a) **種子 id 去時間化**:`_append_seed` 改用決定性 id(例如 `r-seed-<kind>-<seq>`)。
  三行改動,不動任何跨檔契約;既有 jsonl 歷史仍留舊 id(可接受,加一行遷移 note)。
- (b) **遷移成功後回寫一次**:hub 在 `_load_or_migrate_rules` 發現 `version != _CACHE_VERSION`
  時 `save_rules` 並 `logger.info`。回退窗從「無限」縮成「這一次開機之前」——
  跑了 29 天之後,那個窗的價值已經是負的。
- (c) 兩個都做(建議):(a) 保證即使將來又有新遷移也不會再漂,(b) 讓磁碟與記憶體回到同一頁。

**風險**:改 id 生成規則會讓「規則變更前後的 jsonl 無法用 id 串起來」—— 但現況本來就串不起來。
不動任何 CLAUDE.md §4 契約(`rule_id` 不在契約清單裡)。**工作量 S。**

---

### F-02 磁碟 v1 / 記憶體 v4 已分離 29 天,遷移鏈每次開機重跑(**medium**,零錯誤訊號)

**位置**:`copycat/signal_rules.py:502-522`、`copycat/server/signal_hub.py:443-453`

`load_rules` 的 docstring:「**載入時不回寫檔案**,磁碟要到第一次 upsert 才以 v4 落檔 ——
這段就是回退窗:期間舊碼可直接讀原檔。」

設計意圖沒問題,**但沒有任何機制告訴你這個窗開了多久**。實測 prod:

- 磁碟 `data/signal_rules.json` mtime = **2026-08-15 20:21**,`_cache_version: 1`,4 條
- 記憶體 = v4,7 條(`GET /api/stock/signals/rules`)
- 三次開機的 log 各印一整輪遷移 INFO(`grep "訊號規則檔 v"`)

**衍生後果**:
- F-01(種子 id 每次重生)完全是它的衍生物。
- v3→v4 的「cdp_cross / vol_burst 通知翻 false」每次開機重跑。整體 review F-30 已記載
  「再升回 v4 碼時翻旗會重跑」,但那條寫的是「回退再升回」的情境;prod 的實況是
  **從來沒有升上去過,所以每天都在翻**。
- 對測試與量測的影響:任何以 `data/signal_rules.json` 為輸入的腳本(包括我這一輪的 benchmark)
  必須走 `load_rules` 才會拿到 prod 真相;直接 `json.load` 拿到的是 4 條 v1,
  而 `rule_config` 對它會 `KeyError 'rearm_dwell_secs'`(已實測)。

**修法**:hub `_load_or_migrate_rules` 在遷移發生時多印一行 WARNING(不是 INFO):
「規則檔磁碟版本 %d,記憶體 %d;第一次編輯規則前磁碟不會更新」。
加上 F-01(b) 的回寫就一次解決。**工作量 S。**

---

### F-03 編輯規則 = 靜默清空該規則的所有 per-code 狀態,並重發訊號(**high**,零錯誤訊號,實測復現)

**位置**:`copycat/server/signal_hub.py:455-465`(`_make_slot`)、`:493`(upsert 內)

```python
def _make_slot(self, rule: Rule) -> _RuleSlot:
    return _RuleSlot(
        rule=rule,
        detector=SignalDetector(rule_config(rule, self._cfg), now_fn=self._now_fn),  # ← 全新的
        enabled=frozenset({rule["kind"]}) if rule["enabled"] else frozenset(),
    )
```

新 detector 的 `_cooldown` / `_touch` / `_latch` / `_suppressed` / `_side` / `_window` /
`_prev` / `_pullback` / `_sweep_group` / `_sweeps` / `_lookback` **全部是空的**。
`_seed_slot` 只補 `cdp_cross` 的 `_basis`(`:517-529`)—— 其餘九份狀態沒有人補。

**實測復現**(`bench_edit.py`):

```
== 情境:10:00 鎖漲停發過一則,10:30 使用者在規則視窗把「通知」勾起來 ==
  10:00 首次鎖上                    → [('limit_lock', 'up', 1)]
  10:30 同一顆 detector,仍鎖著      → []                      (latch 擋住,正確)
  (新 detector 第 1 筆只初始化       → [])
  10:30 編輯規則後(新 detector)     → [('limit_lock', 'up', 1)]  ← 重發,touch_count 歸 1

== 同情境:cdp_cross 的 cooldown / suppressed 一併消失 ==
  10:00 穿越中軸                    → [('cdp_cross', ('cdp',), 1)]
  10:05 來回再穿一次(同一顆)        → []                      (suppressed + cooldown 擋住)
  10:05 編輯規則後(新 detector + _seed_slot 補基準) → [('cdp_cross', ('cdp',), 1)]  ← 同一條線同一天再發
```

**為什麼特別嚴重**:
1. **編輯的動機通常就是「把通知打開」** —— 於是重發的那一則會直接進 Discord + toast + 嗶 + 桌面通知。
   使用者看到的是「我剛打開通知就收到一則」,完全像是一則真訊號。
2. `signal_state.py` 的模組 docstring 花了整整一段講「狀態推進與事件產出分離(design R2):
   關掉爆拉不影響共用同一個窗的爆量;停用期間鎖上→打開的 latch 照常轉移,重開後不會補發一則
   過期的打開」。**這個設計在 detector 層做得很漂亮,卻被上一層的 `enabled` 切換路徑整個抵銷** ——
   因為切 `enabled` 走的是同一條 PUT,而 PUT 會重建 detector。
   `useSignalRules.ts:1-7` 的 docstring 甚至明說「切開關與改參數因此走同一條 PUT」。
3. 爆拉回檔的反向:在飛的波(`_pullback` entry)被清掉 → 那一波的回檔**漏發**,沒有任何訊號。
4. `touch_count` 歸 1 → rail 上的「第 n 次」在使用者眼中是有意義的資訊,重編號沒有任何提示。

**修法**(依侵入性):
- (a) **只在真的需要時重建**:`upsert_rule` 比對 `rule_config(old)` vs `rule_config(new)`,
  相等就**沿用舊 detector**、只換 `rule` 與 `enabled` 兩欄(`_RuleSlot` 是 frozen dataclass,
  `dataclasses.replace` 即可)。這一刀解決「改名 / 切通知 / 切啟用」這三種最常見的編輯 ——
  它們**完全不改 detector 的行為參數**。
  ⚠ `enabled` 切換後沿用舊狀態正是 design R2 想要的語意(「重開後不會補發一則過期的打開」)。
- (b) 參數真的變了時,把可安全移轉的狀態搬過去(`_latch` / `_cooldown` / `_touch` 三份與參數無關;
  `_window` 的內容與 `window_secs` 有關但只要重新 trim 即可)。
- (c) 至少:upsert 後印一行 WARNING 點名「規則 X 的偵測狀態已重置,可能重發」。

**驗證判準**:紅先行一條 —— 「對一條 `limit_lock` 規則只改 `name`,upsert 後餵兩筆鎖停 tick,
斷言零事件」。現在會紅。**工作量 M**(選 (a) 是 S)。

**風險**:動到 `_RuleSlot` 的建構路徑,而 `signal_rules.py:459` 的註解明說 `_make_slot` 是
「建 detector 的**唯一**入口(R5)」—— 改法要保持這一點(加一個 `_reuse_slot` 分支,不是第二個建構點)。

---

### F-04 `MAX_RULES = 30` 量化後是空頭支票(**high**,實測)

**位置**:`copycat/signal_rules.py:53-54`

```python
#: REST 可寫入的無界量要有上限(R11)—— 熱路徑是 per-tick N × evaluate。
MAX_RULES = 30
```

註解自己講對了一半。實測(開盤 300 s、95 檔、135 ticks/s 的真實分佈重放):

| 配置 | µs/tick | % 一核 | 記憶體 | window 條目 |
|---|---|---|---|---|
| prod 7 條 | **178.8** | 2.42% | **38.7 MB** | 283,423 |
| 7 條全部停用 | 62.2 | 0.84% | — | — |
| 1 顆共用 detector、六 kind 全開 | 67.9 | 0.92% | — | — |
| 1 顆共用 detector、關 vol_burst | 9.3 | 0.13% | — | — |
| **`MAX_RULES` 30 條** | **1367.2** | **18.47%** | **149.3 MB** | 1,214,670 |
| 30 條中 23 條停用 | 491.6 | 6.64% | — | — |

**三個推論**:
1. **單筆 tick 阻塞 event loop 1.37 ms**。`_handle_quote` 走
   `stock_engine.py:1150 loop.call_soon_threadsafe`,所以這 1.37 ms 是**不可搶佔的 loop 阻塞**,
   直接疊在下單 route、WS 心跳、capital 回報上。下單的純 Python 段 p50 ≈ 1.0 ms ——
   30 條規則時訊號層可以把它翻倍(p99)。
2. **停用不便宜**:23 條停用只從 18.5% 降到 6.6%。對應 §3 的 M-04。
3. **記憶體是第二條軸**,而且比 CPU 更難救:30 條 × `window_secs=3600`(契約上界)的穩態
   外推 **~2 GB** —— 這是一個**從規則視窗按得出來的 OOM**。
   上一輪 B06 的 F-07 已經指出 CPU 面(25 ms/tick),**記憶體面是這一輪新增的**。

**修法**:
- 短期(不動契約):`MAX_RULES` 從 30 降到 **實測撐得住的數字**。以「開盤尖峰不超過 5% 一核」
  為預算 → 7–8 條。以「單筆阻塞 ≤ 0.5 ms」為預算 → 11 條。
  ⚠ **這是跨語言契約的一半**(`useSignalRules.ts:29`),要同動,而且目前**沒有 parity 測試**(見 F-05)。
- 中期:上一輪 B06 F-01(vol_burst running sum)+ F-02(detector 拆兩層)。
  B7/B8 的反事實說明:兩者都做之後,30 條的成本會落在**現況 7 條的一半以下**,
  `MAX_RULES = 30` 才真的兌現。
- 要 user 拍板:`signal_rules.py` 的模組 docstring 把「一條規則 = 一顆 detector」寫成設計決定,
  拆兩層 = 改這個決定。

---

### F-05 parity 只釘了一半:`MAX_RULES` / `CDP_LEVELS` / 錯誤碼零 parity 測試(**medium**,零錯誤訊號)

**現況(今天跑過,兩邊全綠)**:

```
$ .venv/Scripts/python -m pytest tests/test_signal_rules.py -q     → 188 passed
$ npx vitest run src/lib/signal-param-parity.test.ts               → 6 passed
```

`tests/fixtures/signal_param_specs.json` 釘住三樣:`specs`(六 kind 的鍵集 + 值域)、
`int_keys`、`cooldown`。前端 `PARAM_FIELDS` 的鍵集因為型別是
`Record<RuleKind, readonly ParamField[]>`,**`RULE_KINDS` 是被 fixture 的 `specs` 鍵集傳遞性釘住的**
(前端 parity 測試第二條 `expect(actual).toEqual(fixture.specs)` 會比鍵集)。這部分做得很好。

**沒被釘住的三樣**:

| 常數 | 後端 | 前端 | 漂掉的樣態 |
|---|---|---|---|
| `MAX_RULES` | `signal_rules.py:54` = 30 | `useSignalRules.ts:29` = 30 | 後端降到 12 → 前端「新增規則」按鈕到第 30 條才 disable,第 13 條起拿到泛用 `INVALID_RULE`,而 `title` 還寫「上限 30 條」。**這就是 N055 修掉的那個樣態,只是換了一個常數** |
| `CDP_LEVELS` | `signal_rules.py:51` 5 值 tuple | `useSignalRules.ts:26` 5 值 as const | 後端加線 → 規則視窗少一個 checkbox,使用者永遠設不到;後端減線 → 送出即 `INVALID_RULE` |
| 錯誤碼 | `RuleError` 值域 `{INVALID_RULE, RULE_NOT_FOUND}` + `app.py` 的 `RULE_SAVE_FAILED` | `errText()` 三碼 | 新增碼 → 前端 fallback「儲存失敗」。已有 fallback,**最輕的一個** |

**修法**:`signal_param_specs.json` 加三個鍵 `"max_rules": 30`、`"cdp_levels": [...]`、
`"error_codes": [...]`,兩邊各加一條斷言。與既有 parity 測試同形,**工作量 S**。
⚠ 加 fixture 鍵要同步更新 fixture 的 `_note`(它是契約說明的唯一出處)。

**注意 F-04 與 F-05 有依賴**:若先做 F-04 的「降 `MAX_RULES`」而沒有 F-05 的 parity,
就是親手製造 M-05。**F-05 必須先於 F-04 的短期修法。**

---

### F-06 `enabled` 的成本語意與設計意圖相反(**medium**,實測)

**位置**:`signal_hub.py:607-610`、`signal_state.py:311, 396-398`

```python
for slot in self._slots.values():        # ← 不看 slot.enabled
    events = list(slot.detector.evaluate(code, tick, ctx, slot.enabled))
```

`evaluate` 內的三段狀態推進在 `enabled` gate **之前**:
- `:311` `sweep_events = self._eval_sweep(...)` —— 在「首 tick 只初始化」gate 之前
- `:317-323` `_window` append + trim + `_prev`
- `:396-398` `_eval_cdp` 的 `_advance_rearm` + `_advance_sides`

這些在 detector 層是**刻意的、正確的**(design R2:停用期間狀態照走,重開後不補發、方向不反)。
問題是:**per-rule detector 讓「刻意的狀態推進」變成「N 份重複的刻意狀態推進」**。

實測代價:
- 7 條全停用 = **62.2 µs/tick(開盤)**,是全開 178.8 µs 的 **35%**
- 單條停用的 `cdp_cross`(有基準)= **5.88 µs/tick** vs 沒有基準的 4.16 → **1.72 µs 純死工**
- 30 條中 23 條停用仍要 491.6 µs/tick

上一輪 B06 抓到的「`_distribute`(`signal_hub.py:980-988`)只看 kind 不看 `enabled`」是同一件事的
**觸發端**:停用的 CDP 規則照樣收到基準 → `_eval_cdp` 的 `basis` 非空 → 每 tick 跑兩圈 5 線。

**修法**:
- (a) `_distribute` 與 `_seed_slot` 加 `if not slot.enabled: continue` —— **三行,省 1.72 µs/tick/停用CDP規則**。
  ⚠ 要配套:規則從停用切回啟用時必須補基準(現在 upsert 重建 detector 順便解決了,
  但如果做了 F-03(a) 的「沿用舊 detector」就必須明確補一次 `_seed_slot`)。**兩個 finding 有耦合。**
- (b) `on_tick` / `on_book` 迴圈跳過 `not slot.enabled` 的 slot —— **會改變行為語意**
  (停用期間狀態不推進 → 重開後可能補發一則過期的鎖停打開),與 design R2 直接衝突。
  **不建議單獨做**;正解是 F-04 的拆兩層(共用一份狀態推進 + per-rule 門檻),
  那樣停用的規則自然只省掉它自己的 gate,而狀態推進本來就只有一份。

---

### F-07 規則 CRUD 零 log、零審計(**high**,零錯誤訊號,量化缺口)

**位置**:`copycat/server/signal_hub.py:468-515`

`upsert_rule` / `delete_rule` 全程**沒有任何 `logger` 呼叫**,唯一的例外是
`:485 logger.warning("規則數已達上限 %d,拒絕新增")`。`server/audit.py` 只服務下單。

**為什麼這對量化系統是硬傷**:spec #192 的影子期是**四週**,對照基準是 repo 外一份
無版控的研究腳本。這四週裡任何一次「把掃單簇的 `min_sweeps` 從 2 調成 3」都會讓
`data/signals/*.jsonl` 的事件母體從某一刻起換定義,而:
- jsonl 列上只有 `rule_id` + `rule_name`,**沒有參數快照**
- `rule_id` 本身還不穩定(F-01)
- 沒有任何一行 log 說「10:47 有人改了規則」
- 磁碟規則檔會被覆寫,**改之前的參數就此消失**(`save_rules` 是 `os.replace`,無版本)

事後對帳時,你會看到事件密度在某一天變了,而**沒有任何辦法知道是市場變了還是門檻變了**。

**修法**(建議全做,都是 S):
1. `upsert_rule` / `delete_rule` 各加一行 INFO:`"訊號規則 %s:%s → %s"`(`_rule_tag` 已存在)。
2. 落一份 **`data/signals/rules_audit.jsonl`**:`{ts, action, rule_before, rule_after}`。
   ⚠ **不要寫進 `data/signals/<日>.jsonl`** —— CLAUDE.md §4「T+1/T+2 回填原地補欄 + 離線讀者契約」
   的 W1 明文要求「不新增列型、每列 `kind` 恆在」,研究目錄的離線讀者逐列讀 `s["kind"]` 無防禦。
3. `save_rules` 前把舊檔複製成 `signal_rules.<epoch>.bak`(保留最近 N 份)。

---

### F-08 掃單簇 golden fixture 與 prod 參數脫鉤(**medium**,零錯誤訊號)

**位置**:`tests/live/test_signal_state.py:764-775`

```python
def _run(self, case: dict, params: dict) -> ...:
    det = _det(clock,
        sweep_cluster_window_secs=float(params["cluster_window_secs"]),   # ← 讀 fixture
        sweep_min_sweeps=int(params["min_sweeps"]), ...)
```

`TestSweepClusterGolden` 鎖的是「**在拍板參數下**,線上 `_eval_sweep` 的事件集合 ==
研究 `combo_events.py` 的 `expected_prefix`」。這是對的 —— 它釘住的是**定義**。

但使用者在規則視窗把掃單簇的五個參數任何一個改掉之後:
- 測試照樣全綠(它用 fixture 的參數,不是 prod 規則檔的)
- prod 的事件母體已經不是研究基準的那一組
- 而政策層(P / B-a / B-b / S)**唯一的觸發源就是掃單簇事件**

CLAUDE.md §4 對這條契約的描述是「掃單簇**定義**另由研究 golden fixture 釘住」——
**定義釘住了,實例沒有。**

**修法**:加一條測試(或啟動時的自檢),若 `data/signal_rules.json`(經 `load_rules`)存在
`sweep_cluster` 規則且其 params ≠ fixture 的 params,印 WARNING
「線上掃單簇參數已偏離研究基準,影子期對帳需重算」。測試環境沒有那個檔就 skip。**工作量 S。**

---

### F-09 `_seed_slot` / `set_basis` 是 O(檔數 × `_side` 條目)的二次式(**low**,實測)

**位置**:`copycat/live/signal_state.py:222-223`

```python
def set_basis(self, code: str, cdp: dict[str, int] | None) -> None:
    self._basis[code] = dict(cdp) if cdp else None
    self._side = {k: v for k, v in self._side.items() if k[0] != code}   # ← O(全部條目)
```

`_seed_slot`(`signal_hub.py:524-529`)對每一個有基準的檔呼叫一次 → O(N_codes × 5·N_codes)。

實測(每檔 5 線):

| 自選檔數 | `_side` 條目 | `_seed_slot` 迴圈 |
|---|---|---|
| 50 | 250 | **0.382 ms** |
| 90 | 450 | **1.190 ms** |
| 150(`WATCHLIST_LIMIT`) | 750 | **3.048 ms** |

在 event loop 上、`_rules_lock` 內。現況 3 ms/次、一天幾次 —— **不是效能問題**,
但形狀是二次式,而 `WATCHLIST_LIMIT` 是個會被調的常數(2026-08-13 從 50 調到 150)。

`drop_code`(`:275-288`)有同樣的形狀(四份 dict 各 rebuild 一次),
150 檔 × 7 slots = **1.11 ms**,同樣在 loop 上。

**修法**:`_side` 改成兩層 `dict[str, dict[str, tuple[int,int]]]`(code → level → ...),
刪除變成 `self._side.pop(code, None)`。`_cooldown` / `_touch` / `_latch` 同形。
**這會動到 `signal_state.py` 的內部資料結構,但不動任何公開簽名或契約** ——
是乾淨的 🔵 純重構。**工作量 M**(要補 characterization,`reset_day` / `drop_code` /
`set_basis` 三條路都要釘住)。

---

### F-10 規則變更不廣播,多分頁會看到舊規則(**low**,零錯誤訊號)

**位置**:`frontend/src/hooks/useSignalRules.ts:68-70`、唯一呼叫點 `StockPage.tsx:95`

```ts
export function useSignalRules() {
  return useQuery({ queryKey: RULES_KEY, queryFn: fetchRules, retry: 1 });
}
```

沒有 `refetchInterval`,後端也沒有把規則變更推上 `/ws/stock`。
A 分頁改了規則,B 分頁的 `SignalRulesDialog` 顯示的是舊列表;B 照著編輯 →
撞名 `INVALID_RULE`,或以舊 payload PUT 覆蓋掉 A 剛存的改動(**後寫者贏,零提示**)。

實務上 user 只開一個分頁,所以是 low。但「看盤日常是 prod build + 常開整天」(CLAUDE.md §1)
的場景下,一天之內開兩個視窗並不罕見。

**修法**:最低成本是 `staleTime: 0` + 依賴 `refetchOnWindowFocus`(TanStack Query 預設開)
—— 切回分頁就重抓。要即時就在 `/ws/stock` 加一則 `{"type":"rules_changed"}`
(⚠ 那會是新的跨檔契約,前端 `useStockStream` 的 `default` 分支會靜默丟棄舊 dist,要同版部署)。

---

## 5. 不要動(反向結論)

| 項目 | 位置 | 理由 |
|---|---|---|
| **`RuleBody` 全欄 `object` + 預設 None** | `app.py:234-258` | 這是守住 `{"detail":{"error":code}}` 全站錯誤契約的唯一辦法。宣告成 `bool`/`int` 會讓 pydantic 把 `"yes"`/`"3"` 寬鬆轉型;宣告成必填會回 422 + list 形 detail。註解已把兩種後果寫清楚。**看起來像「沒用型別」,其實是最貴的一課。** |
| **`_normalize_params` 的鍵集**精確**相等檢查** | `signal_rules.py:164-165` | `set(raw) != set(spec)` → `INVALID_RULE`。這一條讓「後端加了參數鍵但前端沒跟」變成**大聲失敗**(送出即拒),而不是靜默套 detector 預設。前端 `PARAM_FIELDS` 漂掉時使用者立刻知道。這是全庫少數把漂移做成 loud 的地方。 |
| **`normalize_rule` 是純函式、冪等、188 條測試** | `signal_rules.py:199-244` + `tests/test_signal_rules.py` | 今天跑過 188 passed / 0.60 s。值域、bool 先擋(`_as_int` 的 `isinstance(value, bool)`)、NaN 走 `not lo <= n <= hi`(比較恆 False)、名稱唯一性排除自身 —— 每一條都有對應測試。**不要為了效能碰它(2.48 µs,一天跑幾次)。** |
| **`_append_seed` 的撞名 / 滿載 WARNING 帶後果句** | `signal_rules.py:435-464` | `skip_note="(掃單簇是政策層唯一的觸發源:種子沒進去 = 影子期零政策列)"`。這是全庫 log 品質的天花板 —— 盤後 grep WARNING 看得到後果,不用回頭讀碼。 |
| **`_MIGRATE_QUIET_KINDS` 與 `_QUIET_KINDS` 分開寫** | `signal_rules.py:111-115` | 註解自陳:掃單簇在 v3 檔不存在,把它放進翻旗集合是「順手」,哪天這段拿去對 v4+ 檔用就會把使用者開回的通知靜默再關掉。**這是對「順手」的正確抵抗。** |
| **`load_rules` 的「空陣列 ≠ 缺檔」** | `signal_rules.py:503-507` | 使用者刪光規則後重啟不得復活預設。這個區別如果拿掉,「我明明把規則都刪了」會在每次重啟變成「又全回來了」。 |
| **共用 golden fixture 的 parity 形狀** | `tests/fixtures/signal_param_specs.json` + 兩側各一條斷言 | 「兩邊各自對 fixture 斷言,改壞任一邊只有那一邊紅」—— 這比「後端測試直讀前端原始碼字面」乾淨。**要擴充(F-05)就照這個形狀擴,不要另開第二種。** |
| **`save_rules` 的 OSError 往外拋** | `signal_rules.py:566-579` | 「吞掉這裡的失敗會讓畫面顯示新規則、重啟後跳回舊的(記憶體不得先於落檔更新)」。`upsert_rule` 的順序(驗證 → 落檔 → swap)是對的。 |
| **`_seed_slot` 只補 cdp_cross 基準** 這件事本身 | `signal_hub.py:517-529` | 補基準這半邊是對的(沒有它 CDP 會停到隔天)。問題在**另外九份狀態沒補**(F-03),不是這一段寫錯。修 F-03 時要保留這段的語意。 |
| **`atomic_write_text` 沒有 `fsync`** —— 對規則檔而言可接受 | `fileio.py:21-24` | 規則檔不是錢。斷電後壞檔 → `load_rules` raise → hub None → signals routes 503 + 規則視窗印「規則載入失敗」,**大聲**。這與 `server/audit.py` 的下單審計(B10 的 finding)是完全不同的風險等級,不要把那邊的結論套過來。 |
| **`_eval_volume` 之外的五個 `_eval_*`** | `signal_state.py` | 實測全部 ≤ 0.7 µs/tick 的邊際成本(`sweep_cluster` 4.30 vs 停用 4.20)。`_eval_sweep` 的 O(1) 前綴重算、`_eval_pullback` 的 `rearm_base` O(1) 化(review F-02)都已經做過了。**這一層已經寫對了,不要再優化。** |

---

## 6. 改造順序 + 量測判準

| # | 做什麼 | 為什麼排這裡 | 工作量 | 怎麼量才算改對了 | 改壞了怎麼退 |
|---|---|---|---|---|---|
| 1 | **加 loop 佔用探針**:`on_tick` 前後 `perf_counter`,per-tick 耗時進一個 reservoir,`/api/health` 掛 `signal_eval_us_{p50,p99,max}` + `signal_slots` | **先量後改**。整個系統零效能儀器,現在所有數字都是我在 harness 裡重放出來的,沒有一個是 prod 實測 | S | 開盤後 `curl -s localhost:8721/api/health \| jq .signal_eval_us_p99`;09:00–09:06 的 p99 應落在 **150–400 µs**(與我的 178.8 µs/tick 開盤實測同量級)。差一個數量級 = 我的重放模型錯了,先修模型再往下 | 移除三行 + health 欄;零行為改動 |
| 2 | **F-05 parity 補齊**:fixture 加 `max_rules` / `cdp_levels` / `error_codes`,兩側各加一條斷言 | **必須先於第 3 步**。第 3 步要改 `MAX_RULES`,沒有 parity 就是親手製造 M-05 | S | 後端 `pytest tests/test_signal_rules.py -q` 全綠;前端 `npx vitest run src/lib/signal-param-parity.test.ts` 全綠;**突變驗證**:把 `useSignalRules.ts:29` 改成 29 → 前端 parity 必紅、後端必綠(證明「改壞哪邊只有哪邊紅」) | revert fixture + 兩條測試 |
| 3 | **F-01 + F-02**:`_append_seed` 用決定性 id;hub 遷移後回寫一次 + WARNING | id 穩定是影子期對帳的前提,越早越好(每多跑一天就多一組孤兒 id) | S | 重啟兩次,`GET /api/stock/signals/rules \| jq -r '.rules[].id'` 兩次逐字相同;`grep "訊號規則檔 v" logs/server-*.log` 在**第二次**重啟後為 0 行;`cat data/signal_rules.json \| jq ._cache_version` == 4、`.rules \| length` == 7 | 停 server,把 `data/signal_rules.json` 換回備份的 v1 檔(改造前先複製一份) |
| 4 | **F-07 規則審計**:upsert/delete 各一行 INFO + `data/signals/rules_audit.jsonl` + 落檔前備份 | 影子期還在跑;每晚一天,中途調參就多一天查不出來 | S | 在規則視窗改一個參數再改回來 → `wc -l data/signals/rules_audit.jsonl` == 2、每列含 `rule_before`/`rule_after`;`ls data/signal_rules.*.bak \| wc -l` ≥ 2;**確認沒寫進當日 jsonl**:`grep -c '"kind": "rules' data/signals/<今日>.jsonl` == 0(W1 契約) | 刪 audit 寫入(純 additive,不影響既有路徑) |
| 5 | **F-03 upsert 不重建 detector**(參數未變時沿用舊 slot) | 這是唯一會**產生假訊號**的一條。排在 1/2 之後是因為要先有探針與 audit 才驗得出「改了之後真的不再重發」 | S–M | 紅先行:對 `limit_lock` 規則只改 `name`,upsert 後餵兩筆鎖停 tick,斷言 **零事件**(改前紅、改後綠)。真環境:盤中對一條有鎖停在身的規則切一次「通知」,`grep '"kind": "limit_lock"' data/signals/<今日>.jsonl` 在 upsert 時刻 ±30 s 內**零新列**;Discord 零新卡 | `_make_slot` 恆重建(現行為)是一行 fallback |
| 6 | **F-06(a)**:`_distribute` / `_seed_slot` 跳過 `not slot.enabled` | 便宜、與第 5 步同一個檔區。**必須在第 5 步之後**:沿用舊 detector 後,停用→啟用的切換要明確補一次 `_seed_slot` | S | 紅先行:停用一條 CDP 規則,`request_basis` 後斷言該 slot 的 `detector._basis` 為空;再啟用 → 斷言基準補回。效能:第 1 步的 `signal_eval_us_p99` 在「有停用 CDP 規則」時應下降 ~1.7 µs × 停用條數 | 移掉兩個 `continue` |
| 7 | **上一輪 B06 F-01**:`_eval_volume` 的 `sum()` 換成增量維護的 running total | 這是單點最大的一刀(43.3 → ~0.05 µs/tick/slot)。排在這裡是因為它會**改變第 8 步的預算**,要先落地再重新算 `MAX_RULES` | M | 紅先行 = 既有 `vol_burst` 測試全綠 + 一條新的「窗頭 popleft 後 running total 與 `sum()` 逐筆相等」性質測試(至少 1000 筆隨機序列)。效能:`bench_micro.py` 的「vol_burst enabled @ 窗 1501」從 **47.5 µs → < 6 µs**;prod `signal_eval_us_p99` 開盤應從 ~180 µs 掉到 **< 60 µs** | 保留舊 `sum()` 路徑在旗標後(一輪即刪) |
| 8 | **F-04 短期修法**:依第 7 步後的實測重設 `MAX_RULES`(連同 fixture + 前端) | 要等第 7 步的實測才知道該設多少。**預算式**:開盤尖峰 ≤ 5% 一核 且 單筆阻塞 ≤ 0.5 ms | S | 重跑 `bench_open.py` 取新的 µs/tick,解 `N × per_slot ≤ 0.5 ms`;設定後在規則視窗按到第 N+1 條 → 按鈕 disable 且 `title` 印新數字;`pytest` + `vitest` parity 兩邊綠 | 三處同時改回 30 |
| 9 | **F-08**:掃單簇參數偏離研究基準的啟動自檢 WARNING | 影子期結束前要有。排在 8 之後只因它獨立、不阻塞任何人 | S | 手動把掃單簇 `min_sweeps` 改成 3 重啟 → `grep "偏離研究基準" logs/server-*.log` 恰一行;改回 2 重啟 → 零行 | 移除自檢(純 log) |
| 10 | **F-04 中期 / 上一輪 B06 F-02**:detector 拆兩層(共用狀態推進 + per-rule 門檻) | 最大的一刀,也是唯一要 **user 拍板**的一刀(改 `signal_rules.py` 模組 docstring 寫死的設計決定) | L | 判準 = `bench_shared.py` 的 B7 行:開盤尖峰 **178.8 → ≤ 70 µs/tick**(做完第 7 步後 → ≤ 12 µs);記憶體 **38.7 → ≤ 8 MB**;`tests/live/test_signal_state.py::TestSweepClusterGolden` **必須仍綠**(它是掃單簇定義的唯一鎖);`copycat validate` 全 PASS | 分支整個丟掉(這一步不做增量遷移,一次到位或不做) |

---

## 7. 工具評估

| 工具 | 用在哪 | 為什麼 | 代價 | 結論 |
|---|---|---|---|---|
| `perf_counter` + 固定大小 reservoir(stdlib) | `signal_hub.on_tick` / `on_book` 外圈 | 系統零效能儀器,規則層的所有數字現在都是 harness 重放。**兩次 `perf_counter` ≈ 0.06 µs,佔 178 µs 的 0.03%** | 每 tick 兩次呼叫 + 一次 list 寫入 | **建議導入**(fix_plan #1) |
| `tracemalloc` 週期快照 | ops 腳本,不是常駐 | F-04 的記憶體軸目前只有我的 harness 數字,沒有 prod 實證;`tracemalloc` 常駐會讓分配變慢 3–10× | 只在手動診斷時開 | **有條件導入**:寫成 `python -m copycat.tools.memsnap` 之類的一次性腳本,不進 server |
| `psutil`(取 RSS 給 `/api/health`) | `/api/health` 加 `rss_mb` | M-12 的 OOM 需要一個可 grep 的早期訊號;`psutil.Process().memory_info().rss` ~20 µs,每次 health 才呼叫一次 | **新增一個 runtime 依賴** —— 違反 `dependencies = []` 的 stdlib-only 紀律 | **不建議**:Windows 上可用 `ctypes` 打 `GetProcessMemoryInfo`,或直接讀 `sys.getallocatedblocks()` 當代理。要 user 拍板才加依賴 |
| `pydantic` 的 `model_config = ConfigDict(extra="forbid")` | `RuleBody` | 讓「body 帶了拼錯的欄名」從「靜默忽略 → 該欄變 None → 泛用 INVALID_RULE」變成明確的 422 | 422 的 detail 是 list 形,**破壞全站 `{"detail":{"error":code}}` 契約** —— 正是 `RuleBody` 全欄 `object` 想避免的 | **不建議**。要做就自己在 `payload()` 裡比對鍵集並 raise `RuleError("INVALID_RULE")` |
| `hypothesis`(property-based testing) | `normalize_rule` 的冪等性 / 值域 | 現有 188 條是 example-based;`normalize_rule` 是純函式、冪等,是 property test 的教科書對象 | dev 依賴 +1(不進 runtime);學習成本 | **有條件導入**:若之後真的要動 `normalize_rule`(目前建議不動),它是最好的安全網。現在不做 |
| `orjson` / `msgspec` 取代 `json.dumps` | `save_rules` | **完全不值得**:`save_rules` 一天跑幾次、實測 0.56–0.79 ms,而且大部分是磁碟不是編碼 | 新增 runtime 依賴 | **不建議**(頻率不對) |
| `numpy` 取代 `_window` deque | `signal_state` | 上一輪已駁回:`_apply` 1.96 µs/tick、增量式、穩態零配置。這一輪的 `_eval_volume` 問題是 **O(窗長)的演算法形狀**,不是常數項 —— running total 就是正解,numpy 只會更慢 | — | **不建議**(形狀不對;上一輪 `_REFUTED` 已記) |
| `watchdog` / 檔案監看 讓規則檔外部改動自動生效 | `signal_rules.json` | 想解 F-10 的多分頁問題 | 新增依賴;而且「外部改檔自動生效」會與 `_rules_lock` 的臨界區打架,是新的競態來源 | **不建議**。F-10 用 `staleTime: 0` 就夠 |

---

## 8. 尚未釐清的問題

1. **`MAX_RULES` 的預算式該用哪一條?** 「開盤尖峰 ≤ X% 一核」還是「單筆 tick 阻塞 ≤ Y ms」?
   後者直接對應下單延遲(這是要下實單的系統),但前者才是持續佔用。**要 user 拍板 X / Y。**
2. **F-03 的修法要做到哪一層?** (a) 只在 `rule_config` 相等時沿用舊 detector(解決 90% 的真實編輯),
   還是 (b) 連參數變更也搬移 `_latch`/`_cooldown`/`_touch`?(b) 的語意需要拍板:
   「把爆量門檻從 3 倍調成 2 倍」之後,原本 30 分鐘的冷卻該不該保留?
3. **遷移後回寫(F-01(b))會關掉回退窗。** 跑了 29 天之後這個窗還有價值嗎?
   我的判斷是沒有,但這是 user 的部署紀律問題,不是我的。
4. **影子期(spec #192,2026-09-08 起四週)期間可以動這一區嗎?**
   F-01 / F-03 / F-07 都會改變 jsonl 的內容或時序。影子期到 2026-10-06 —— 是要等,
   還是「先做 F-07(純 additive 審計)其餘等」?**要 user 拍板。**
5. **`data/signal_rules.json` 沒有備份也不進版控。** 若它壞掉,7 條規則的參數就只剩
   log 裡的種子卡 INFO 行可以還原(而磁碟上那 4 條的參數沒有任何 log)。
   要不要把它(或一份 sanitized 版本)進版控?
6. **`_side` / `_cooldown` / `_touch` / `_latch` 改兩層 dict(F-09)** 與
   **detector 拆兩層(F-04 中期)** 有沒有重疊?若拆兩層會整個重寫狀態持有方式,
   F-09 就白做。**建議先決定 F-04 中期做不做,再決定 F-09。**
7. **開盤尖峰的真實 tick 速率我只有回補行的還原值**(09:00–09:06 平均 135 ticks/s)。
   前 10 秒的瞬時峰值可能高一個數量級,而那正是最該量的一格 —— 第 1 步的探針落地後
   才會有答案。
