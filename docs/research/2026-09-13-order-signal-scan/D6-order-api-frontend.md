# D6 — 下單:HTTP/API 層與前端下單路徑 架構/效能掃描報告

> 區塊:`copycat/server/capital_api.py` + `frontend/src/hooks/useCapital.ts` +
> 三座閃電梯(`PriceLadder` / `StkfutLadder` / `FuturesLadder`)+ `OrderPanel` +
> `components/capital/*` + `lib/flash-*` / `qty-quick` / `close-order` / `trade-text` / `api-error`
> 掃描日期:2026-09-13 · 目標:**「按鈕按下去到 HTTP request 離開瀏覽器」與「HTTP 進來到
> 呼叫 CapitalClient」這兩段**,以及讀取面(輪詢 / invalidate)的實際負載。
>
> 所有數字標 **[實測]** 或 **[推估]**。實測腳本留在本目錄:
> `bench_routes.py`(route 端到端,in-process TestClient)、`bench_post.py`(POST route + pydantic)、
> `bench_localhost.py`(loopback 一跳底噪)、`bench_mutate.mjs`(真 query-core 5.101.2 的
> mutate→fetch 相位)、`bench_click.mjs`(clickPrice 同步段成分)、`access_rate.py`(access log 統計)。
> **本輪沒有啟動 server、沒有送出任何單(POST 基準用 stub client 取代 `submit_*`)。**

---

## 0. 一句話結論

**這一段程式碼本身快到不值得優化**:從 `onClick` 進來到 `fetch()` 被呼叫,全部 JS 工作
合計 **≈ 2 µs** [實測];HTTP 進來到呼叫 `CapitalClient` 的 route 層工作 **≈ 0.06 ms** [實測]。
整條送單鏈 **E[總耗時] ≈ 76 ± 12 ms** [實測,499 筆審計配對自行重算],其中 route + 前端
佔不到 **0.1%**。

真正的問題全在別的軸上:

1. **讀取面 59–63% 的 HTTP 請求是 capital 輪詢**,而寫入面只佔 0.10–0.25% [實測]。
2. **`/ws/capital` 的 `capital_position` 只送 `{count}`,不送資料**(本輪任務陳述的前提
   「拿的是已經推播出去的同一份資料」**為假**,見 §4)—— 所以 REST 現在真的是唯一資料通道。
3. **下單結果的三種語意裡有兩種在畫面上沒有讀者**:券商拒單理由(`err_msg`)、
   「結果未知,勿重送」(`OrderResult.ok === false` 的 200)。兩條都零錯誤訊號。
4. **`new QueryClient()` 零預設值** → `networkMode: "online"` 生效 →
   `navigator.onLine === false` 時送單 **不是失敗而是「暫停」**,恢復連線後自動補送。
   在「server 就在同一台機器」的架構下,這是最危險的一條靜默路徑。

---

## 1. 架構地圖(這一段實際怎麼運作)

### 1.1 寫入面(六個送單入口 → 六支 POST)

```
[武裝路徑 — 無確認窗]                        [確認窗路徑]
PriceLadder.clickPrice / marketOrder         CapitalOrdersList.OrderRow(刪/改/減)
StkfutLadder.clickPrice / marketOrder        CapitalPositionsList.confirm(平倉)
FuturesLadder.clickPrice / marketOrder       FuturesLadder.confirmClose(一鍵平倉)
   └ arm.state.armed 必須為真                OrderPanel.handleConfirm(TXO 表單)
   └ 同格/同鈕 500 ms 防抖                      └ CapitalConfirmDialog(原生 <dialog> showModal)
[無確認窗、無武裝檢查]
PriceLadder.cancelLot / StkfutLadder.cancelLot / FuturesLadder.cancelLot / cancelAll
   └ for (const seq of seqs) cancelOrder.mutate(...)   ← N 筆並發、零上限
        │
        ▼  hooks/useCapital.ts::useCapitalMutation → fetchJson(POST)
   JSON.stringify(body)  →  fetch(url, {method:"POST", headers:{Content-Type: application/json}})
        │                    ★ 無 signal / 無 timeout / 無 keepalive
        ▼
   瀏覽器 ── vite preview(Node,4173)── proxy ──▶ uvicorn 127.0.0.1:8721
        │       (CLAUDE.md §1 看盤日常;preview.proxy 預設沿用 server.proxy)
        ▼
   server/capital_api.py
     ├ pydantic BaseModel 驗形(StockOrderBody / FutureOrderBody / CancelBody / …)
     ├ _capital(request)  = app.state.capital 屬性讀(None → 503 CAPITAL_DISABLED)
     ├ [order/future]  product_of → _stkfut_gates(lookup_product + tick 閘)
     │                  → multiplier_of → futures.resolved_contract(dict get)
     │                  → to_exchange_symbol
     ├ [correct-price fut] _correct_price_tick_gate → client.store.orders()  ★ 全表建構 + 持鎖
     ├ [position/close fut] _close_tick_gate
     └ → frozen dataclass → await client.submit_* / cancel_* / close_position
        │
        ▼  (以下屬 B10,不重述)  gate → 前置審計 to_thread → _cmd_q → COM 執行緒 → SendStockOrder
        ▼
   回程:dataclasses.asdict(OrderResult) → FastAPI response field(`-> dict`)
         → pydantic-core dump_json → JSONResponse → 兩跳 proxy → fetch resolve
        │
        ▼
   settleFlashSend(兩參數 then)→ dispatch send_ok/send_fail → showHint → setState
   useCapitalMutation.onSuccess → invalidate ["capital-orders"] + ["capital-positions"]
```

### 1.2 讀取面(四支 GET + 一條 WS)

```
App.tsx:159  useCapitalStream()   ← 全 app 唯一擁有者
   ├ useQuery(positionsQueryOptions(15_000))   ← 部位輪詢的唯一節奏擁有者(N068)
   ├ useQuery(fillsQueryOptions(30_000))       ← 成交輪詢的唯一節奏擁有者
   └ connectWithRetry(/ws/capital)
        onMessage → emitCapitalEvent → 全域 listener set
                  → EVENT_QUERY_KEY 查表 → scheduleInvalidate(200 ms trailing debounce)
                       capital_order    → ["capital-orders", "capital-fills"]
                       capital_position → ["capital-positions"]
                       capital_status   → (無對應 key,只更新 module store 的 wsStatus)

讀取端(refetchInterval: false,被動吃 invalidate):
   useCapitalPositions  ← PriceLadder / StkfutLadder / FuturesLadder / CapitalPositionsList
   useCapitalFills      ← PriceLadder / StockChart / GroupGridView / FuturesChart
   useCapitalOrders     ← PriceLadder / StkfutLadder / FuturesLadder / CapitalOrdersList
                          ★ 但本身帶 refetchInterval: 30_000(沒收斂到 stream,與 positions/fills 不同)
   useCapitalStatus     ← OrderPanel / CapitalOrdersList / CapitalPositionsList
                          ★ 帶 refetchInterval: 10_000 且**每個 observer 各一份**(沒收斂)
```

`/ws/capital` 的實際 payload(`capital/client.py:430 / 446 / 672 / 316`):

| event | data | 大小 |
|---|---|---|
| `capital_position`(樂觀套用)| `{count, source:"fill"}` | ~40 B |
| `capital_position`(回查鏈落地)| `{count}` | ~25 B |
| `capital_order` | `{seq_no, stock_no, market, status_label, price, qty}` | ~120 B |
| `capital_status` | `{status, last_error}` | ~50 B |

**沒有任何一則帶部位 / 委託的完整資料。** 前端對 `capital_position` 的處理是
「一律 invalidate,不看 data」(`client.py:428` 的註解自承),資料一定要再走一趟 REST。

---

## 2. 端到端延遲預算(送單:現股限價,閃電梯點價)

TestClient 的框架底噪以同一支 `GET /api/capital/status`(payload 28 B)量得 p50 = 1.16 ms,
下表的 route 段一律扣掉這個底噪。

| # | 區段 | 位置 | 成本 | 依據 |
|---|---|---|---:|---|
| 1 | 輸入延遲(pointerdown → React onClick 執行)| 瀏覽器主執行緒 | 典型 ~0;**p99 ≲ 37 ms** | [實測·借用] 09-03 開盤 prod build 93 s trace:>50 ms long task = 0,最大 36.7 ms |
| 2 | `touchIdle()`(clearTimeout + setTimeout) | `useFlashArm.ts:40-44` | **0.259 µs** | [實測] bench_click.mjs |
| 3 | 武裝 / buyLocked 查表 + 同格 500 ms 防抖 + body 字面量 | `PriceLadder.tsx:272-303` | **0.065 µs** | [實測] |
| 4 | `mutateAsync()` → `mutationFn` 真被呼叫 | query-core `mutation.js:88-113` | **p50 1.4 µs / p95 4.9 µs** | [實測] bench_mutate.mjs(真 query-core 5.101.2) |
| 5 | `JSON.stringify(body)` | `useCapital.ts:109` | **0.242 µs** | [實測] |
| 6 | `fetch` → vite preview(Node)→ uvicorn(**兩跳**) | `vite.config.ts` `server.proxy` | **推估 0.5–1.5 ms** | [推估] 下界來自 [實測] loopback:新連線 HTTP 一趟 p50 0.52 ms、重用 0.12 ms、純 TCP connect p50 0.14 ms;access log 實證 4,262 個不同 client port / 5,041 次請求 → 連線幾乎不重用 |
| 7 | uvicorn/ASGI + FastAPI route(驗形 → dataclass → 呼叫 client 之前)| `capital_api.py:294-307` | **p50 0.06 ms**(扣底噪);pydantic 驗形 **1.21 µs**、`StockOrderRequest` **0.75 µs** | [實測] bench_post.py |
| 7b | 送單 request 在**共用 event loop** 上的排隊 | `server/app.py` 全部 TC4 fanout 同一條 loop | **未量測** | [推估] 無 loop lag 探針;開盤每秒數百 tick 時是唯一「規模由市場決定」的段 |
| 8 | safety gate(五個純函式)| `capital/safety.py` | < 5 µs | [實測·前輪 B10] |
| 9 | 前置審計 `to_thread` + `append_audit` | `client.py:884` | p50 **0.38 ms**;共享 executor 滿時**無上界** | [實測·前輪 B10] |
| 10 | `_cmd_q` → COM 執行緒 → `fut` 回 loop | `client.py:886-891` | p50 0.21 ms / p95 0.82 ms(池空) | [實測·前輪 B10] |
| 11 | **`SendStockOrder` + COM pump + 券商往返(黑盒)** | `com.py:150-169` | 整鏈 **E[總] ≈ 76 ± 12 ms**;**≥ 0.4% 超過 1.0 s;至少 1 筆超過 3.0 s** | [實測] 本輪自行重算 499 筆審計前/後置配對:跨秒率 7.6%(→ E≈76 ms,SE ±12 ms)、2 筆跨 2 s、1 筆跨 4 s |
| 12 | 後置審計 + `dataclasses.asdict(OrderResult)` + 回應序列化 | `client.py:917` / `capital_api.py:307` | 0.38 ms + **0.94 µs** | [實測·前輪] / [實測] |
| 13 | 回程兩跳 + `res.json()` | | 推估 0.5–1.5 ms | [推估] 同 #6 |
| 14 | `settleFlashSend` → `showHint` → React commit | `flash-send.ts:29-43` | 通知走 `setTimeout(0)` macrotask,≈ 一個 frame | [原始碼實證] `notifyManager.js` `defaultScheduler = systemSetTimeoutZero` |
| 15 | **成交 → 部位條 / 打平線更新(樂觀套用路徑)** | `client.py:430` → `useCapital.ts:138` | 樂觀套用 **p50 0.2 ms / p95 0.9 ms / max 10.2 ms**(n=189)+ 200 ms debounce + 一趟 REST ≈ **210–250 ms** | [實測] prod log `成交樂觀套用部位` |
| 16 | **成交 → 均價 / 損益(券商真相,回查鏈)** | `client.py:478-703` | **p50 1.94 s / p95 5.41 s / max 6.64 s**(n=183) | [實測] prod log `部位落地 … 自成交回報到達起 N ms` |

**加總(送單方向,扣掉 #11 黑盒與 #7b 未量段):前端 ≈ 2 µs + route ≈ 0.06 ms +
proxy 兩跳推估 1–3 ms + 審計/佇列 ≈ 0.97 ms ≈ 2–4 ms。** 對照整鏈 76 ms → **我負責的
這一段佔不到 5%,其中純 JS/route 的部分佔不到 0.1%。**

### 2.1 讀取面的預算(每次輪詢)

| route | payload(實測)| handler(扣底噪)| 頻率(實測 access log)|
|---|---:|---:|---|
| `/api/capital/positions` | **1,411 B**(7 列)| **0.02–0.12 ms** | **5,040 / 51.5 h**(09-11 log)· **5,530 / 15.0 h**(09-10)· **占全部 HTTP 33.8%** |
| `/api/capital/status` | **28 B** | ~0.00 ms | 2,259 / 51.5 h;**每個 observer 各一份 10 s 計時器**(最多 3 個) |
| `/api/capital/fills` | 12 B(空)– 數 KB | ~0.02 ms | 1,220 / 51.5 h |
| `/api/capital/orders` | N=20 → **9.5 KB**;N=60 → **28.6 KB**;N=200 → **95.4 KB** | N=20 → 0.11 ms;N=60 → **0.43 ms**;N=200 → **1.45 ms** | 826 / 51.5 h |
| `POST /api/capital/order/stock` | 請求 ~180 B / 回應 ~80 B | 0.06 ms | **13–28 / 日** |
| `POST /api/capital/order/cancel` | ~60 B | 0.06 ms | **2–7 / 日** |

**寫入 : 讀取 = 15 : 9,345(09-11 log)= 1 : 623。**
capital GET 四支合計 **占全部 HTTP 請求 59.0%(09-10)/ 62.6%(09-11)**。

`raw` 欄在 orders payload 中的占比 **20%**(合成樣本;真 OnNewData 48 欄更長,實際占比只會更高),
而前端 `types.ts:100` 宣告了它、產品碼 **零讀者**。

---

## 3. 前端 click → fetch 逐段(問題 1 的答案)

**結論:上一輪「click→fetch 無阻塞、TanStack 通知走 `setTimeout(0)` macrotask、fetch 在
microtask 先發」完全成立,而且可以給出數字。**

原始碼證據鏈(query-core 5.101.2,本機 `node_modules`):

1. `MutationObserver.mutate`(`mutationObserver.js:56-62`)同步 `build()` + `addObserver()` +
   `return mutation.execute(variables)`。
2. `Mutation.execute`(`mutation.js:88-…`)是 `async`,同步跑到第一個 `await`:
   `createRetryer(...)` → `this.#dispatch({type:"pending", …})`(觀察者通知進
   `notifyManager.batch`)→ `if (mutationCache.config.onMutate)` 為假直接跳過 →
   **`const context = await this.options.onMutate?.(...)`**(本專案沒定義 `onMutate`,
   `await undefined` = 讓一個 microtask)→ `await this.#retryer.start()`。
3. `retryer.start()`(`retryer.js:118-124`)在 `canStart()` 為真時**同步**呼叫 `run()` → `fn()`
   → `mutationFn` → `fetchJson` → `JSON.stringify` + `fetch`。
4. `notifyManager.js` 的 `defaultScheduler = systemSetTimeoutZero` → **render 通知是 macrotask**,
   一定排在同一個 task 內發出的 `fetch` 之後。

實測(`bench_mutate.mjs`,2,000 次):
```
mutateAsync() → mutationFn 被呼叫 (µs): p50=1.4  p95=4.9  max=649.4(GC 離群)
```

**同步計算沒有擋在前面**:`clickPrice` 的全部同步工作 = `touchIdle`(0.259 µs)+ 查表/樣板/
防抖(0.065 µs)+ body 字面量(0.014 µs)= **0.34 µs**,加上 TanStack 的 1.4 µs 與
`JSON.stringify` 的 0.242 µs = **≈ 2 µs**。

**React re-render 沒有擋在前面**:onClick 是 React 19 的 discrete event,handler 同步執行;
`showHint` 的 setState 只在**回應回來之後**才發生。`PriceLadder` 每 tick 重算的
`aggregateLots` / `positionRows` / `buildLadder`(見 F4 報告)是 render 期的成本,
不在 click→fetch 這條路上 —— 它們影響的是 **#1 輸入延遲**(主執行緒被佔住時 click 事件
排隊),而那一段有 09-03 trace 的上界(最大 long task 36.7 ms)。

---

## 4. 「`/api/capital/positions` 還需要嗎」(問題 5 的答案)

### 4.1 任務陳述的前提為假 —— 有證據

> 「每日 4,384 次拿的是已經由 `/ws/capital` 推播出去的同一份資料」

**不是同一份資料。** `capital/client.py:430` / `672` 的 `_emit` payload 只有 `{"count": N}`
(+ 樂觀套用那則多一個 `"source": "fill"`)。`client.py:428` 的註解白紙黑字:

```python
# `useCapitalStream` 對 capital_position 一律 invalidate,不看 data);只有
# `tests/capital/test_fill_latency.py` 用它分辨兩種推播。
```

也就是說 WS 是**通知通道**不是**資料通道**。今天把 REST 拔掉,部位面板會整個沒有資料。

### 4.2 但這個形狀對量化系統是錯的

實測頻率:**5,040 次 / 51.5 h**(09-11)、**5,530 次 / 15.0 h**(09-10)、
**5,073 次 / 12.8 h**(09-09)。占全部 HTTP 請求 **31–39%**。

單次成本微不足道(payload 1.4 KB、handler 0.02–0.12 ms)。所以**理由不是 CPU**,而是:

1. **診斷訊號被淹沒**:09-11 的 log 共 20,473 行,其中 9,345 行是 capital GET 的 access log
   (45.6%)。本輪要從 log 找任何東西都得先寫腳本過濾 —— 這是可量的 ops 成本。
2. **每次都是一條新 TCP 連線**:5,041 次請求用掉 4,262 個不同 client port
   [實測]。Node 預設 agent keep-alive 約 5 s,而輪詢間隔 15 s → socket 每次都過期。
   一次新連線的 loopback HTTP 往返 p50 0.52 ms vs 重用 0.12 ms [實測]。
3. **節奏與需求不匹配**:部位在成交之外**完全不變**。一天真正需要更新的時點 ≈ 成交筆數
   (本機樣本 n=183/週)+ 開機一次。用 15 s 定時輪詢覆蓋一天 4,000+ 次,而真正該快的
   那 200 次卻要吃 200 ms debounce + 一趟往返。
4. **`refetchIntervalInBackground` 預設 false**:分頁失焦 → 輪詢**全停**。所以這 5,000 次
   既不是「安全網」(失焦時沒有),又不是「即時」(15 s)。它落在兩頭不著地的位置。

### 4.3 該做什麼

**把 `capital_position` / `capital_order` 的 WS payload 換成完整資料**(與 REST route
共用同一支 builder),REST 降級成 reconcile 通道(重連 / 重新聚焦 / 手動 refresh 觸發,
外加 60 s 保險輪詢)。

- payload 成本:1.4 KB × ~200 則/日 = 280 KB/日,零壓力。
- 收益:部位顯示延遲從 **210–250 ms** 降到 **< 5 ms**(省掉 200 ms debounce + 往返);
  positions 請求數從 ~5,000 降到 ~100。
- ⚠ **跨檔契約**:`avg_source` / `today_qty` / `unit` 的產生點會多一個出口。
  必須**共用同一支序列化函式**(route 與 WS 都呼叫它),否則 CLAUDE.md §4 的
  「少送 `avg_source` → 前端當 fill 多加一次買費」那條零訊號失效會多一條複製路徑。

---

## 5. Findings

### F-01 【critical】`new QueryClient()` 零預設 → `networkMode: "online"` 讓送單「暫停」而不是「失敗」

**位置** `frontend/src/main.tsx:16`
```ts
const queryClient = new QueryClient();   // 沒有任何 defaultOptions
```

TanStack Query v5 的 mutation 預設 `networkMode: "online"`。`Mutation.execute`
(`mutation.js`)先 `const isPaused = !this.#retryer.canStart()`;`canStart()` 在
`onlineManager.isOnline() === false` 時回 false → `retryer.start()` 走
`pause().then(run)`,**`mutateAsync` 的 promise 不 settle**。

而 `queryClient.js:42-45`:
```js
this.#unsubscribeOnline = onlineManager.subscribe(async (online) => {
  if (online) { await this.resumePausedMutations(); ... }
});
```
→ **連線恢復時自動把那張單送出去**。

**為什麼這在本專案特別嚴重**:server 跑在**同一台機器**的 127.0.0.1。使用者的 WiFi 斷掉
(或 Windows 誤判 `navigator.onLine === false`)時,**localhost 明明通**,單卻被扣住;
畫面上只有一顆一直轉的鈕(`settleFlashSend` 的 then 永遠不跑,`showHint` 不動);
幾分鐘後網路回來,**一張幾分鐘前的限價單被送進市場**。

零錯誤訊號,而且與 `client.py:892-898` 的「結果未知,勿重送」設計意圖正面衝突 ——
那條的前提是「單可能已出手」,這條是「單一定還沒出手、但等一下會出手」。

**修法**(一行,零後端改動):
```ts
new QueryClient({ defaultOptions: { mutations: { networkMode: "always" } } });
```
`"always"` = 不看 `navigator.onLine`,直接送,失敗就是失敗。對 localhost server 這是唯一
正確的語意。查詢面可另外評估(查詢暫停無害)。

---

### F-02 【high】券商拒單的真正理由前端零讀者 —— 所有 999 都顯示「券商拒單(999)」

**位置** 後端 `server/app.py:2120-2131` 送出:
```python
content={"detail": {"error": "BROKER_REJECTED", "err_code": exc.err_code, "err_msg": exc.err_msg}}
```
前端 `lib/api-error.ts::ErrorDetail` 只宣告 `error` / `reason` / `err_code`;
`useCapital.ts::parseCapitalError:96-98` 只取 `err_code`:
```ts
if (code === "BROKER_REJECTED" && detail.err_code) return `${code}:${detail.err_code}`;
```
`grep -rn "err_msg" frontend/src` 的命中**全在 `.test.tsx` fixture**,產品碼零命中 [實測]。

**實際後果**(本機 `data/audit/capital-*.jsonl`,52 筆 `ok=false`):
| 審計檔裡的真正理由 | 畫面上顯示 |
|---|---|
| `[999] 因您尚未簽署新版風險預告書,已可簽署,暫不可送下單!` | 券商拒單(999) |
| `[999] 融資餘額超過核定額度 249萬!` | 券商拒單(999) |
| `[960] 已委託尚可未刪單!` | 券商拒單(960) |

三種完全不同的處置(去簽文件 / 換現股或減量 / 這張單已經不在了)在畫面上長得一模一樣。
memory 記載的「249 萬額度斷路器」正是這條路徑上實際發生過的事件。

**修法**:`ErrorDetail` 加 `err_msg?: string`;`parseCapitalError` 的 BROKER_REJECTED 分支改帶
`err_msg`;`tradeErrorText` 對已有 `:` 後綴的既有行為不變(它只 split 第一段)。
⚠ 這是**跨檔契約**(CLAUDE.md §4 API error shape),兩邊同動,`useCapital.test.tsx:110`
已有 fixture 可直接改成斷言。

---

### F-03 【high】`OrderResult.ok === false` 的 200 回應在四個寫入入口中有三個沒有讀者

`_execute_write` 逾時路徑(`client.py:892-897`)回的是 **HTTP 200** + `ok:false` +
`message:"結果未知,勿重送"`。四個消費端:

| 入口 | 有沒有讀 `r.ok` | 結果 |
|---|---|---|
| 三座梯的 `clickPrice` / `marketOrder` → `settleFlashSend` | **有**(`flash-send.ts:31-38`)| ✅ hint 印出「結果未知,勿重送」+ 計 `send_fail` |
| `FuturesLadder.confirmClose` | **有**(`FuturesLadder.tsx:281-292`)| ✅ |
| `CapitalPositionsList.confirm` | **沒有** —— `closePosition.mutate(closeBodyOf(...))` 無 callback | ❌ `error` 為 null、列表不變 → 畫面與「還沒平到」一模一樣 |
| `CapitalOrdersList`(刪單 / 改價 / 減量)| **沒有** —— `cancelOrder.mutate({...})` 無 callback | ❌ 同上,只有 throw 才進 `actionError` |
| 三座梯的 `cancelLot` / `cancelAll` | **沒有**,而且連 `cancelOrder.error` 都不渲染 | ❌❌ 完全零訊號 |

**這是「單可能已經出去了」的唯一警告**,而它在最容易連按的三個入口上被丟掉。

**修法**:`useCapitalMutation` 改成回傳一個帶 `onResult(r)` 慣例的包裝,或者最省的做法 ——
把 `settleFlashSend` 的尾段守門抽成不依賴 arm 的版本(`settleWrite(p, {showText})`),
四個入口共用。零後端改動。

---

### F-04 【high】`cancelLot` / `cancelAll`:N 筆並發、零上限、只留最後一筆的錯誤

**位置** `PriceLadder.tsx:366-369`、`StkfutLadder.tsx:250`、`FuturesLadder.tsx:257-265`
```ts
function cancelLot(lot: LadderLot): void {
  touchIdle();
  for (const seq of lot.seqs) cancelOrder.mutate({ seq_no: seq, market: "sec" });
}
function cancelAll(): void { cancelLot(allSeqNos); }   // FuturesLadder
```

`MutationObserver.mutate`(`mutationObserver.js:56-62`)每次呼叫都
`this.#currentMutation?.removeObserver(this)` 然後換成新的 mutation:
```js
mutate(variables, options) {
  this.#mutateOptions = options;
  this.#currentMutation?.removeObserver(this);
  this.#currentMutation = this.#client.getMutationCache().build(...);
```
→ **只有最後一筆的 `isPending` / `error` 進得了 `cancelOrder`**;前 N−1 筆的失敗無處可去。
而三座梯**都沒有渲染 `cancelOrder.error`** → 刪單失敗零訊號(F-03 的加重版)。

同時:N 筆同時進 `_cmd_q`,在 COM 執行緒上串行送出(每圈一筆,`client.py:808-816`),
每筆前後各一次審計 `to_thread`。一個「全撤」= 2N 次共享 executor 排隊 + N 次 COM 往返。
以 #11 的 E≈76 ms 計,10 筆活單的全撤 ≈ **0.8 秒**,期間畫面完全靜止。

**修法**:
1. 三梯的紅方格點刪加一條錯誤列(或走 F-03 的 `settleWrite`),至少讓失敗可見。
2. `cancelAll` 加一個彙總狀態(`n 筆送出 / m 筆失敗`),不要只留最後一筆。
3. (後端側,屬 B10)刪單/平倉可以在 COM 執行緒上做批次,不要一圈一筆。

---

### F-05 【high】`/api/capital/positions` 的節奏與需求不匹配 —— 5,000 次/日換 15 s 新鮮度

見 §4 全節。實測:5,040 / 51.5 h(33.8% 的 HTTP 請求)、payload 1,411 B、handler 0.02–0.12 ms、
4,262 個不同 client port(連線幾乎不重用)。

**這不是 CPU 問題**(全天合計 < 1 秒 CPU),是**形狀問題**:
- 該快的(成交後部位)吃 200 ms debounce + 一趟往返;
- 不該打的(部位沒變的 4,800 次)照打;
- 分頁失焦時兩者都停。

**修法**:見 §4.3(WS 送完整 payload + REST 降成 reconcile)。

---

### F-06 【medium-high】`useCapitalStatus` 是唯一沒收斂節奏的 capital 查詢 —— 每個 observer 各一份 10 s 計時器

**位置** `useCapital.ts:150-157`
```ts
export function useCapitalStatus() {
  return useQuery({ queryKey: ["capital-status"], ..., refetchInterval: 10_000, retry: 1 });
}
```
呼叫端三處:`OrderPanel:43`、`CapitalOrdersList:32`、`CapitalPositionsList:26`。
`RightRail` 在 `ctx.kind === "none"`(TXO / 指數 tab)時**同時渲染兩個 `CapitalOrdersList`**
(sec + fut)或兩個 `CapitalPositionsList` → 兩個 observer,各自一份 `setInterval`,
相位由掛載時點決定。

這與 `useCapitalPositions` / `useCapitalFills` 的 N068 註解(「per-observer 輪詢的相位由掛載
時點決定,同一支 API 在窗內被打多次」)所解的是**同一個問題**,但 status 沒跟上 ——
**同一份設計教訓在同一個檔案裡只套用了三分之二**。

實證:同一份 log 裡 `/api/calendar` 呈現**每次三行連發**(三個 observer),
`/api/capital/status` 2,259 次 / 51.5 h。

**修法**:照 `positionsQueryOptions` 的樣板抽 `statusQueryOptions(interval)`,
節奏搬進 `useCapitalStream`,讀取端一律 `refetchInterval: false`。十行內、零契約。

---

### F-07 【medium-high】送單 mutation 無 timeout / 無 AbortController / 無中間態

**位置** `useCapital.ts:102-114`
```ts
const res = await fetch(url, init);     // 無 signal、無 timeout
```
後端 `_WRITE_TIMEOUT_S = 10.0`。COM 卡住時使用者看到的是:
- 閃電梯:hint 不變(上一則舊 hint 還掛著,3 秒後才自動清)、武裝鈕照樣紅、**點價鈕照樣可按**
  (只有同格 500 ms 防抖)→ 最容易在這 10 秒內連點。
- 確認窗路徑:`busy` / `isPending` 會鎖鈕 ✅(`CapitalOrdersList:38`、`CapitalPositionsList:105`)。

**閃電梯是唯一沒有 `isPending` 節流的送單路徑**,而它正是連點風險最高的那個。

**修法**:
1. 加一個 ~1.5 s 的「已送出,等待券商回應…」中間態(純文案,`submitStock.isPending` 已有);
2. ⚠ **不可以真的 abort** —— `client.py:899-902` 的 `CancelledError` 分支明文寫著「單可能
   已出手」,前端主動取消只會製造更多「結果未知」。加 AbortController 只能用來**換文案**,
   不能真的中止。

---

### F-08 【medium】`refetchOnWindowFocus` 全開 + `staleTime: 0` → 每次 alt-tab 重抓全部 capital 查詢

`new QueryClient()` 沒給 `defaultOptions` → `staleTime: 0`、`refetchOnWindowFocus: true`。
每次分頁取得焦點,四支 capital 查詢(positions / fills / orders / status)全部 refetch,
而且 orders 在 N 大時是 28–95 KB 的 payload。

這對「部位 / 委託」其實**是對的行為**(回到畫面就該是最新的),對 `status`(10 s 輪詢本來就有)
和 `fills`(30 s)是重複。列在這裡是因為它與 F-05 是同一筆帳:真正需要的是
「WS 為真相 + focus/reconnect 時 reconcile」,而不是三層重疊的輪詢。

**判定:先做 F-05,這條自然收斂。不要單獨動 `refetchOnWindowFocus`** —— 關掉它會讓
「筆電闔蓋回來部位是舊的」變成新的零訊號路徑。

---

### F-09 【medium】`_correct_price_tick_gate` 在 route 層建全表,只為找一筆(前輪 F-06 的 route 半邊,補實測)

**位置** `capital_api.py:191`
```python
rec = next((o for o in client.store.orders() if o.seq_no == seq_no), None)
```
接著 `client.correct_price` → `_fut_multiplier`(`client.py:1065`)**再建一次全表**。

本輪實測 `store.orders()` + `asdict` 的建構成本:N=20 → 0.103 ms、N=60 → 0.310 ms、
N=200 → **1.558 ms**。期貨改價 = 這個數字 ×2,全部在 event loop 上、全部持 `store._lock`。

**N 的成長軸是 process uptime 不是當日筆數**:`store.clear()` 零 prod caller,
而本機 server 實證連跑 **51.5 小時**(09-11 09:05 → 09-13 12:33)[實測,log 首尾時戳]。

**修法**:`CapitalStore.order_of(seq_no)`(鎖內 `dict.get` + 單筆 `_to_record`,~5 µs),
三個 caller 改用它。零契約影響。

---

### F-10 【medium】`OrderRecord.name` 恆為空字串 —— docstring 說「route enrich 填」,但沒有任何 route 填

**位置** `models.py:166` `name: str = ""  # route enrich 填,store 不管`
`grep -n "name" copycat/server/capital_api.py` → 只命中 `logger = logging.getLogger(__name__)` [實測]。

讀者 `CapitalOrdersList.tsx:102`:
```ts
const title = `${order.stock_no ?? ""} ${order.name}`.trim();
```
→ 委託列表**永遠只顯示股號,不顯示股名**。而同一支 `CapitalPositionsList` 的
`{`${p.stock_no} ${p.name}`.trim()}` 有名字(`Position.name` 由 `balance.py` 填)。
兩張並排的表,一張有名一張沒名,而註解說應該有。

**判定**:不是效能問題,是**已經漂掉的契約**。要嘛在 route 用 `useStockNames` 的同一份對映
enrich(前端已有 `/api/stock/names`,更省的是前端自己接),要嘛把欄位與 docstring 一起刪。
現況是「畫面缺一半資訊 + 每列多送一個空欄」。

---

### F-11 【medium】確認窗的 `danger`(正式環境紅底)在 FuturesLadder 的平倉窗漏帶

**位置** `FuturesLadder.tsx:535-548` —— `CapitalConfirmDialog` 沒有 `danger` prop。
對照:`OrderPanel.tsx:304` `danger={isProd}`、`CapitalPositionsList.tsx:136` `danger={danger}`、
`CapitalOrdersList.tsx:230` `danger={danger}`。

`danger` 是 CLAUDE.md §7 第 1 道閘(「正式戶要印環境名」)在 UI 上的落點。
四個確認窗有三個帶、一個不帶 —— 而不帶的那個是**期貨一鍵平倉**(可多筆、金額最大)。

零錯誤訊號:窗照開、字照印,只是少了紅底與「正式」兩個字。

**修法**:`FuturesLadder` 拉 `useCapitalStatus()` 的 `env === "prod"` 傳進去。三行。

---

### F-12 【medium】張數輸入無上界,前後端都沒有

**位置** `LadderView.tsx:217-224`
```tsx
<input aria-label={qtyLabel} type="number" min={1} value={qty}
       onChange={(e) => onQtyInput(Number(e.target.value))} />
```
`qty-quick.ts:18`:`manualQty` = `Math.max(1, Math.floor(qty))` —— **只 clamp 下界**。
`min={1}` 是 HTML 驗證屬性,不會阻止 `1e5` 這種輸入被 `Number()` 接受。
後端 `CAPITAL_MAX_QTY` 依 CLAUDE.md「未設/0 = 不限(user 拍板)」。

→ 武裝態下把張數框打成 `100000` 再點一格價 = 直送 10 萬張。
唯一的攔截是券商端(本機審計檔已有 `[999] 融資餘額超過核定額度 249萬` 的實證,
表示這條路真的會走到券商才被擋)。

**修法**:前端加一個**顯而易見**的上界(`max` + `manualQty` 的 clamp 上界),
數字由 user 拍板。這是 UI 半邊;後端半邊屬 B10 的 F-12 風控層。
⚠ 不要靜默 clamp —— 靜默把 100000 改成 99 是另一種零訊號。

---

### F-13 【medium】REST 查詢失敗後畫面留舊值,零 staleness 標記

`retry: 1` 之後查詢進 error 終態,但 TanStack 會保留 `data`(上一次成功值)。
`PriceLadder` 只讀 `useCapitalPositions().data` / `useCapitalOrders().data`,
**完全沒有讀 `isError` / `dataUpdatedAt`** → capital 後端 502/503 時:
- 部位條照畫、打平線照畫、均價照印;
- 梯上的紅方格(已委託量)照畫;
- 唯一的訊號是 WS 也斷掉時武裝被清(`conn_lost`)—— 但 REST 掛掉不等於 WS 掛掉。

對照:`CapitalPositionsList` 有渲染 `closePosition.error`,但沒渲染 `useCapitalPositions().error`。

**修法**:`PriceLadder` 的部位條 / 紅方格在 `isError` 或 `dataUpdatedAt` 過舊時加灰化或
一個小標記。這條與本專案既有的 stale badge 慣例(ConnectionBadge / 加權 stale 徽章)同型。

---

### F-14 【low-medium】vite preview proxy 那一跳:每次請求一條新 TCP

**證據** [實測]:09-11 log 的 5,041 次 positions 請求用掉 **4,262 個不同 client port**,
最常用的 port 也只出現 25 次。Node 預設 agent 的 keep-alive 約 5 s,而輪詢間隔 15 s →
每次都是新連線。

成本 [實測,loopback 底噪]:新連線 HTTP 一趟 p50 **0.521 ms** vs 重用 **0.116 ms**,
純 TCP connect p50 0.143 ms / p95 0.327 ms / **max 2.788 ms**。

對 5,000 次輪詢 = 多花 2 秒/日(無感)。對**送單**:多 0.4 ms + Node event loop 的
一次排程,占 76 ms 的 0.5%(無感),但它是**尾巴不可控**的一段(Node 的 GC / 其他請求)。

**判定:先不要動。** 前輪 B10 的 F-18(改掛 `StaticFiles` 直接服 `dist`)會一併消掉,
但那是部署慣例異動(CLAUDE.md §1)。在 #11 的黑盒還沒量出來之前,動這一段是在小數點後面努力。

---

### F-15 【low-medium】`/api/capital/orders` 的 `raw` 欄佔 payload 20%,前端零讀者(前輪 F-08 補實測)

[實測] 合成樣本:N=20 → payload 10,732 B 其中 raw 2,180 B(20%);
N=200 → 107,212 B 其中 raw 21,800 B(20%)。真 OnNewData 是 48 個逗號欄,實際比例更高。

`frontend/src/types.ts:100` 宣告 `raw: string`,`components/capital/` 與 `lib/` 零讀取 [實測·前輪已確認]。

**修法**:route 層不輸出 `raw`(⚠ 跨檔契約,`types.ts` 同動)。
配合 F-09 的 `order_of` 之後,orders 這一支就從「O(N) 全表 + 20% 死 payload」變成正常。

---

### F-16 【low】`useCapitalOrders` 帶 `refetchInterval: 30_000` 而 positions/fills 不帶 —— 三種節奏三種寫法

`useCapital.ts` 裡三支讀取 hook 的節奏歸屬不一致:
- `useCapitalPositions` → `false`,節奏在 `useCapitalStream`(15 s)✅ 有 N068 註解
- `useCapitalFills` → `false`,節奏在 `useCapitalStream`(30 s)✅ 有 N068 註解
- `useCapitalOrders` → **自帶 `refetchInterval: 30_000`**,四個呼叫端(三梯 + 列表)各一份 ❌
- `useCapitalStatus` → **自帶 `refetchInterval: 10_000`**,三個呼叫端各一份 ❌(= F-06)

實測 orders 826 次 / 51.5 h,比 30 s 單一節奏應有的量少(分頁失焦停輪詢),但相位仍是
per-observer。同一個檔案裡同一條教訓只落實了一半 —— 這是**下一個人會踩的坑**。

**修法**:與 F-06 同一批,四支統一收斂到 `useCapitalStream`。

---

## 6. 失效模式表(這一段會怎麼壞)

| # | 失效 | 觸發 | 使用者看到 | 零訊號? | 嚴重度 |
|---|---|---|---|---|---|
| 1 | mutation 被 `networkMode:"online"` 暫停,恢復連線後自動送出 | `navigator.onLine === false`(WiFi 掉、Windows 誤判),而 server 在 localhost 明明通 | 鈕一直轉;幾分鐘後那張舊單進市場 | **是** | critical |
| 2 | 券商拒單理由不可見 | 任何 `code != 0` | 「券商拒單(999)」 —— 簽署文件 / 額度爆 / 檔位錯全同一句 | **是** | high |
| 3 | 「結果未知,勿重送」被吞 | `_WRITE_TIMEOUT_S` 10 s 逾時,經 `CapitalPositionsList` / `CapitalOrdersList` / 紅方格點刪 | 什麼都沒有;列表沒變 → 看起來像「還沒生效」 | **是** | high |
| 4 | 批次刪單只留最後一筆錯誤 | `cancelLot` / `cancelAll` 的 N > 1 | 前 N−1 筆的失敗完全不存在;三梯連 `cancelOrder.error` 都不渲染 | **是** | high |
| 5 | 後端忙 / COM 卡住 → 閃電梯可重複按 | `_pump_once` 卡住 / `SendStockOrder` 慢 | 舊 hint 還掛著、武裝鈕仍紅、點價鈕仍可按(只有同格 500 ms 防抖) | 部分(無中間態) | high |
| 6 | 不同價格格子無節流 | 武裝態下快速點多格 | 每格各送一張,前端零速率限制、後端零速率限制 | **是** | high |
| 7 | REST 掛掉但 WS 活著 | capital route 502/503、或 `/api/capital/positions` 失敗兩次 | 部位條 / 打平線 / 紅方格照畫舊值,零 staleness 標記 | **是** | medium-high |
| 8 | 分頁失焦 → 四支輪詢全停 | `refetchIntervalInBackground` 預設 false | 切回來之前部位可以是數小時前的;若 WS 也斷則完全不更新 | 部分(切回會 focus refetch) | medium |
| 9 | capital WS 斷線 → 武裝被清、鎖定鈕鎖住最長 30 s | 任何 WS blip(`WS_BACKOFF_CAP_MS = 30_000`) | 武裝自動解除(**這是有訊號的**),但最長 30 s 不能重新武裝 | 否 | medium |
| 10 | 期貨一鍵平倉的確認窗沒有「正式」紅底 | prod 環境 + FuturesLadder 平倉 | 窗照開、字照印,少了環境警示 | **是** | medium |
| 11 | 張數框誤打 → 直送超大單 | `1e5` / 多按一個 0;`min={1}` 無 `max`;後端 `CAPITAL_MAX_QTY` 預設不限 | 直到券商拒單才知道 | **是** | medium |
| 12 | `OrderRecord.name` 恆空 | 一直如此 | 委託列表只有股號沒有股名,而部位列表有 | **是** | low-medium |
| 13 | 跨日長跑 → orders payload 與列表無上限成長 | `store.clear()` 零 prod caller;實證連跑 51.5 h | 委託列表混入前幾天的單;payload N=200 時 95 KB / 1.45 ms | 部分(列表看得出來) | low-medium |
| 14 | 舊後端 / 新前端形狀不合 | `OrderResult` 少欄 | `r.ok` 為 undefined → 走 else → 印「送單失敗」,而單其實送出去了 | **是** | low-medium |
| 15 | 審計寫入失敗 | 磁碟滿 / 權限 | 「審計寫入失敗,單未送出」✅ 文案齊全、語意正確 | 否 | (對照組:這條寫對了)|

---

## 7. 改造順序 + 量測判準

| # | 動作 | 為什麼排這裡 | 工作量 | 量測判準 | 回退 |
|---|---|---|---|---|---|
| 1 | `main.tsx` 加 `defaultOptions.mutations.networkMode: "always"` | 一行,擋掉唯一一條「單會在你不知道的時候出去」的路徑。沒有它,下面每一條都是在安全性破洞上面做效能 | S | DevTools Network 離線模式下按送單 → **必須立刻拿到 fetch 失敗**,而不是一直 pending;恢復連線後 **Network 面板不得出現補送的 POST**。`useCapital.test.tsx` 加一條 offline 案 | 改回不帶 defaultOptions |
| 2 | `err_msg` 接到畫面(F-02)+ `settleWrite` 共用尾段讓「結果未知」在四個入口都可見(F-03)+ 批次刪單彙總(F-04) | 這三條是同一件事:**寫入結果的語意在 UI 上補齊**。CLAUDE.md §7 的審計要求已經做到後端,前端是斷點 | M | 用 `data/audit/capital-*.jsonl` 裡真實的三種 999 訊息做 fixture,斷言畫面印出**不同**的字串;`CapitalPositionsList.test.tsx` 加「200 + ok:false」案,斷言有可見文字 | 各條獨立,單條 revert |
| 3 | 裝 **前端 User Timing 探針**:`performance.mark("order:click")` / `("order:done")` + `measure`(六個送單入口共用一支 helper);後端同步做 B10 的 F-10 分段時戳 | **沒有這個,#4 之後的每一條都是盲改。** 前端這一半特別便宜(已有 `dev-perf-guard` 的 entry 上限機制可沿用),而且它量的正是我這一區負責的那一段 | S | 開盤送一張真單,DevTools Performance 面板的 `order:*` measure 與後端審計行的 `lat_us.total` 相減 = 「瀏覽器 + proxy 兩跳 + loop 排隊」。**目標:p95 < 5 ms**;超過就代表 #7b 的 loop 排隊是真的 | 探針純 additive,直接刪 |
| 4 | `useCapitalStatus` / `useCapitalOrders` 的節奏收斂到 `useCapitalStream`(F-06 / F-16) | 十行內、零契約、照抄同檔已有的 `positionsQueryOptions` 樣板。先做這個,再看 #5 的效果才乾淨(否則 positions 降下去了 status 還在洗版) | S | 盤後 `grep -c 'GET /api/capital/status' logs/server-*.log` **降到「聚焦時數 × 360」以內**(單一 10 s 節奏的理論值);同理 orders 降到「聚焦時數 × 120」 | 單檔 revert |
| 5 | `capital_position` / `capital_order` 的 WS payload 換成完整資料(**與 REST route 共用同一支序列化函式**),REST 降成 reconnect / focus / 60 s 保險(F-05 / §4.3)| 這是讀取面唯一的結構性改動,也是把「成交後部位更新」從 210–250 ms 降到 < 5 ms 的唯一辦法。排在 #4 之後是因為要先把節奏收乾淨才量得出差別 | L | (a) `grep -c 'GET /api/capital/positions'` **降 90% 以上**;(b) #3 的探針量「成交回報到達 → 部位條重繪」**p50 < 20 ms**(現況 210–250 ms);(c) `tests/capital/test_models.py::test_avg_source_parity_with_frontend` 仍綠 —— **`avg_source` / `today_qty` / `unit` 三條契約必須只有一個產生點** | WS payload 是 additive(多帶欄位),前端先讀 WS 後讀 REST 的順序可用一個旗標切回 |
| 6 | 張數上界(F-12)+ FuturesLadder 平倉窗帶 `danger`(F-11) | 兩條純 UI 安全閘,和 #5 無依賴,可以併進任何一批 | S | 張數框打 `100000` → 送出鈕 disabled + **可見**理由;prod 下 FuturesLadder 平倉窗有紅底「正式」(截圖存 `docs/specs/`) | 各三行 |
| 7 | `CapitalStore.order_of(seq_no)`(F-09),三個 caller 改用 | 期貨改價路徑現在建兩次全表。等 #5 把 REST 量降下來之後,這條剩下的就只有寫入路徑,值得修 | S | 微基準:N=200 的期貨改價 route 從 **3.1 ms → < 0.1 ms**;`tests/capital/test_store.py` 全綠 | 加一支方法,caller 改回 |
| 8 | route 不輸出 `raw`(F-15)⚠ 跨檔契約 | payload 20% 死重。排最後是因為它要動 `types.ts`,而收益只有在 N 大時才有感 | M | `/api/capital/orders` payload **降 20% 以上**;`npx tsc -b` 綠 | 加回一欄 |
| 9 | (觀察,不改)`store.clear()` 的日界呼叫者(F-13)| 跨日長跑讓 `_orders` 無上限成長。但 `clear()` 的語意與「回報重播」綁死(`store.py` 檔頭),隨便加 caller 會踩 `_positions_seeded` / 水位那組坑 | — | 先量:連跑 3 天後 `curl /api/capital/orders \| wc -c`。超過 200 KB 再談 | — |
| 10 | (觀察,不改)vite proxy 那一跳(F-14)| 在 #11 黑盒量出來之前,0.4 ms 的改動沒有意義 | — | #3 的探針差值若顯示 proxy 段 > 3 ms 才動 | — |

---

## 8. 這裡不要動(反向結論)

| 位置 | 為什麼不要動 |
|---|---|
| **mutation 的 `retry` 預設 0** | `useCapitalMutation` 沒設 `retry`,query-core 的 mutation 預設就是 0(`mutation.js` `retry: this.options.retry ?? 0`)。**真錢寫入不重試是對的**,任何「加個 retry 讓它穩一點」的念頭都要先過 `_execute_write` 的「結果未知」語意 |
| `settleFlashSend` 的兩參數 `then`(不是 `.then().catch()`)| `flash-send.ts:26-28` 的註解說明白了:串接會讓成功分支自己拋的例外掉進 catch → 同一次送單既 `send_ok` 又 `send_fail`。這是刻意的,別「簡化」 |
| `settleFlashSend` 的**不對稱** `alive()` 守門(失敗無條件計、成功要守門)| `flash-send.ts:4-9`。改成對稱會讓「連 3 敗自動解除」那道閘永遠關不上 |
| 同格 / 同鈕 500 ms 防抖 + 市價鈕**獨立槽位** + key 併入股號 | `PriceLadder.tsx:314-323` 有三段 review 來歷(R9 / r1 IMPL-1)。這是誤送防線不是效能路徑 |
| `useFlashArm` 的 Esc **capture 相位**監聽 | `useFlashArm.ts:56-69`(N080):`CapitalConfirmDialog` 在自己的 keydown 上 `stopPropagation()`,冒泡相位收不到。改成冒泡 = `LOCK_TITLE` 白紙黑字的承諾變成假的 |
| `useFlashArm` 的 `conn_lost` **level 觸發**(deps 帶 `state.locked`)| SC-13:只看邊沿的話「已經斷線了才鎖定」之後鎖定態會在斷線上無限存活 |
| `dispatch` / `touch` 的 **identity 恆定**(原始 `useReducer` dispatch + `useCallback([])`)| `useFlashArm.ts:22-29` + `PriceLadder.tsx:371-378`:包一層會讓 `left_view` 的 cleanup 每次 re-render 都跑 = **每收一則報價就解除一次武裝** |
| `CapitalConfirmDialog` 的 `closedRef` 一次性旗標 + `armContractCheck` | 它堵的是「點確認送單後、caller 卸載前按 Esc → UI 誤導成已取消但單已送出」。不要為了「可重用」把它做成受控元件 |
| `armGate` / `marketButtonState` / `KIND_TRAITS` / `close-order.ts::kindOf` 的**單一定義**慣例 | 這幾支都是「三座梯共用一份安全規則」的產物,各自的檔頭都寫明了分散後的失效樣態(零訊號)。重構時逐字保留 |
| 確認窗的焦點落在「取消」(`cancelRef.current?.focus()`)| `CapitalConfirmDialog.tsx:62-65` 的註解:真錢窗,Enter 不可直達送單 |
| `store._today_net_lots_locked` 的 `fill_date != today` 過濾 | `store.py:300-321`:它**已經**處理了「跨日長跑時聚合不只當日」這件事,註解寫得比我能寫的清楚。F-13 的 payload 成長與這條無關,不要一起改 |
| `pydantic` 驗形(1.21 µs)/ `dataclasses.asdict(OrderResult)`(0.94 µs)/ FastAPI 的 `-> dict` 回應路徑 | 實測都在個位數微秒。`ORJSONResponse` 在這個 FastAPI/pydantic 版本上是**退步**(已知事實)。route 層零優化空間 |
| `_stkfut_gates` / `_require_legal_tick` / `_correct_price_tick_gate` / `_close_tick_gate` 的**三處共用判準** | `capital_api.py:140-229` 的四段 docstring 逐條說明了「三處只有兩處在」的失效樣態。要改的是 F-09 的查詢方式,不是判準 |

---

## 9. 工具選型

| 工具 | 用在哪 | 為什麼 | 代價 | 結論 |
|---|---|---|---|---|
| `performance.mark` / `measure`(瀏覽器內建)| 六個送單入口 + `settleFlashSend` 尾段 | 唯一能量出「click → 畫面回饋」真值的東西;與後端 `lat_us` 相減得到 proxy + loop 排隊那一段 | 零相依;dev build 的 entry 累積已有 `dev-perf-guard` 可沿用 | **建議導入(最優先)** |
| chrome-devtools MCP `performance_start_trace`(**已裝**)| 開盤時對閃電梯做一次 trace | #187 已有「93 s 內 >50 ms long task = 0」的先例判準,可直接沿用當驗收 gate;這是 §2 #1「輸入延遲」唯一的量法 | 需開盤取證 | **建議用(當驗收 gate)** |
| TanStack Query `defaultOptions`(內建)| `main.tsx` | `networkMode` / `staleTime` / `retry` 現在全是隱式預設,而其中一個(mutation networkMode)是 critical | 零相依;要逐項拍板,不可一次全改 | **建議導入(只改 mutations.networkMode)** |
| `@tanstack/react-query-devtools` | dev 觀察 query/mutation 狀態 | 能直接看到「哪個 observer 在輪詢、相位是什麼」,F-06/F-16 這類問題肉眼可見 | 新 devDependency;只在 dev build | **有條件導入**:F-06/F-16 修完就不太需要,但修之前很省事 |
| uvicorn `--no-access-log` + 自訂 request 中介層(只記非 2xx / 慢請求)| `server/__main__.py` | 9,345 行/日的 capital GET access log 是診斷的主要噪音來源(45.6% 的 log 行)。換成「只記慢的」同時解掉 F-05 的觀測代價 | 會失去「每個請求都有一行」的既有除錯慣例,要 user 拍板 | **有條件導入(需拍板)**:建議等 #5 把請求量降下來再評估 |
| `orjson` / `msgspec` | REST 回應編碼 | — | 新相依,與 stdlib-only 哲學衝突 | **不建議**:實測 orders N=200 的 `json.dumps` 只 0.505 ms,而 `orders()+asdict` 是 1.558 ms —— 瓶頸在建構不在編碼,換編碼器解不到 |
| `fetch` 的 `keepalive: true` | `fetchJson` | 想省掉 F-14 的新連線 | `keepalive` 的語意是「頁面卸載後仍送出」,不是連線重用,而且有 64 KB body 上限 —— **用錯地方** | **不建議** |
| `AbortController` + timeout | 送單 mutation | 想讓按鈕不要轉 10 秒 | ⚠ `client.py:899-902` 明文「單可能已出手」。**只能拿來換文案,不能真的 abort** | **有條件(只做文案,不做取消)** |
| `numpy` / `polars` / `winloop` | — | — | — | **明確不建議**:這一區零數值運算、零批次;route 層工作量 0.06 ms,換 event loop 實作的收益在量測噪音以下 |

---

## 10. Open questions

1. **prod 的實際 `store._orders` N 是多少?** 決定 F-09 / F-15 的優先序(N≈20 時全是雜訊,
   N≈200 時 orders 那支就是 1.45 ms + 95 KB)。量法:`curl -s localhost:8721/api/capital/orders | python -c "import sys,json;print(len(json.load(sys.stdin)['orders']))"`,
   連跑第 1 / 2 / 3 天各量一次。
2. **`navigator.onLine` 在這台機器上會不會誤判?** 決定 F-01 的實際發生率(嚴重度不變)。
   量法:在 `useCapitalStream` 加一行 `onlineManager.subscribe(v => console.warn("online", v))`,
   跑一天看有沒有 false。
3. **使用者按下送單後的主觀等待上限是多少?** 決定 F-07 的中間態要在幾毫秒後出現
   (1.5 s 是我猜的)。這是 user 拍板事項。
4. **閃電梯鎖定態下的實際連點峰值?** 決定要不要做前端速率限制(F/6)以及門檻。
   量法:#3 的探針 mark 就能直接統計每秒 click 數。
5. **`err_msg` 要不要原樣透傳給使用者?** 群益的訊息有些很長(「因您尚未簽署新版風險預告書,
   已可簽署,暫不可送下單!」),閃電梯的 hint 只有一行。要不要做對照表(常見碼 → 短句)
   還是原樣印,是 user 拍板事項。
6. **`OrderRecord.name` 該補還是該刪?**(F-10)補的話股名從哪來(route enrich 還是前端
   `useStockNames` 自己接),刪的話 `types.ts` 同動。
7. **WS payload 化(#5)之後,REST 的 60 s 保險輪詢還要不要?** 若要,對帳不一致時該怎麼處理
   (以誰為準、要不要留痕)—— 這決定它是「保險」還是「第二個真相源」。
