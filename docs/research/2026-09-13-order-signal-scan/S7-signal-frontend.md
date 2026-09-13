# S7 — 訊號:前端 UI 與互動(SignalRail / SignalRulesDialog / 四支 hook / signal-model)

分析日期:2026-09-13　|　範圍:`frontend/src/components/stock/SignalRail.tsx`、`SignalRulesDialog.tsx`、
`components/ToastStack.tsx`、`hooks/useSignalFeed.ts` / `useSignalAlerts.ts` / `useSignalRules.ts` /
`useSignalSound.ts`、`lib/signal-model.ts` / `signal-params.ts` / `signal-bus.ts`,以及接線端
`components/stock/StockPage.tsx`、`App.tsx`、`hooks/useStockStream.ts`、`main.tsx`。

**準繩**:這是要下實單的系統。訊號的 UI 不只是好看 —— 它是「人要不要動手」的唯一抵達路徑。
所以本報告把「看不到 / 晚看到 / 看到錯的」與「畫面卡」放在同一張表上衡量。

---

## 0. 量測方法與可信度聲明

| 項目 | 說明 |
|---|---|
| 環境 | Windows 11、node **v24.13.0**(與 Chrome 同一支 V8 世代);react **19.2.7**(自 `frontend/node_modules`) |
| 真實資料 | `data/signals/20260911.jsonl`(**686 列 prod 真實訊號**);另抽樣 20260903(613 列)對照 DevTools trace 窗 |
| 腳本 | `scratchpad/order-signal-scan/` 下 `rail-lib.mjs`(自 `signal-model.ts` / `SignalRail.tsx` **逐字移植**的純函式)、`bench-rail.mjs`、`bench-elements.mjs`、`bench-combined.mjs`、`bench-alert.mjs`、`bench-baseline.mjs`、`bench-split.mjs`、`sim-rollover.mjs` |
| 方法 | `process.hrtime.bigint()` 包住 2,000–200,000 次迭代、前置 3 次暖機、sink 防最佳化消除。Windows 15.6 ms timer 精度**不影響本批**(全部是 hrtime 長迴圈均攤,不是單次 sleep 量測)。 |
| 不可比的部分 | React **reconciliation / commit / paint** 未量(node 無 DOM)。本報告的 render 成本 = 推導 + `createElement`,**不含** diff 與 DOM commit;真實瀏覽器成本應更高(reconciler 走同樣 2,874 個 element)。 |
| prod vs dev | 全部 benchmark 都跑兩次(`NODE_ENV=production` / 未設)。差距 **7.6×**,是本區塊最大的單一數字,見 §2.2。 |

---

## 1. 現況地圖:訊號在前端怎麼流

### 1.1 兩條完全獨立的抵達路徑

```
後端 signal_hub._emit / _emit_policies
   │  (1) WS  /ws/stock  {"type":"signal",...}   ← 與 tick 同一條 WsBroadcaster 佇列(1000)
   │  (2) jsonl  data/signals/<YYYYMMDD>.jsonl   ← 真相源
   ▼
(1) useStockStream.ts:495-499  case "signal": emitSignal(msg)   ← 不過濾 code,全自選池
   ▼
lib/signal-bus.ts  module 級 EventTarget(單例)
   ├─ useSignalAlerts(掛在 App,**唯一**訂閱點)→ toast / 嗶 / 桌面通知
   └─ useSignalFeed (掛在 StockPage) setLive(prev => mergeSignals(prev,[sig]))
                                              ▼
(2) useQuery ["stock-signals-today"] ── GET /api/stock/signals/today(5 min 輪詢 + WS onopen invalidate + window focus)
                                              ▼
                        signals = useMemo(mergeSignals(baseline, live))   cap = 200
                                              ▼
                        SignalRail(純展示元件,props 由 StockPage 餵)
```

**關鍵結構事實**

- `signal-bus` 是 module 級 `EventTarget` 單例;`emitSignal` 同步 dispatch,兩個 listener 在同一個 WS
  message task 內跑完 → 兩個 `setState` 被 React 19 automatic batching 併成**一次** App render pass。
- `useSignalAlerts` 掛在 `App.tsx:163`(**常駐**,與 tab 無關);`useSignalFeed` / `SignalRail` 掛在
  `StockPage`(`App.tsx:121` 的 lazy + `visited` 閘:**沒進過個股 tab 就不存在**;進過之後
  `hidden` 保留、永不卸載)。
- 因此:**人在期貨 / TXO / 指數 tab 時,SignalRail 照樣每次 App render 都跑完整條推導 + element 建立**
  (`App.tsx:348` 是 `hidden={tab !== "stock"}`,不是條件 render)。

### 1.2 rail 的資料模型(`lib/signal-model.ts`)

| 函式 | 語意 | 每次 render 呼叫次數(200 列 / 173 組) |
|---|---|---|
| `mergeSignals(baseline, live, cap=200)` | 去重(id)→ **依 `time` 字串降冪重排** → 截 200 | 1(在 `useMemo` 內,**不隨 render 跑**) |
| `groupSignals(signals)` | 相鄰同 `(code,time)` 併一組;`key` = 組內**最早到**那則 id | 1(**未 memo**,每 render 跑) |
| `groupKindLabels(group)` | 到達序去重的 kind 文案段 | 173 |
| `groupRuleNames(group)` | 到達序去重的規則名 | 173 |
| `groupPolicyTags(group)` | 政策 chip(P / B-a / B-b / S) | 173 |
| `groupPolicies(group)` | 組內政策列(第三行脈絡來源) | 173 |
| `policyContextText(anchor)` | 第三行「同伴≥3% n・鎖過 有/無・+x.x%/停 y.y%」 | 17(政策組數) |
| `policyTitle(policies)` | **hover 才看得到**的全文 | 17 |
| `segmentTitle(seg)` / `ruleTitle(group,name)` | **hover 才看得到**的逐段提示 | ~180 / ~173 |

四支 `group*` 各自跑一次 `arrivalOrder(group) = [...group.items].reverse()`,
`ruleTitle` 再跑第五次 → **每組 5 次陣列複製**,173 組 = 865 個短命陣列 / render。

### 1.3 提示鏈(`useSignalAlerts`)

- **閘**:`shouldNotify(sig)`(`notify !== false`,缺欄 = true)—— 這一則 `return` 之後就什麼都不做。
  09-11 真實資料 **402 / 686(58.6%)`notify=false`**,所以提示鏈實際只處理 41%。
- **合併**:`groupIndexRef` 以 `code|time` 為鍵的**全索引**(與 rail 的「只併相鄰」刻意不等價,N013 已拍板)。
  TTL 5 s、剩餘 < 1.5 s 就另開新張。同時顯示 4 張,其餘走 `+N`。
- **嗶**:`beepFor(policy)` → `playBeep()`,政策列多一聲(+0.18 s)。單例 `AudioContext`,
  `closed` 回收重建、`suspended` 放棄這一聲並 `resume()`(單飛旗標)。靜音走
  `getSoundOn()` 的 **localStorage 直讀**(不快取)。
- **桌面通知**:只在 `document.hidden` 發;固定 `tag="copycat-signal"`(OS 層只有一格);
  合併窗 `COALESCE_MS = 300`、節流窗 `NOTIFY_MIN_INTERVAL_MS = 5000`;`pendingRef` 是
  **單槽 latest-wins**;`fire()` 到期時若人已回前景 → 丟棄且不記帳。
  **靜音不關桌面通知**(design §8.3 明文,正確)。

### 1.4 規則視窗(`SignalRulesDialog`)

- 常駐掛載、只切 `open`;`open` **不進 JSX**(`showModal()` 的 `InvalidStateError` 坑,沿
  `WatchlistManagerDialog` 樣板)。關閉時**不渲染內容** → 不在 render 熱路徑上。
- 表單值一律以字串存,轉型 + 值域檢查全收在 `submit()`。
- 前後端 parity 由 `lib/signal-params.ts`(`PARAM_FIELDS.min/max/integer`、`COOLDOWN_MIN/MAX`)
  對後端 `copycat/signal_rules.py`(`PARAM_SPECS`、`INT_PARAM_KEYS`、`COOLDOWN_MIN/MAX`),
  以共用 fixture `tests/fixtures/signal_param_specs.json` 兩邊各一條 parity 測試釘住。
  **已驗:六個 kind 的鍵集、值域、整數鍵與後端 `PARAM_SPECS` 逐格相同。**

---

## 2. 端到端延遲預算

### 2.1 單則訊號:WS frame 落地 → 人感知

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 1 | `JSON.parse` 一則訊號 wire | `ws-reconnect.ts` → `useStockStream` | **3.82 µs**(政策列,~1 KB) | 實測 | 一般列更小 |
| 2 | switch → `emitSignal` → EventTarget dispatch(2 listener) | `useStockStream.ts:497` / `signal-bus.ts:22` | **0.115 µs** | 實測 | 不可能是瓶頸 |
| 3 | `useSignalAlerts` handler 純計算(`shouldNotify` + index + `formatGroupToastText`) | `useSignalAlerts.ts:211-269` | **0.50 µs**(單則)/ **0.95 µs**(政策 3 則組) | 實測 | |
| 4 | `useSignalFeed` listener `mergeSignals(200 prev, [1])` | `useSignalFeed.ts:89` | **10.54 µs** | 實測 | O(n log n) 全排序,n=201 |
| 5 | React render pass(App 全樹,**prod build**) | — | **0.6 – 1.0 ms**(推估) | 推估 = 5,000–8,000 element × 實測 105–127 ns/element | 前一輪 F7 的 element 量級 |
| 5a | ├ 其中 **SignalRail**(200 列 / 2,874 element) | `SignalRail.tsx:170-295` | **365.6 µs** | 實測 | 開盤 20 列時 30.8 µs |
| 6 | 瀏覽器 layout + paint | — | 2 – 8 ms(推估,未量) | 推估 | |
| 7 | 嗶:`osc.start(currentTime)` → 喇叭出聲 | `useSignalAlerts.ts:107` | ~2.7 ms(render quantum)+ 20–40 ms(WASAPI 共享模式輸出 latency) | 推估 | 對「聽到有事」不重要 |
| 8 | 桌面通知(**背景分頁**)合併窗 | `useSignalAlerts.ts:266` | 設定 300 ms → **實際 ≥ 1 s**(背景 setTimeout clamp;code 自己註解了) | 推估(機制確定) | |
| 8a | 桌面通知(**長背景分頁 > 5 min**) | 同上 | **最壞 ~60 s**(Chrome intensive throttling,1 timer/min) | 推估 | §4 FM-06 |
| 8b | 桌面通知節流窗 | `NOTIFY_MIN_INTERVAL_MS` | 5 s | code | 固定 tag,OS 層本來就只有一格 |

> **可見 tab 的端到端 ≈ 1 – 9 ms**,其中 99% 在 React render + paint,而**訊號本身的處理不到 15 µs**。
> 提示鏈的純計算**不要動**。

### 2.2 常態底噪:SignalRail 在每次 App render 都付的錢(本區塊真正的成本)

`SignalRail` 完整 render function(推導 + `createElement`,**不含** reconcile / commit),實測:

| rail 列數(組數 / element) | **prod build** | dev build | @150 App render/s(prod) | @150(dev) |
|---|---|---|---|---|
| 20 列(294 el) | **30.8 µs** | 269 µs | 4.6 ms/s | 40.4 ms/s |
| 50 列(761 el) | **79.7 µs** | 737 µs | 12.0 ms/s | 110.5 ms/s |
| 120 列(1,753 el) | **201.3 µs** | 1,727 µs | 30.2 ms/s | 259.1 ms/s |
| **200 列 = cap(2,874 el)** | **365.6 µs** | **2,770 µs** | **54.8 ms/s** | **415.5 ms/s** |

- 前一輪 F7 量到 App 全樹重繪 **100–250 次/秒**(tick 驅動,與訊號無關)。
  → 收盤前 rail 滿 200 列時,`SignalRail` 一個元件就吃掉 **36.6 – 91.4 ms/s**(prod)的純 JS,
  等於 **3.7% – 9.1% 的單核**,而且 **人在期貨 tab 時照付**。
- **dev build 是 prod 的 7.6×**(2,770 / 365.6)。整天掛 `npm run dev` 時,單 SignalRail
  就是 **277 – 692 ms/s = 28% – 69% 的單核**。這是 CLAUDE.md §1「整天掛著一律用 prod build」
  那一行第一次有具體數字。
- **既有的 93 秒 DevTools trace(09-03 開盤、>50 ms long task = 0)沒有覆蓋最壞情況**:
  該窗(09:00–09:02)rail 只有 **66 列**(實測 20260903.jsonl)→ 約 100 µs/render。
  收盤前的 365.6 µs 是那個窗的 **3.7 倍**,從未被量過。

**其中 38% 是沒人看得到的 hover title**(實測,`bench-split.mjs`):

| 區段 | 200 列 / render | 占比 |
|---|---|---|
| 推導全部 | 166.8 µs | 100% |
| 扣掉 `segmentTitle` / `ruleTitle` / `policyTitle` | 103.4 µs | 62% |
| → **hover-only title** | **63.4 µs** | **38%** |
| 　├ `ruleTitle`(每組再 reverse 一次 + 逐 item `kindLabel`) | 54.1 µs | 32% |
| 　└ `policyTitle`(17 個政策組) | 19.2 µs | 12% |

### 2.3 baseline 自癒路徑(5 分鐘輪詢 / WS onopen / window focus)

| 區段 | 位置 | 成本 | 依據 |
|---|---|---|---|
| 後端讀整份 jsonl | `app.py:1581` `asyncio.to_thread(hub.today_signals)` | 未量(共用 loop 預設 executor,鄰居 = 最壞 20 s 不可中斷的 TC4 取數) | 前一輪 X1/X3 已立案 |
| wire 大小(09-11 686 列) | — | **264,200 B**(gzip 22,004 B) | 實測 |
| `JSON.parse(264 KB)` | TanStack `res.json()` | **614.3 µs**(主執行緒同步) | 實測 |
| `[...body.signals].reverse()` | `useSignalFeed.ts:53` | 0.8 µs | 實測 |
| `mergeSignals(686, 200)` | `useSignalFeed.ts:97` | **46.4 µs** | 實測 |
| **合計一次 baseline 重整** | | **≈ 0.66 ms 前端** + 一次後端整檔 jsonl 讀 | |
| 觸發頻率 | `refetchInterval` 5 min(分頁可見時)+ **每次 window focus**(`new QueryClient()` 零 default → `staleTime:0` + `refetchOnWindowFocus:true`) | 盤中 alt-tab 一次 = 264 KB + 一次後端整檔讀 | `main.tsx:16` |

> **`mergeSignals` 拿到 686 列、丟掉 486 列**:cap 200 是在**前端**、在傳輸與 parse **之後**才套。
> 後端 `today_signals()` **沒有任何上限**。

---

## 3. 主要 findings

### S7-01 `live` 跨日永不清空 → 次日 rail 的「今日訊號」裡**一則今天的都沒有** — **critical / 零錯誤訊號**

**位置**:`frontend/src/hooks/useSignalFeed.ts:83-97`

```ts
const [live, setLive] = useState<SignalMsg[]>([]);
useEffect(() => onSignal((sig) => setLive((prev) => mergeSignals(prev, [sig]))), []);
const signals = useMemo(() => mergeSignals(baseline ?? [], live), [baseline, live]);
```

`live` 只在元件卸載時消失,而 `StockPage` 一旦造訪就 `hidden` 保留、**永不卸載**
(`App.tsx:121` 註解明文)。`mergeSignals` 只以 `time`(`HH:MM:SS`)排序,**不看日期**
—— 訊號列其實有 `trade_date` 欄(實測 jsonl 每列都有),但前端 `SignalMsg`(`signal-model.ts:33-92`)
**沒有宣告它**,排序與去重都用不到。

**模擬證據**(`sim-rollover.mjs`,餵 20260911 真實 686 列):

```
昨日收盤 live 長度 = 200  時間區間 10:44:37 ~ 13:30:00
次日 09:05 rail 列數 = 200
其中屬於【今天】的 = 0          ← ★
rail 最上面三列: ['2026-09-11 13:30:00 3037', '2026-09-11 13:30:00 2327', ...]
```

機制:昨日 `live` 被 cap 成「time 最大的 200 則」= 10:44–13:30。次日 09:05 的新訊號
`time="09:05:xx"` 排在那 200 則之下 → `mergeSignals` 的 `slice(0,200)` **當場把它丟掉**,
連 `live` 都存不進去。今日 baseline 的列同樣被壓在 200 名外。
**畫面上 rail 只印 `HH:MM`(`SignalRail.tsx:198` `hhmm()`),沒有任何日期**,
而 stage2 之後 `tradeDate === today` → 標題印「**今日訊號**」。

**要到 10:44 之後**(今天的時刻超過昨日 cap 窗下界)今天的訊號才開始擠得進來。
整個早盤 —— 也就是訊號最有價值的時段 —— rail 是昨天的。

toast / 嗶 / 桌面通知**不受影響**(走 bus 直達),所以「有嗶但 rail 上找不到那一列」
就是這個 bug 的外顯形,而使用者只會以為自己看漏了。

**修法**:(a) `SignalMsg` 補 `trade_date?: string`,`mergeSignals` 排序鍵改
`` `${trade_date ?? ""} ${time}` ``(缺欄退回現況);(b) `useSignalFeed` 在
`baselineQuery.data.tradeDate` 變動時 `setLive([])`。兩者都要 —— (b) 修今天這一份,
(a) 修跨午夜聯集那一份(見 S7-02)。

**風險**:`mergeSignals` 的排序穩定性與「live 在前」語意(CC-3 / review 已釘)不可動;
只加排序鍵的前綴,不改比較方向與參數順序。`signal-model.test.ts` 51 條 + `useSignalFeed.test.tsx` 護著。

---

### S7-02 兩日聯集時依 `HH:MM:SS` 排序 → 跨午夜 rail 錯序 — **high / 零錯誤訊號**

**位置**:`lib/signal-model.ts:179`

```ts
out.sort((a, b) => (a.time === b.time ? 0 : a.time > b.time ? -1 : 1));
```

後端 `signal_hub.today_signals()`(`signal_hub.py:1433`)在 **engine 日別 ≠ 牆鐘日**時
回傳**兩天的聯集**(「日期字串升冪串接,舊日在前」)。這在每天午夜到次日 stage2 之間**必然發生**,
以及「空自選 / 零推播讓 engine 日別停在昨日」的常態。

前端 `fetchToday` 只 `.reverse()` 整份(`useSignalFeed.ts:53`),再交給只看 `time` 的排序
→ **昨日 13:30 的鎖漲停排在今日 09:00 的掃單簇上面**。標題此時是「MM-DD 訊號」(因為
`tradeDate !== today`),所以至少有一句話說「這不是今天」,但列與列之間分不出是哪一天。

**修法**:與 S7-01 (a) 同一處。

---

### S7-03 `SignalRail` 零 memo,完整 render 掛在 100–250 Hz 的 App 重繪上 — **high**

**位置**:`SignalRail.tsx:174`(`groupSignals(signals).map(...)`)、`StockPage.tsx:235-258`

實測 **365.6 µs / render(200 列,prod build)**,= 36.6–91.4 ms/s(§2.2)。
`SignalRail` 既不是 `React.memo`,列也不是獨立元件,所以每次 App render 都重跑
**推導(166.8 µs)+ 2,874 個 `createElement`(198.8 µs)**。

`signals` 的 identity 是穩定的(`useSignalFeed.ts:97` 的 `useMemo`,deps `[baseline, live]`),
所以 memo 命中率接近 100% —— **但目前一格 memo 都沒有**。

**而且 `React.memo(SignalRail)` 單獨做沒有用**:`StockPage` 餵進去的 5 個 callback prop
每次 render 都換身分:

```tsx
// StockPage.tsx:205  function toggleRule(rule) {...}        ← 函式宣告,每 render 新身分
// StockPage.tsx:219  function requestNotif() {...}          ← 同上
// StockPage.tsx:241  onOpenManager={() => setRulesOpen(true)}   ← inline arrow
// StockPage.tsx:245  onSelect={(next) => {...}}                 ← inline arrow
// StockPage.tsx:253  onToggleSound={setSoundOn}                 ← 這個是穩定的(useSignalSound 回傳模組函式)
```

**修法(兩步,順序不可反)**:

1. `StockPage` 把 `toggleRule` / `requestNotif` / `onOpenManager` / `onSelect` 包 `useCallback`
   (`onSelect` 的 deps 含 `view` / `wl` / `pickedGroup`,要一起處理)。
2. `SignalRail` 內把每一列抽成 `const SignalRow = memo(function SignalRow({group, onSelect}) {...})`,
   並把 `groupSignals(signals)` 包 `useMemo`(讓 `group` 物件 identity 穩定)。

改完後 rail 的每 render 成本 ≈ 173 次 memo 淺比較 + 173 個 `createElement`
≈ **18–25 µs**(推估,以實測 105 ns/element),即 **15–20×**。

**風險**:`group.key` 的「錨在最早到那則」語意(review C-4 / T-11)必須保留 —— `groupSignals`
的 `last.key = sig.id` 那一行是新訊號前插時避免整列重掛的關鍵,memo 之後它**更重要**
(key 換 = memo 失效 + 卸載重掛)。`SignalRail.test.tsx` 43 條護著。

---

### S7-04 38% 的 rail 推導花在沒人看的 hover `title` 上 — **medium**

**位置**:`SignalRail.tsx:100-112`(`segmentTitle` / `ruleTitle`)、`SignalRail.tsx:255 / 270 / 283`

```tsx
<span className={toneOf(seg.sig)} title={segmentTitle(seg)}>      // 每段
<span title={ruleTitle(group, name)}>{name}</span>                // 每個規則名
<span ... title={policyTitle(policies)}>                          // 每個政策組
```

實測 **63.4 µs / render(200 列)= 全推導的 38%**,其中 `ruleTitle` 一支就 54.1 µs —— 它對每個
規則名再做一次 `[...group.items].reverse()` 並對每則呼叫 `kindLabel`,是本檔最貴的單一函式。

這些字串只有滑鼠停在那一列上才會被讀出來,**一天大概發生個位數次**,卻每秒算 150 遍。

**修法**:S7-03 做完 memo 之後這一項自動消失(每列只在 group 換身分時算一次)。
**不要**單獨拿掉 title —— hover 全文是 review F-18 / T-12 明文要求的資訊(政策列的
`first_of_day` 逐標記差異只有 hover 看得到)。

---

### S7-05 WS 佇列丟掉的訊號 frame,**永遠不會 toast / 嗶 / 桌面通知** — **high / 零錯誤訊號**

**位置**:`copycat/server/ws.py:65-80`(丟最舊保最新)+ `useSignalFeed.ts` / `useSignalAlerts.ts`

訊號與 tick 共用同一條 per-client 佇列(實測 `signal_hub.py:1016 / 1125` 的
`{"type":"signal"}` 走 `publish()`)。佇列滿時**丟最舊** —— 開盤爆量正是佇列會滿、
也正是訊號最密集的時刻(實測 09:00 那一分鐘 42 則)。

丟掉之後:

- **rail**:5 分鐘後的 baseline 輪詢會把它補回來(前提:分頁可見)→ 使用者只是晚 5 分鐘看到。
- **toast / 嗶 / 桌面通知**:`useSignalAlerts` 只訂 bus,**baseline 重抓不會回放到 bus**
  → 那一則的提示**永久不發**。人若正在看期貨 tab,等於完全沒發生過。
- tick 有 `seq` 跳號自癒;**訊號沒有任何序號**,前端無從得知丟了。

**修法**(擇一,不必全做):
- 最小:`/api/health` 或 badge 曝露 `WsBroadcaster.window_dropped`,讓「這一窗丟過東西」看得見。
- 正解:訊號列補一個單調 `seq`(每條 WS 各自計數),前端偵測跳號時只針對訊號重抓 baseline 並
  **把補回來的未見過訊號回放到 bus**(以 `id` 去重,`useSignalAlerts` 已有 `groupIndexRef` 可擋重複)。

**風險**:回放會讓「重啟後同 id 重發」變成重複提示 —— 需要一個 per-session 的 `seenIds` 集合
(上限即 cap 200)。`useSignalAlerts.test.tsx` 46 條護著。

---

### S7-06 桌面通知在長背景分頁最壞晚 ~60 s,且單槽只留最後一則 — **high / 零錯誤訊號(推估)**

**位置**:`useSignalAlerts.ts:119-125, 260-269`

```ts
const COALESCE_MS = 300;
pendingRef.current = text;                       // ★ 單槽 latest-wins
if (notifyTimerRef.current === undefined) {
  const at = Math.max(now + COALESCE_MS, lastNotifyRef.current + NOTIFY_MIN_INTERVAL_MS);
  notifyTimerRef.current = window.setTimeout(fire, at - now);
}
```

code 註解已經承認背景分頁的 clamp 讓合併窗變 ≈1 s。**但漏了 Chrome 的 intensive throttling**:
分頁隱藏且**靜音**超過 5 分鐘後,`setTimeout` 被降到**每分鐘一次**。看盤機把瀏覽器縮到背景
正是這個條件。後果:

- 首則桌面通知最壞晚 **~60 s**;
- `pendingRef` 是**單槽**,那 60 秒內的所有訊號只剩**最後一則**的文案會送到 OS;
- `fire()` 到期時若人剛好回前景 → `if (!document.hidden) return;` **整批丟棄**,
  而 toast 早就 TTL 過期了 → **那 60 秒的訊號一則都沒抵達過人**。

**放大器**:`beepFor` 會播音訊,而「正在播放音訊」是 intensive throttling 的豁免條件之一。
所以 **把提示音關掉,會順帶把桌面通知的延遲從 ~1 s 惡化到 ~60 s** —— 兩個開關在 UI 上
毫無關聯,而 code 裡也沒有任何一行提到這件事。

**標記為推估**:機制與門檻取自 Chrome 的 timer throttling 政策,**本輪沒有在真瀏覽器量過**。
量法見 §6 fix_plan 第 7 步。

**修法**:`pendingRef` 由單槽改成小陣列(上限 4~8,文案合併成「n 則:…」);
合併/節流 timer 改掛 `ServiceWorkerRegistration.showNotification`,或至少在
`document.visibilitychange → hidden` 時把窗改短。最小改動 = 單槽改陣列(把「只剩最後一則」修掉),
延遲那一半留給量測後再決定。

---

### S7-07 cap 200 靜默截掉當日 71% 的訊號,且**沒有溢出計數** — **medium / 零錯誤訊號**

**位置**:`lib/signal-model.ts:167-181`(`cap = 200`)

實測 09-11 共 686 列,rail 的 200 列只覆蓋 **10:44:37 – 13:30:00**。
早上 10:44 之前的所有訊號(486 則,71%)在 UI 上**永遠不可達** —— 沒有捲軸盡頭提示、
沒有「+486」、沒有日期欄。toast 有 `overflow` 計數(`ToastStack.tsx:40`),rail 沒有。

且這 264 KB 已經傳過來、parse 過了(§2.3)才被丟掉。

**修法**:rail 底部加一列「另有 n 則較早的訊號」(數字 = `baseline.length + live.length - 200`,
去重後)。不建議直接放寬 cap —— 那會讓 S7-03 的成本線性上升。

---

### S7-08 舊 dist 遇到新 rule kind:「編輯」按了沒反應,**而 ErrorBoundary 救不了** — **medium / 零錯誤訊號**

**位置**:`SignalRulesDialog.tsx:74-78`(`toForm`)

```ts
function toForm(rule: SignalRule): FormState {
  const params: Record<string, string> = {};
  for (const field of PARAM_FIELDS[rule.kind]) {   // ★ 未知 kind → undefined → TypeError
```

`PARAM_FIELDS` 是 `Record<RuleKind, ...>`,索引未知字串得 `undefined`,`for...of undefined`
丟 `TypeError: undefined is not iterable`。呼叫點是 `onClick`(`SignalRulesDialog.tsx:399-403`)。

**對 CLAUDE.md §4 該條的一項校正**:那裡寫「onClick 內 TypeError、**零 ErrorBoundary**」,
容易讀成「加 ErrorBoundary 就好」。實際上 **React 不攔 event handler 的例外**(它不經過
error boundary,也不會走 `createRoot` 的 `onUncaughtError` —— 而 `main.tsx:19` 本來就沒傳 options)。
所以:
- **症狀不是白屏**,是「按了沒反應 + console 一行紅字」,元件樹完好;
- **加 ErrorBoundary 完全不會改變這個行為**。

已驗證 rail 那一側確實不炸:`kindLabel`(`signal-model.ts:153`)未知 kind 原樣回傳、
`toneOf` 有 default、`KIND_LABEL[rule.kind]` 得 `undefined` React 渲染成空 —— 與 CLAUDE.md
「訊號列對舊 dist 不炸」一致。render 路徑上唯一的 `PARAM_FIELDS[form.kind].map`
(`:480`)只在 `form.kind` 已經是合法 kind 時才到得了(`toForm` 先炸)。

**修法**(不要加 ErrorBoundary):
```ts
const fields = PARAM_FIELDS[rule.kind] ?? [];      // toForm
```
加上列表列渲染一顆「此規則種類需要更新前端」的膠囊,並把「編輯」鈕 disable。
後端已有 `VersionDriftBadge`(`App.tsx:327`),但它是全站層級的膠囊,**不會告訴使用者
「你正要點的這顆鈕現在是壞的」**。

---

### S7-09 同 kind 新增 param 時,舊 dist 的「編輯→儲存」拿到泛用 INVALID_RULE — **medium**

`toForm` 只抄 `PARAM_FIELDS[kind]` 列的鍵(`:76-78`),`submit` 也只送那些鍵(`:260-273`)。
後端 `_normalize_params` 是**精確鍵集**(`signal_rules.py:70` 註解:「多鍵 / 缺鍵同樣是 INVALID_RULE」)。
所以後端加一個參數而前端沒跟 → 使用者按儲存只拿到「規則設定不合法」,**而他什麼都沒改**。

fixture parity(`tests/fixtures/signal_param_specs.json`)釘的是**同一次 commit 的兩邊**,
釘不住「跑著的 server 與瀏覽器裡的 dist 不同版」。

**修法**:`parseError` 的 `INVALID_RULE` 文案在 dialog 內改成帶版本提示的長句,或
`errText` 多一格「規則設定不合法(若剛更新過後端,請先重新整理)」。成本近零。

---

### S7-10 規則改名撞名時,前端不擋也不指出是名稱 — **low**

後端 `normalize_rule`(`signal_rules.py:221`)對重名 raise INVALID_RULE。
前端 `submit()`(`:243-295`)檢查了空名 / 非數字 / 整數鍵 / 值域 / cdp 零線,**唯獨沒檢查重名**,
而 `rules` 就在 props 裡(`SignalRulesDialog.tsx:154`)。使用者只會看到泛用文案。

**修法**:`submit` 內加
`if (rules.some(r => r.id !== form.id && r.name.trim() === name)) { setLocalError("已有同名規則"); return; }`

---

### S7-11 通知權限被拒時畫面**零指示**,背景分頁整條提示鏈死 — **medium / 零錯誤訊號**

**位置**:`SignalRail.tsx:341-349`

```tsx
{notifPermission === "default" ? (<button ...>允許通知</button>) : null}
```

註解說得對:`denied` 再呼叫也會被靜默拒絕。但結果是 **`granted` 與 `denied` 在 UI 上長得一模一樣
(都是沒有那顆鈕)**。配上靜音開著時:人切到別的 app → 沒有 toast(看不到)、沒有嗶、沒有桌面通知
→ **整條提示鏈是死的,而畫面上沒有任何跡象**。對要下實單的系統,這是「以為有人會叫我」的最糟形狀。

**修法**:`denied` 時印一行灰字「桌面通知已被瀏覽器封鎖(需到網站設定開啟)」;
`granted` 時印「桌面通知 開」。三態各一句,零成本。

---

### S7-12 `staleTime: 0` + `refetchOnWindowFocus` → 每次 alt-tab 重抓 264 KB 訊號 baseline — **medium**

**位置**:`main.tsx:16` `new QueryClient()`(零 defaultOptions)

TanStack v5 的預設是 `staleTime: 0` + `refetchOnWindowFocus: true`。盤中 alt-tab 回來一次
= 所有 active query 一起重抓,其中訊號 baseline 是 **264 KB + 一次後端整檔 jsonl 讀**
(`app.py:1581` 的 `to_thread`,鄰居是最壞 20 s 不可中斷的 TC4 取數)。

**這一條同時是好事**:它正是背景分頁停止輪詢(`refetchIntervalInBackground: false`)之後
唯一的自癒路徑(FM-05)。所以**不要關掉 focus refetch**,要縮的是 payload。

**修法**:後端 `/api/stock/signals/today` 加 `?limit=` 查參(預設無上限、前端送 `limit=250`),
或至少讓端點支援 `since=<time>`。省下 ~75% 的 wire 與 parse。
**注意 CLAUDE.md 的「無查參」設計**:那條說的是「未宣告的查參一律忽略,舊 bundle 照樣 200」——
新增一個**可選**查參不違反它(舊 bundle 不送 = 維持現況)。

---

### S7-13 `useSignalSound` 的 localStorage 直讀掛在 render 路徑上 — **low(推估)**

**位置**:`useSignalSound.ts:20-22, 43`

```ts
export function getSoundOn(): boolean { return readLocal(SOUND_KEY) !== "off"; }
const soundOn = useSyncExternalStore(subscribe, getSoundOn, getSoundOn);
```

`getSnapshot` 在**每次** render 被 React 呼叫(App 的 `useSignalAlerts` 一次 + StockPage 的
`useSignalSound` 一次)→ 100–250 Hz × 2 = **200–500 次 localStorage 同步讀 / 秒**。
Chrome 的 localStorage area 在 renderer 內有快取,單次 `getItem` 通常 < 1 µs,所以**量級上大概率無害**,
但它是同步 storage API,而且 `readLocal` 外面包了一層 try/catch。

**本輪未在瀏覽器量過 → 標記推估。** 若要改,module 級快取 + `setSoundOn` 主動失效 + `storage`
事件監聽(順便修「另一個分頁改了音效開關本頁不知道」)即可,是一個三行的 deep module。
**不是現在要動的東西**,列在這裡是為了在 §6 的量測步驟裡一起量掉。

---

### S7-14 mutation error 殘留:回到列表仍顯示上一次的錯誤 — **low**

**位置**:`SignalRulesDialog.tsx:297-299`

```ts
const mutationError = save.error?.message ?? del.error?.message ?? null;
```

「取消」只 `setForm(null); setLocalError(null)`(`:558-561`),**不 reset mutation**。
`save.error` 會留到下一次 `mutate` 為止 → 回到列表頁仍頂著一行紅字。
`open` 翻轉時會清 `localError` 但同樣不清 mutation(`:194-201`)。

**修法**:取消 / 關閉時多呼叫 `save.reset(); del.reset();`。

---

### S7-15 `useSignalFeed` 只在 StockPage 存在 —— 沒進過個股 tab 就沒有 baseline 自癒 — **low**

`App.tsx:127` `stock: tab === "stock"`。使用者開站停在指數 tab 時,`useSignalAlerts`(App 常駐)
照樣發 toast / 嗶 / 桌面通知,但 **rail 與 baseline 都不存在** → 這段時間 WS 丟掉的訊號沒有
任何補回路徑,而且一旦之後進個股 tab,baseline 會補回 rail 但那些訊號的提示早就錯過了。
與 S7-05 同一根因(提示鏈只吃 WS)。屬知情取捨,列出備查。

---

### S7-16 訊號抵達路徑本身**極快,不要動** — **參考**

實測:`emitSignal` dispatch **0.115 µs**、`formatGroupToastText` **0.50 / 0.95 µs**、
`mergeSignals(200,[1])` **10.5 µs**。真實到達率:09-11 全日 686 則,**尖峰 42 則/分鐘 = 0.7/s**,
單秒最多 4 則。整條提示鏈每秒的純計算 **< 10 µs**。

每則訊號觸發的 App render:抵達 1 次(`setQueue` + `setLive` 被 batching 併掉)+ TTL 到期
`drop()` 1 次 = **≤ 1.4 render/s**,相對 tick 驅動的 100–250 render/s 是捨入誤差。

**結論:訊號多不會讓畫面卡。讓畫面卡的是 tick,而訊號 rail 是被 tick 拖著跑的乘客。**

---

## 4. 失效模式表

| # | 失效 | 觸發 | 症狀(人看到什麼) | 零訊號 | 位置 | 嚴重度 | 現在怎麼發現 |
|---|---|---|---|---|---|---|---|
| FM-01 | `live` 跨日不清 → 次日 rail 零今日訊號 | 分頁掛過夜 + 進過個股 tab | 標題「今日訊號」,列全是昨天的;有嗶但 rail 找不到那一列 | ✅ | `useSignalFeed.ts:83-97` | **critical** | 發現不了。要加:rail 列顯示日期,或 `trade_date !== tradeDate` 時印警示列 |
| FM-02 | 兩日聯集依 `HH:MM:SS` 排序 → 跨午夜錯序 | 每天午夜~次日 stage2;空自選讓 engine 日別停在昨日 | 昨日 13:30 排在今日 09:00 上面 | ✅ | `signal-model.ts:179` | high | 同 FM-01 |
| FM-03 | WS 佇列滿丟訊號 frame | 開盤 tick 爆量(佇列 1000) | 該則**永不** toast/嗶/通知;rail 5 分鐘後才出現 | ✅ | `ws.py:65-80` | high | 盤後 `grep "佇列滿" logs/server-*.log`(有訊號被丟時不會特別說)。要加:訊號 `seq` 或 `/api/health` 曝露 `window_dropped` |
| FM-04 | cap 200 截掉早盤 71% | 每天 10:45 之後 | 捲到底就沒了,沒有「還有 486 則」 | ✅ | `signal-model.ts:180` | medium | 發現不了。要加:溢出計數列 |
| FM-05 | 背景分頁 baseline 輪詢停擺 | 分頁切走 | 回來前那段的丟包不補 | ⚠ 半 | `useSignalFeed.ts:82`(TanStack `refetchIntervalInBackground:false`) | medium | window focus 會自癒(S7-12),所以**只在「視窗仍 focus 但分頁 hidden」的情境**持續 |
| FM-06 | 長背景分頁通知晚 ~60 s + 單槽只剩最後一則 | 分頁隱藏 > 5 min 且無音訊 | 一批訊號只跳出一則、且晚很久 | ✅ | `useSignalAlerts.ts:119-125,264` | high | 發現不了(推估,待真瀏覽器驗) |
| FM-07 | 關靜音 → 失去 audio 豁免 → FM-06 惡化 | 使用者按「提示音 關」 | 桌面通知變更晚 | ✅ | `useSignalAlerts.ts:63-67` | medium | 發現不了(推估) |
| FM-08 | 通知權限 denied 無指示 | 使用者曾按過「封鎖」 | 背景時完全無提示,UI 與「已授權」一模一樣 | ✅ | `SignalRail.tsx:341` | high | 發現不了。要加:三態各一句文案 |
| FM-09 | 舊 dist + 新 rule kind → 編輯鈕沒反應 | 只 build 後端沒 build 前端 | 點「編輯」毫無反應,console 一行 TypeError | ✅(對非開發者) | `SignalRulesDialog.tsx:76` | medium | 開 DevTools 才看得到。**ErrorBoundary 不救**(event handler 不經 boundary) |
| FM-10 | 舊 dist + 既有 kind 新增 param | 同上 | 按儲存 →「規則設定不合法」,但什麼都沒改 | ✅ | `SignalRulesDialog.tsx:76,260` | medium | 發現不了 |
| FM-11 | dev build 整天掛著 | 用 `npm run dev` 看盤 | 下午整頁鈍;SignalRail 一支就 277–692 ms/s | ⚠ | §2.2 實測 | high | 感覺得到,但歸因不到 rail。CLAUDE.md §1 已有規矩 |
| FM-12 | 規則重名 | 改名撞到既有規則 | 泛用「規則設定不合法」,不知是名稱 | ⚠ | `SignalRulesDialog.tsx:243` | low | 錯誤有顯示,只是不精確 |
| FM-13 | mutation error 殘留 | 儲存失敗後按取消 | 列表頁頂著上一次的紅字 | ⚠ | `SignalRulesDialog.tsx:297` | low | 看得到(但會誤導) |
| FM-14 | `AudioContext` 被系統回收 / autoplay 未解鎖 | 系統睡眠醒來、未互動 | 那一則不出聲(下一則恢復) | ⚠ | `useSignalAlerts.ts:80-99` | low | 已知情、註解完整,**不要動** |
| FM-15 | 沒進過個股 tab → 無 rail / 無 baseline | 開站停在指數 tab | 只有 toast,沒有列表,丟包無補回 | ⚠ | `App.tsx:127` | low | 進 tab 後 baseline 會補 rail,但提示已錯過 |

---

## 5. 明確「不要動」的部分

| 對象 | 理由 |
|---|---|
| `lib/signal-bus.ts` 整檔 | 實測 dispatch **0.115 µs**。EventTarget 單例是這一區塊最乾淨的 seam,換成 zustand / context 只會多一份 state。 |
| `formatGroupToastText` / `kindLabel` / `_kind_text` 文案 | CLAUDE.md §4 明文:與後端 `_kind_text` **逐字對齊**(含「零也帶正號」)。有 `signal-model.test.ts` 字面釘住。任何「順手統一格式」都會讓 Discord / jsonl / WS 三邊對帳變人工比對。 |
| `groupSignals` 的 `last.key = sig.id`(錨在最早到那則) | review C-4 / T-11 修過的坑;拿組首 id 當 key = 每多併一則就整列卸載重掛。memo 化之後更關鍵。 |
| `mergeSignals` 的排序穩定性 + 「live 參數在前」 | review CC-3:去重後必須重排,否則 WS 重連補回的訊號被埋在舊 live 之下。改排序鍵時**只加前綴**,不動比較方向與參數順序。 |
| `useSignalAlerts` 的 `groupIndexRef` 全索引 vs rail 的相鄰併組**刻意不等價** | N013,2026-08-24 user 拍板不改。兩者載體不同(浮動卡片 vs 有序清單)。 |
| `playBeep` 的 `closed` / `suspended` 分支與 `resuming` 單飛旗標 | review F2 / F4 實測修過的;`suspended` 時 `currentTime` 凍結會讓已 start 的節點整天不可 GC。 |
| `ToastStack.tsx` | ≤ 4 張卡 + 一個 `+N`,`toasts.length === 0 && overflow === 0` 時整個不掛。零可省。 |
| `useSignalSound` 用 `useSyncExternalStore` | 回傳 boolean 純值 → Object.is 穩定,不會無限重繪;跨元件樹同步是這裡唯一正解。(FM 只在 render 頻率上,見 S7-13) |
| `SignalRulesDialog` 的 `open` 不進 JSX + 關閉時不渲染內容 | 真瀏覽器踩出來的 `InvalidStateError` 白畫面坑;而且讓 dialog 完全不在 render 熱路徑上。 |
| `lib/signal-params.ts` 的 parity fixture 機制 | 六個 kind 的鍵集 / 值域 / 整數鍵已逐格核對後端 `PARAM_SPECS`,**完全一致**。 |

---

## 6. 改造順序(每一步附量測判準)

> 全程 gate 沿 CLAUDE.md §1:`npm test` + `npx tsc -b` + `npx eslint src` +
> `npx react-doctor@latest --scope changed --no-telemetry`(在 `frontend/`)。

### 步驟 1 — 先裝儀器(**先量後改**)
把 `SignalRail` 與 `App` 各包一顆 `<Profiler>`(dev-only),把 `onRender` 的 `actualDuration`
打進一個 module 級 histogram,並在 dev 加一顆隱藏的 `window.__railStats()`。
**判準**:prod build 下午 13:00 的個股 tab,收 60 s,印出 `SignalRail` 的
render 次數 / p50 / p99 與 `signals.length`。這是後面每一步的 baseline。
**回退**:純新增 dev-only code,刪掉即可。

### 步驟 2 — FM-01 / FM-02(correctness 優先於 perf)
`SignalMsg` 補 `trade_date?: string`;`mergeSignals` 排序鍵改 `` `${a.trade_date ?? ""} ${a.time}` ``;
`useSignalFeed` 在 `tradeDate` 變動時 `setLive([])`。
**判準**:(a) 新增測試 —— 餵「昨日 200 則 + 今日 45 則」,斷言輸出前 45 列全是今日
(現況跑這條會紅:`sim-rollover.mjs` 實測今日列數 = **0**);(b) 兩日聯集的排序測試;
(c) 真環境 —— 分頁掛過夜,次日 09:10 rail 首列時間 < 09:10 且標題「今日訊號」。
**回退**:單一 commit,revert 即回現況。

### 步驟 3 — FM-08 / FM-12 / FM-13(零成本的可見性補丁)
通知權限三態各一句文案;`submit` 加重名檢查;取消/關閉時 `save.reset()` / `del.reset()`。
**判準**:`SignalRail.test.tsx` 加三條(`granted` / `denied` / `default` 各印什麼);
`SignalRulesDialog.test.tsx` 加兩條。
**回退**:純 UI 文案 + 一個 early return。

### 步驟 4 — FM-09 / FM-10(舊 dist 防禦)
`toForm` 的 `PARAM_FIELDS[rule.kind] ?? []`;列表列對未知 kind 顯示「需要更新前端」膠囊 +
disable 編輯鈕;`errText("INVALID_RULE")` 補版本提示尾句。
**判準**:測試餵一條 `kind: "future_kind"` 的規則 —— 現況點編輯會丟 TypeError(測試會紅),
改完後列得出來、編輯鈕 disabled、膠囊在。**不加 ErrorBoundary**(event handler 不經它)。
**回退**:三處 defensive default,revert 即回。

### 步驟 5 — S7-03 第一半:穩定 `StockPage` 的 callback prop
`toggleRule` / `requestNotif` / `onOpenManager` / `onSelect` 包 `useCallback`。
**判準**:步驟 1 的 Profiler —— 這一步**單獨做完 render 次數與時間不會變**(memo 還沒加),
所以判準是 **eslint `react-hooks/exhaustive-deps` 零新增 warning** + 既有 43 + 30 條測試全綠 +
手動驗「點訊號列切標的 / 群組切換」行為逐字不變。
**回退**:單一 commit。**這一步不可與步驟 6 合併 commit** —— 合併之後 memo 沒生效時分不出是哪一半錯。

### 步驟 6 — S7-03 第二半:`useMemo(groupSignals)` + `memo(SignalRow)`
把每列抽成 `const SignalRow = memo(function SignalRow({ group, onSelect }) {...})`,
`groupSignals(signals)` 包 `useMemo([signals])`。S7-04 的 hover title 成本隨之消失。
**判準**:步驟 1 的 Profiler,同一個 13:00 / 200 列 / 60 s 窗:
`SignalRail` 的 **p50 `actualDuration` 從 ~0.37 ms 降到 < 0.05 ms**(目標 ≥ 7×);
render **次數不變**(memo 省的是子樹不是自己)。
外加 DevTools Performance 93 s trace 對照:>50 ms long task 維持 0、
`Scripting` 總時數下降。
**回退**:兩個 commit(memo 行為零改動,🔵 純重構),revert 任一半都能跑。

### 步驟 7 — FM-06 / FM-07 的**真實量測**(先量,不要先改)
真瀏覽器:prod build、開個股 tab、把視窗最小化 8 分鐘、期間讓後端發 3 則相隔 20 s 的
`notify=true` 訊號,記錄每則桌面通知的實際抵達時刻;再重複一次「提示音開」的對照組。
**判準**:量到的延遲若 p99 < 2 s,FM-06/07 降級為 low 並結案;若出現 > 10 s 的單次,
才做「單槽改陣列 + ServiceWorker showNotification」。
**回退**:不改 code,純量測。

### 步驟 8 — FM-04 溢出計數
rail 底部加一列「另有 n 則較早的訊號」。
**判準**:測試斷言 686 列輸入時那一列印「另有 486 則」;真環境 14:00 看得到。
**回退**:一個 `<li>`。

### 步驟 9 — S7-12 payload 瘦身
後端 `/api/stock/signals/today` 加**可選** `?limit=`(不帶 = 現況無上限,舊 bundle 不受影響),
前端送 `limit=250`。
**判準**:`curl -s "127.0.0.1:8721/api/stock/signals/today?limit=250" | wc -c` 約 **≤ 100 KB**
(現況 264 KB);不帶 limit 的回應**逐位元組不變**(舊 bundle 相容);
DevTools Network 在 alt-tab 回來時該 request 的 size 下降 ≥ 60%。
**回退**:後端查參可選、前端一個字串常數。

### 步驟 10 — FM-03 訊號丟包可觀測(**最後做,改動最大**)
訊號列補 per-connection 單調 `seq`;前端偵測跳號 → 只重抓訊號 baseline →
把未見過的訊號(per-session `seenIds`,上限同 cap)**回放到 bus**。
**判準**:後端測試 —— 人為丟一則後前端能補上且**恰好**多發一則 toast;
盤中 `grep "佇列滿" logs/server-*.log` 命中時,前端 console 應有對應的「訊號跳號補抓」一行。
**回退**:`seq` 是 additive 欄(缺欄 = 舊行為),前端偵測可用一個 feature flag 關掉。

---

## 7. 工具評估

| 工具 | 用在哪 | 為什麼 | 取捨 | 結論 |
|---|---|---|---|---|
| **React `<Profiler>` + 自寫 histogram** | `SignalRail` / `App` | 目前**前端零 render 計數**(前一輪已立案)。步驟 6 的判準沒有它就只能靠感覺 | dev-only,prod 不裝;`Profiler` 本身有 ~5% overhead | **建議導入**(步驟 1 的前置) |
| **babel-plugin-react-compiler(React Compiler)** | 全 frontend | 自動 memo,一次解決 S7-03 + F5-09 + 前一輪 F7 的整批「未 memo」 | React 19.2 相容,但它會改變**所有**元件的 memo 邊界 —— 本 repo 有多處「刻意不 memo」與「刻意 memo 邊界」的長註解(ChartStatic / GroupCard / RiverCard),全交給編譯器等於把那些拍板一次失效;且需要全量回歸 3,069 條前端測試 | **有條件導入**:先在 `SignalRail` 一支上以 `"use memo"` 試點,量出來與手寫 memo 同級再談擴大 |
| **@tanstack/react-virtual** | SignalRail 列表 | 200 列 × 17 element 是虛擬化的典型甜蜜點 | 但手寫 memo 已能拿到 15–20×,而虛擬化會讓 hover title、捲動位置保持、`aria` 清單語意都要重做;rail 只有 200 列上限(不像 `LimitListSection` 可到 400+) | **不建議**(先做步驟 6;若之後放寬 cap 到 1000 再重評) |
| **`ServiceWorkerRegistration.showNotification` + `requireInteraction` + click handler** | 桌面通知 | 目前 `new Notification(text, {tag})` 沒有 click handler → 收到通知**無法一鍵回分頁**;且長背景分頁受 timer throttling(FM-06) | 需要一支 service worker(專案目前零 SW),會牽動 Vite build 與 `npm run preview` 的流程 | **有條件導入**:等步驟 7 量到真的 > 10 s 再做 |
| **Web Worker 解 baseline JSON** | `fetchToday` | 264 KB parse 阻塞主執行緒 | 實測只有 **614 µs**,一天最多幾十次 | **不建議** —— 不成比例(步驟 9 的瘦身便宜得多) |
| **Zod / valibot 驗 WS 訊號 payload** | `useStockStream:497` 的 `msg as unknown as SignalMsg` | 目前是裸強制轉型,後端改欄名 = 前端靜默吃壞值 | 每則訊號多 ~5–20 µs(到達率 0.7/s,可忽略);但會多一份與後端 dataclass 平行維護的 schema,而本 repo 的契約紀律是**測試 + fixture parity**,不是 runtime schema | **不建議**(與 repo 既有契約機制重複;真要防漂,走 §6 步驟 10 的 `seq` 更對症) |
| **why-did-you-render** | 全 frontend | 找出「為什麼這次 render」 | React 19 相容性尚未穩定;`<Profiler>` 已能回答「多貴」,而「為什麼」本區塊已經查清(tick 驅動的 App 全樹) | **不建議** |

---

## 8. 未決問題(要 user 拍板 / 需要真環境才答得出來)

1. **rail 的 cap 要不要提高?** 200 是在 S7-03 memo 化**之前**訂的。memo 之後成本主要是
   element 數而不是推導,放寬到 686(全日)大約是 `365 µs → 1.2 ms`(推估)——
   memo 化之後這 1.2 ms 一天只付幾十次,可能反而划算。要不要放寬,取決於「早盤的訊號
   下午還需不需要翻得到」—— 這是交易習慣問題不是技術問題。
2. **FM-06 / FM-07 的真實延遲**:Chrome intensive throttling 的機制確定,但**門檻與豁免條件
   沒有在這台機器上驗過**。步驟 7 的量測做完之前,不要先動 `COALESCE_MS`。
3. **FM-03 的訊號 `seq` 該由誰配?** per-connection(與 tick 的 `seq` 語族不同)還是 per-hub
   全域?後者可跨連線對帳但會與「重啟後同 id 重發」的既有語意打架。
4. **回放補發的訊號要不要響?** S7-05 的「補回來就回放到 bus」會讓一則 5 分鐘前的訊號現在才嗶。
   對盤中交易這可能是噪音而不是資訊 —— 也許該補 rail 但只在 console 記一行。
5. **`live` 清空的時機**:步驟 2 用 `tradeDate` 變動當觸發。但 `tradeDate` 在 stage2 才前進,
   而午夜到 stage2 之間 baseline 是兩日聯集 —— 那段時間 `live` 該保留還是清?
   (本報告的建議是保留 + 靠排序鍵修正,但這是可以拍板成「清掉更簡單」的。)
6. **`/api/stock/signals/today` 的 `limit` 語意**:要「最新 n 則」還是「`since=HH:MM` 之後」?
   前者簡單,後者對「我要看 09:00 到現在」更有用。
7. **`SignalRail` 要不要在 `tab !== "stock"` 時整個不渲染?** 那是比 memo 更徹底的省法
   (省 100%),代價是切回個股 tab 時整個 rail 重掛一次(~0.37 ms + DOM 重建)。
   與專案「tab 用 hidden 不卸載」的既有慣例衝突,需要拍板。

---

## 附錄:benchmark 原始輸出

```
### bench-rail.mjs(純推導,含 hover title)
rows=686  after mergeSignals cap → 200
groups in view = 173 ; policy rows in view = 18
railRenderPass(200 列)                    160.597 µs/op
  └ groupSignals(200) 單獨                  3.176 µs/op
railRenderPass(50 列)                      35.027 µs/op
railRenderPass(20 列)                      14.477 µs/op
mergeSignals(686 baseline, 200 live)      32.198 µs/op
mergeSignals(200 prev, [1 新訊號])          10.518 µs/op

### bench-combined.mjs(推導 + React.createElement)
NODE_ENV=production
200 列 / 2874 elements   365.62 µs   (127 ns/el)   @150/s = 54.8 ms/s
120 列 / 1753 elements   201.33 µs   (115 ns/el)   @150/s = 30.2 ms/s
 50 列 /  761 elements    79.68 µs   (105 ns/el)   @150/s = 12.0 ms/s
 20 列 /  294 elements    30.84 µs   (105 ns/el)   @150/s =  4.6 ms/s
NODE_ENV=(dev)
200 列                  2769.69 µs   (964 ns/el)   @150/s = 415.5 ms/s
 50 列                   736.86 µs   (968 ns/el)   @150/s = 110.5 ms/s

### bench-split.mjs(hover title 占比)
全部(一次 render 的推導)                               166.76 µs
扣掉 segmentTitle/ruleTitle/policyTitle                103.36 µs
→ hover-only title 占比 38%(63.4 µs/render)
  ruleTitle 單獨                                       54.14 µs
  policyTitle 單獨                                     19.20 µs

### bench-alert.mjs(訊號抵達路徑)
emitSignal:new CustomEvent + dispatch(2 listeners)    0.115 µs
formatGroupToastText(單則組)                            0.502 µs
formatGroupToastText(政策 3 則組)                        0.945 µs
mergeSignals(200 prev, [新 1 則])                      10.544 µs
JSON.parse(1 則訊號 wire)                               3.824 µs

### bench-baseline.mjs(5 分鐘 baseline)
payload bytes 264200   (gzip 22004)
JSON.parse(264 KB)                                    614.3 µs
[...].reverse()                                         0.8 µs
mergeSignals(686, 200)                                 46.4 µs

### sim-rollover.mjs(跨日模擬)
昨日收盤 live 長度 = 200  時間區間 10:44:37 ~ 13:30:00
次日 09:05 rail 列數 = 200 ; 其中屬於【今天】的 = 0
```

### 真實資料統計(20260911.jsonl,686 列)

```
kinds: cdp_cross 295 / surge_pullback 159 / surge 59 / sweep_cluster 49 /
       policy 49 / crash 39 / vol_burst 30 / limit_lock 6
groups 614(size 1:550 / size 2:56 / size 3:8;max 3)
單秒最多 4 則;單分鐘最多 42 則(09:00)
notify=false 402 / 686 = 58.6%
平均列 407 B(政策列 1,074 B / 一般列 356 B)
第 200 新的 time = 10:44:37  → rail 只覆蓋 10:44:37 – 13:30:00
```
