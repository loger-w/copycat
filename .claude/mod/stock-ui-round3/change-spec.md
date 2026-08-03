# stock-ui-round3 — change-spec

現況表:`.claude/mod/stock-ui-round3/current-state.md`
分支:`mod/stock-ui-round3`
Round 1 review:`change-spec-review-round-1.json`(2×P0 / 8×P1 / 5×P2,**全數 accepted**,無誤報)

## 提問姿態分流判定

**判定 = 已成形改法 → grilling 姿態**(命中判準:user 給出 10 條逐項、可指認的具體改動,
每條都指名畫面元素與期望結果,非開放式目標)。已於 2026-07-29 停下拍板,4 個開放點全部
由 user 選定(見下「拍板紀錄」);其餘為實作級選擇,標 `[auto-default]`。

### 拍板紀錄(2026-07-29)

| 提問 | user 選擇 |
|---|---|
| 項 3 左緣刻度 | **現況正確,免改**(江波圖 `TICK_PCTS` 已是 ±2/4/6/8 + 漲跌停 + 平盤) |
| 項 1 右緣 % 刪除範圍 | **靜態 % 欄 + hover % 標兩處都刪** |
| 項 6 中間高度做法 | **新增量測 hook,圖表吃剩餘高度** |
| 項 9 慢法 | **兩種都修**(無資料 60s + 冷載入固定空等) |

---

## 1. 改完的成功條件(可驗收)

畫面類條件一律寫成「畫面可指認」表述,由 user 對照過目(Phase 8)。

| SC | 條件(畫面可指認 / 可量測) | 對應項 |
|---|---|---|
| SC-1 | 江波圖**主圖 svg 內、右側 60 個 viewBox 單位以內的 text 節點,不含 `%` 字元**:既無靜態刻度 % 欄,滑鼠移到圖上任意高度時右緣也不浮出 % 方塊(左緣價位標與底部時間標照舊出現)。**排除**:圖下方 figcaption 的「外盤比 55.2%」與頂部資訊列的漲跌 % 為刻意保留,不在此條範圍 `[amendment 2026-07-30: R12 — 原「看不到任何 % 字元」範圍過寬,會把刻意保留的兩處誤判成紅]` | 1 |
| SC-2 | 江波圖開啟 CDP 後,右緣五條水平線的文字是**價位數字 + `*`**(例 188 元標的顯示 `188.5*`),畫面上找不到 `AH` / `NH` / `CDP` / `NL` / `AL` 任一字串;五條線**顏色互不相同**:由上而下 = 紅 / 淺紅 / 琥珀 / 淺綠 / 綠 `[amendment 2026-07-30: R12 — 原示例 1188.0* 自相矛盾(≥1000 元帶 tick 5 元應為 1190 且 0 位小數),改用 100–500 元帶示例]` | 2 |
| SC-3 | SC-2 的價位數字全部是**該價位帶的合法檔位**:100–500 元標的只出現 `.0` / `.5` 結尾,≥1000 元標的只出現 5 的倍數整數(無小數點),10–50 元標的只出現 `.05` 的倍數 | 2 |
| SC-4 | 江波圖**看不到貼在最上緣與最下緣的紅、綠虛線**(左緣漲停 / 跌停價位文字仍在) | 4 |
| SC-5 | 個股頁左側自選清單**右邊有一條垂直分隔線**;右側交易面板(閃電/委託/部位)**左邊有一條垂直分隔線**,兩條線顏色與其他框線一致 | 5 |
| SC-6 | 1440×900、1920×1080、**1366×768** 三種視窗下,個股頁中間欄**不出現垂直捲軸**,且下半列五檔卡片與明細卡片的**底邊互相齊平且貼在中間欄底部**。量法:devtools `document.querySelector('main').scrollHeight === clientHeight` 回 true,並截圖對照 `[amendment 2026-07-30: R10 — 補矮視窗(1366×768)量點,原本只驗兩種高視窗,拆掉捲軸逃生口後矮視窗會靜默裁切]` | 6 |
| SC-6b | **明細連點 3 次「載入更多」(90 筆)後**,`<main>` 仍無捲軸(`scrollHeight === clientHeight`),且把 `[data-testid=tick-tape]` 捲到底(`el.scrollTop = el.scrollHeight`)時「載入更多」鈕**完整可見不被裁切**。量法:devtools 執行上述兩式 + 截圖 `[amendment 2026-07-30 round2: R21 — 原措辭「鈕仍可見可點」不可機械判定且與現況矛盾(30 筆 × 24px = 720px 早就超過列高,鈕本來就要捲動才看得到,非本輪造成)]` | 6 |
| SC-7 | 江波圖底部的時間文字(09:00 / 10:00 / 11:00 / 12:00 / 13:00)與 hover 浮出的時間方塊文字**呈黃色** | 7 |
| SC-8 | 江波圖下方內外盤能量副圖**左緣出現量刻度數字**(頂端 = 該日單邊最大張數、中線 = 其半),頂端數字**不被最高的那根 bar 蓋住**,且中線位置有一條淡橫線 `[amendment 2026-07-30: R15(1) — 補「不被蓋住」,原設計 maxSide 那根 bar 高度等於副圖全高必然重疊]` | 8 |
| SC-9 | 分 K / 日 K 載入耗時(量法:`curl -o /dev/null -w "%{time_total}"`)—— (a) TC4 查無資料標的(9999)`?tf=1&days=30` **首次 ≤ 25s**(現況 60.1s);(b) 同標的 15 秒內**再次請求 ≤ 0.1s**(現況 60.1s);(c) 今日有資料的冷載入標的 `?tf=1&days=30` **≤ 1.6s**(現況 2.13s);(d) **無資料標的 `?tf=D` 首次 ≤ 25s** `[amendment 2026-07-30: R7 — fetch_bars_range 實為三處 _collect_history(:442/:444/:452),tf=D 無資料路徑原本沒被任何 SC 覆蓋]` | 9 |
| SC-10 | K 線圖(日 K 與分 K)左緣價位刻度**全部是合法檔位**:1000 元以上標的不出現 `1003` 或帶小數點的數字、100–500 元標的不出現 `102.4`;刻度數字不重複;**刻度數 ≥ 1**(不得整組消失)`[amendment 2026-07-30: R11]` | 10 |
| SC-11 | 項 3 = 確認項:江波圖左緣仍為 11 條(漲停 / +8 / +6 / +4 / +2 / 平盤 / −2 / −4 / −6 / −8 / 跌停),**本輪不得改動** | 3 |

---

## 2. 不能破壞的既有行為白名單

**這比新行為更重要。** Phase 5 自評與 Phase 7 都要逐條對照。

| W | 行為 | 出處 |
|---|---|---|
| W-1 | 江波圖 Y 域**恰為** `[lower, upper]`,上下呼吸空間由 `PAD_Y` 像素留邊出,不是價格域放寬 | `stock-intraday-svg.ts:104-107` |
| W-2 | `toY` / `priceAtY` 共用同一組 `PAD_Y` / `X_LABEL_H` 且互為逆函數;退化域(`ySpan<=0`)兩者都特判成常數 | `stock-intraday-svg.ts:117-129` |
| W-3 | 非 ±10% 漲跌幅商品:公式算出的中間刻度落在域外時**跳過**,不得讓 `toY` 變負 / 刻度次序反轉;相同 `priceMilli` 去重 | `stock-intraday-svg.ts:159-173` |
| W-4 | K 線 hover 存 **viewBox 座標**(非 bar index),縮放/平移後十字線不指錯 | `CandleChart.tsx:284` |
| W-5 | `ChartStatic` / `EnergySub` / `CandleChart.ChartStatic` 的 **memo 邊界**:hover 每次 mousemove 不得重建蠟燭 / 量 bar / 線層 | `StockIntradayChart.tsx:58,223`、`CandleChart.tsx:84` |
| W-6 | 左緣 hover 價位標 snap 到**合法 tick**(顯示的價位要可下單) | `StockIntradayChart.tsx:332`、`CandleChart.tsx:396` |
| W-7 | `minuteOf` **不 snap 最近**:無成交分鐘不畫垂直線與資料點,但水平線 / 左價標照畫(分解退化) | `stock-intraday-svg.ts:181-185`、`StockIntradayChart.tsx:402-419` |
| W-8 | X 軸靜態時間標籤與 hover 時間標**重疊時整個不畫**(消除半截殘字) | `StockIntradayChart.tsx:209`、`CandleChart.tsx:219` |
| W-9 | 圖上拖曳不觸發選字(`select-none`) | `StockIntradayChart.tsx:356`、`CandleChart.tsx:415` |
| W-10 | 五檔缺檔補「—」不塌陷、**不送單**(只發 `stock-price-click`) | `OrderBook.tsx:59-68,36-41` |
| W-11 | 明細「載入更多」鈕在**任何視窗高度下**可見可點,下半列不得被壓成 0 高整塊消失 | `StockPage.tsx:82-89`、`TickTape.tsx:57-65` |
| W-11b | `TickTape` 根節點的 `h-full` + `overflow-y-auto` **需要父層有確定高度**才會內捲;父層退化成內容高時明細會無限撐長 `[amendment 2026-07-30: R1 — 新增,這是 W-11 成立的隱性前置條件,原 spec 未寫]` | `TickTape.tsx:28-31` |
| W-12 | 切換江波圖 ↔ K 線時**圖表區塊高度不跳**(兩個 figure 的框外 chrome 逐項對稱) | `CandleChart.tsx:25-28` |
| W-13 | RightRail 閃電 tab 是**條件 render 不是 `hidden`**:離開畫面即解除武裝 | `RightRail.tsx:15-21,207` |
| W-14 | `/api/stock/bars` response shape `{code, tf, bars}` **完全不變**;`tf=D` 的 query key 不含 `days` `[amendment 2026-07-30 round2:R-12 撤回,由「可加欄位」收回為「不變」]` | `app.py:412`、`useStockBars.ts:70` |
| W-15 | don't-cache-empty 的**斷線可恢復**性質:TC4 失敗與真無資料上游不可分,空結果不得被**永久**釘住 | `bars.py:101,124,158-160` |
| W-16 | 歷史段負向快取**只寫到有證據掃過的最後一天**(TC4 分頁截斷不得把後面日子誤釘成空) | `bars.py:65-82` |
| W-17 | `_collect_history` 的 TC4 通訊失敗仍收斂為 `ConnectionError`(由 `_req` 負責),engine 層降級空 | `stock_source.py:379-397`、`stock_engine.py:192-201` |
| W-18 | 全站捲軸配色規則(選擇器必須是 `*`,不是 `html`) | `index.css:41-44` |

---

## 3. Backward compat / migration

- 前端:顯示層 + 兩個新純模組(hook / 常數)。**無 localStorage schema 變動**。
- 後端:`/api/stock/bars` 回應**一字不動**(`{code, tf, bars}`)`[amendment 2026-07-30 round2:
  R-12 撤回後不再加欄位]`。
- 空結果由「永不快取」改為「**短 TTL 負向快取**(15s)」—— 仍可恢復(W-15 保留)。
- **無 migration 需求**。

## 4. Out of scope

- 個股期 / TXO / 期貨 / 指數頁的版面(項 5 的右欄 border 會連帶出現在所有 tab,這是必然)。
- MA5 / MA20 疊線的 label 文字(user 只點名 CDP 的 AH/NH 用語)。
- 自選側欄重做、閃電梯部位/損益、K 線捷徑鍵等 `docs/next-time.md` 既有待辦。
- K 線 endpoint 的 inflight dedup(next-time 既有項)。
- 國定假日交易日曆(next-time 既有項)。

---

# Phase 3 — Diff 級 spec

三類標記:🔴 行為改動(既有測試該紅)/ 🟢 新功能(加新測試)/ 🔵 純重構(測試不該變)

## 🟢 R-1 `frontend/src/lib/stock-tick.ts` — 新增 tick 對齊與格式化純函數

`[amendment 2026-07-30: R14 — 由 🔵 改標 🟢:本項帶新測試 T-1,不符專案「🔵 = 測試不該變」定義]`

新增兩支(既有 `tickOf` / `snapDown` / `snapUp` / `buildLadder` 完全不動):

```ts
/** snap 到**最近**合法 tick(既有 snapDown/snapUp 是方向性的)。 */
export function snapNearest(priceMilli: number): number

/** 依該價位帶 tick 級距決定小數位(對齊 treading-king formatTickPrice)。 */
export function fmtTickPrice(priceMilli: number): string
```

級距對照(毫元):`>=1_000_000` tick 5000 → 0 位;`>=500_000` tick 1000 → 0 位;
`>=100_000` tick 500 → 1 位;`>=50_000` tick 100 → 1 位;`>=10_000` tick 50 → 2 位;
`<10_000` tick 10 → 2 位。`fmtTickPrice` 先 `snapNearest` 再格式化。

## 🟢 R-2 `frontend/src/hooks/useContainerSize.ts` — 新建

`[amendment 2026-07-30: R14 — 由 🔵 改標 🟢(帶新測試 T-4);R3 — 補「量測對象高度必須由外層 flex 指派」前置條件與 1px 去抖]`

```ts
export interface Size { width: number; height: number }
export function useContainerSize<T extends HTMLElement>(): [React.RefCallback<T>, Size]
```

- `ResizeObserver` 觀測;**feature-detect**:`typeof ResizeObserver === "undefined"`(jsdom)
  → 直接回 `{width:0,height:0}` 不掛 observer。
- ref 用 **callback ref**(非 `useRef`):conventions 記載 hook null-ref 陷阱。
- **去抖**:量到的值與前次差 ≤1px 時不 `setState`(避免亞像素回饋抖動與 ResizeObserver 迴圈)。
- **呼叫端契約(必寫進 docstring)**:被量測元素的高度**必須由外層 flex 指派**
  (`flex-1 min-h-0`),**不得由內容決定** —— 否則量到的是「內容現在多高」而非「還剩多少」,
  SC-6 會靜默失效並形成回饋迴圈。

## 🟢 R-2b `frontend/src/lib/chart-frame.ts` — 新建(兩張圖共用的框外 chrome 常數)

`[amendment 2026-07-30: R4 — 新增;原 spec 讓兩個元件各自扣 chrome,(a) 漏扣 mb-1 4px、
(b) 未扣 figure 的 padding/border 導致縮放比高估 ≈2.4%,且 W-12 只靠「兩邊記得扣一樣的項」]`

```ts
/** figure 框外 chrome(px)。兩張圖逐項對稱是 W-12 成立的唯一依據 → 收在同一個常數。 */
export const CHART_FRAME = {
  padX: 32,        // p-4 左右
  padY: 32,        // p-4 上下
  border: 2,       // border 上下 / 左右各 1
  topRow: 22 + 4,  // h-[1.375rem] + mb-1
  bottomRow: 16 + 4, // h-4 + mt-1
} as const;

/** 量到的 wrapper 尺寸 → svg 可用的「渲染像素」與 viewBox 換算。 */
export function svgBox(wrapper: Size, viewBoxWidth: number, minPx = 180): {
  renderPx: number;    // svg 該渲染多高(px)
  viewBoxHeight: number;
  usable: boolean;     // 量測無效(0)時 false → 呼叫端退回固定常數
}
```

換算:`svgWidthPx = wrapper.width − padX − border`;`s = svgWidthPx / viewBoxWidth`;
`renderPx = max(minPx, floor(wrapper.height − padY − border − topRow − bottomRow) − 2)`
(−2 = 安全邊,讓誤差方向恆為「略短」而非溢出);`viewBoxHeight = round(renderPx / s)`。

## 🔴 R-3 `frontend/src/lib/stock-intraday-svg.ts`

| 動作 | 內容 |
|---|---|
| 🔴 移除 | `YTick.pct` 欄位與 `pctOf` 計算(SC-1)。`yTicks` 只留 `{y, priceMilli}` |
| 🔴 改 | `OverlayLine`:`label: string` → `kind: "cdp" \| "ma"` + **`level: "ah"\|"nh"\|"cdp"\|"nl"\|"al"\|"ma5"\|"ma20"`**;`label` 欄位刪除 |
| 🟢 加 | `IntradayGeometry.maxSide: number`(內外盤副圖歸一分母,現為區域變數 `:147`)→ 供 SC-8 |
| 🔴 改 | `energyBars` 的 `outerH`/`innerH` 分母由 `size.height` 改為 `size.height − SUB_TOP_PAD`(新常數 10),頂端量刻度文字才不會被最高 bar 蓋住 `[amendment 2026-07-30: R15(1)]` |
| — 不動 | `TICK_PCTS`(SC-11)、Y 域(W-1)、`toY`/`priceAtY`(W-2)、域外跳過與去重(W-3)、`minuteOf`(W-7)、`upperY`/`lowerY` 欄位(仍回傳,只是元件不再畫) |

`upperY` / `lowerY` **保留欄位**:刪欄位屬順手清理(鐵則 B),本輪只停止繪製。

## 🔴 R-4 `frontend/src/components/stock/StockIntradayChart.tsx`

| 行號(現) | 動作 | 內容 |
|---|---|---|
| `:92-97` | 🔴 刪 | 漲跌停兩條 dashed line(SC-4) |
| `:122-132` | 🔴 刪 | 右緣靜態 `%` text(SC-1) |
| `:37-40` | 🔴 刪 | `fmtPct`(刪 `:471` 後無 caller) |
| `:153-170` | 🔴 改 | 疊線:`key` 改 `l.level`;文字改 `LEVEL_TEXT` 查表;CDP 五條依 `l.level` 上色 |
| `:161` | 🔴 改 | **判色條件 `l.label === "MA20"` → `l.level === "ma20"`** `[amendment 2026-07-30: R9 — 原 diff 表漏列這處字串耦合,現況表有標]` |
| `:211` | 🔴 改 | X 軸時間文字 `fill-ink-dim` → `fill-time`(SC-7) |
| `:490` | 🔴 改 | hover 時間標文字 `fill-ink` → `fill-time`(SC-7) |
| `:449-474` | 🔴 刪 | hover 右緣 `pct-tag` + `PCT_TAG` 常數 + `hoverPct`(SC-1) |
| `:223-240` | 🔴 改 | `EnergySub` 加量刻度:左緣兩個 text(`maxSide`、`maxSide/2`)+ 中線淡橫線;`maxSide` 與 `dims` 由 props 傳入(SC-8) |
| `:21-22` | 🔴 改 | `MAIN` / `SUB` 由模組常數改為 props 驅動;見 R-6 |

**`LEVEL_TEXT` 映射** `[amendment 2026-07-30: R9 — 原 spec 刪了 label 卻沒定義 MA 文字來源]`:

```ts
const LEVEL_TEXT: Record<OverlayLine["level"], (p: number) => string> = {
  ah: (p) => `${fmtTickPrice(p)}*`,  nh: (p) => `${fmtTickPrice(p)}*`,
  cdp:(p) => `${fmtTickPrice(p)}*`,  nl: (p) => `${fmtTickPrice(p)}*`,
  al: (p) => `${fmtTickPrice(p)}*`,  ma5: () => "MA5", ma20: () => "MA20",
};
```

**CDP 配色** `[auto-default: 上紅下綠、中軸琥珀 | reason: 台股紅漲綠跌 —— 壓力位(上方)紅、
支撐位(下方)綠,中軸取既有 profit 琥珀金不與紅綠系混淆;user 已在拍板 preview 看過]`:

| level | stroke / fill | 色 |
|---|---|---|
| `ah` | `stroke-bull` / `fill-bull` | #f0524f 紅 |
| `nh` | `stroke-bull/55` / `fill-bull/70` | 淺紅 |
| `cdp` | `stroke-profit` / `fill-profit` | #d9a441 琥珀 |
| `nl` | `stroke-bear/55` / `fill-bear/70` | 淺綠 |
| `al` | `stroke-bear` / `fill-bear` | #3ba272 綠 |

## 🔴 R-5 `frontend/src/index.css` — 新增時間色 token

```css
--color-time: #f0b429;   /* 江波圖時間軸黃(語意獨立於 --color-ma5,同色值) */
```

## 🔴 R-6 高度自適應(SC-6 / SC-6b)—— 四檔連動

`[amendment 2026-07-30: R1(P0) / R2(P0) / R3 / R4 / R8 / R10 — 本節整段重寫]`

### R-6a `StockPage.tsx`
- `<main>`:**維持 `overflow-y-auto`**(不改 `overflow-hidden`),補 `min-h-0`。
  理由(R10):捲軸是 W-11 在極矮視窗下的逃生口;正常尺寸下因為圖表吃剩餘高度,
  捲軸本來就不會出現(SC-6 仍成立),把它拆掉只會讓超界時變成**靜默裁切**。
- 圖表容器:`<StockChart>` 外包 `<div className="flex min-h-0 flex-1 flex-col">`。
- 下半列:`min-h-56 flex-1` → **`h-56 shrink-0`**(224px 固定,等於現行地板)。
  理由(R1/P0):`TickTape` 的 `h-full` 需要父層**確定高度**(W-11b);
  原提案 `shrink-0 + min-h-56` 讓該列變成「內容自然高」→ 30 筆明細撐成 ~770px、
  每點一次載入更多再 +720px → 圖表被擠到 0、量測回 0、退回固定常數 → 溢出。
  固定 `h-56` 兩邊都保住:高度確定(明細內捲、載入更多恆可見)、不吃剩餘空間(圖表吃)。
- 兩個子 wrapper:`min-w-0 flex-[3]` / `min-w-0 flex-[2]` 各補 **`min-h-0`**;
  五檔的 `self-start` **移除**(R8)。
- `OrderBook.tsx:120` 的 `<section>` 加 **`h-full`**(R8):不加的話卡片仍是自然高,
  SC-6 的「兩塊底邊齊平」達不到。代價 = 卡片底部約 24px 留白 —— 這是對
  `StockPage.tsx:88-89` 既有 `self-start` 取捨的**刻意推翻**,因 user 明確要求貼底。
- **空態高度**(`[amendment 2026-07-30 round2: R22]`):`TickTape.tsx:19` 的「尚無成交」空態
  盒是固定 `h-40`(160px),在 224px 固定列裡會短 64px → SC-6 的「兩塊底邊齊平」在盤前 /
  剛切股時不成立。**改 `h-full`**。
- **已知取捨**:大螢幕上明細列數不再隨視窗變高(固定 224px ≈ 7 列),換得圖表吃滿剩餘。

### R-6b `StockChart.tsx`
- 根 `div` 由 `shrink-0` → `flex min-h-0 flex-1 flex-col`。
- **在模式按鈕列下方新增一層恆存 wrapper** `<div className="flex min-h-0 flex-1 flex-col">`,
  `useContainerSize` 的 ref 掛在**這一層**(三態 loading / error / data 共用)。
  R3 要求:此層高度由外層 flex 指派,不得由內容決定。
- 用 `svgBox()`(R-2b)換算後,把 **`dims: {width, height}` 物件以 `useMemo` 產生穩定 identity**
  再往下傳。`usable === false`(量測 0 / jsdom)→ 傳 `null`,子元件沿用現行固定常數
  → **既有行為不變,既有測試不該紅**。
- **三態 fallback 盒也要吃 `renderPx`**(`[amendment 2026-07-30 round2: R23]`):
  `StockChart.tsx:73`(載入中)/ `:80`(載入失敗)與 `CandleChart.tsx:433`(無 K 線資料)
  目前都是固定 `h-64`(256px)。不改的話:視窗高時圖表區與下半列之間留死白(切模式的
  1–2 秒內 SC-6 不成立)、視窗矮時反而溢出長出捲軸。改法:三個盒改 `flex-1 min-h-0`
  (吃 wrapper 剩餘高),`usable === false` 時才退回 `h-64`。
  `StockIntradayChart.tsx:285`「尚無成交」盒同理。

### R-6c 兩個圖表元件的 props 化(R2 / P0)
原 spec 只寫「MAIN/SUB/DIMS 改為依量測高度計算」,漏了兩件必要連動:

1. **memo 子元件必須經 props 拿尺寸**,不可繼續閉包引用模組常數:
   `StockIntradayChart` 的 `ChartStatic`(`:80,87,93,98,105,116,125,157`)、
   `XAxisLabels`(`:211`)、`EnergySub`(`:228,231`)、模組級 `toX`(`:52`)/`BAR_W`(`:55`);
   `CandleChart` 的 `ChartStatic`(`:103`)、`XAxisLabels`(`:224`)。
   `toX` / `BAR_W` 改為吃 `width` 參數的純函數 —— **此步值不變、測試不該變 = 🔵,單獨
   一個 commit**(`[amendment 2026-07-30 round2: R24 — 原本與 🔴 混在 commit 5,違反鐵則 B]`)。
   **傳純量 `width` / `height` 而非物件**給 memo 子元件,避免 identity 打穿 memo(W-5)。
2. **幾何 useMemo deps 必須含尺寸**:
   `StockIntradayChart.tsx:253-261` 的 `g` / `subGeo` deps `[accum.minutes, accum.meta]`
   → 加 `mainH` / `subH`;`CandleChart.tsx:297-315` deps `[bars, viewport, showBb]`
   → 加 `dimsH`。**repo 的 eslint 沒裝 react-hooks plugin,exhaustive-deps 抓不到這條**,
   → 靠 **T-10b 的元件層 `dims` prop 對照測試**把關(`[amendment 2026-07-30 round2: R20 —
   原本寫「靠純函數層測試把關」做不到:lib 層測試在元件 deps 漏寫時照樣全綠,等於 round 1
   的 P0 沒真正關閉]`)。dims 已是 prop → 測試可直接傳兩種 height render 兩次,
   不必依賴 jsdom 的 ResizeObserver。

### R-6d 尺寸分配
- 江波圖:`renderPx` 依現行比例 **260 : 70** 分給 MAIN / SUB(比例維持 → 視覺不變形)。
- K 線:`renderPx` 全給 `DIMS.height`。
- 兩者都用同一份 `CHART_FRAME` 扣 chrome → **W-12 由建構保證**,不再靠「兩邊記得扣一樣」。

## 🔴 R-7 `frontend/src/lib/candle.ts` — y 刻度 snap 合法檔位(SC-10)

`:218-226` 改:

```ts
const seen = new Set<number>();
for (let i = 0; i < Y_TICKS; i += 1) {
  const raw = Math.round(lo + (span * i) / (Y_TICKS - 1));
  const p = snapNearest(raw);
  if (p < lo || p > hi) continue;   // snap 後溢出域 → 跳過(對齊江波圖 W-3 慣例)
  if (seen.has(p)) continue;        // 低價股 tick 粗時相鄰刻度會 snap 到同價
  seen.add(p);
  yTicks.push({ y: toY(p), priceMilli: p });
}
// 保底:域寬 < 一個 tick 且區間內無合法檔位時全部被跳過 → 刻度整組消失(靜默失效)
if (yTicks.length === 0) {
  const p = snapNearest(Math.round((lo + hi) / 2));
  yTicks.push({ y: Math.min(Math.max(toY(p), PAD_Y), PAD_Y + usable), priceMilli: p });
}
```
`[amendment 2026-07-30: R11 — 補保底;lo/hi 會被 extraSeries(MA/布林,Math.floor 任意整數)
撐成非合法檔位,端點 snap 後落域外是常態,極窄域可能 5 根全跳過]`

`[amendment 2026-07-30 phase5: B1(P0) — **本節原本自己就違反 SC-10**:保底寫
`priceMilli: mid` 未 snap。實算:域 [1000100, 1003000] 毫元、tick 5000 →
mid = 1001550,1001550 % 5000 = 1550 → 畫面出現 1001.55 元。改 `snapNearest(mid)`;
窄域裡唯一的合法檔位必然落在域外(域本身裝不下一個 tick),所以 y 要夾回繪圖區,
否則刻度線與文字會畫進下方量區。原 T-3 只斷言「刻度數 ≥1」抓不到,已補合法性斷言。]`

`span <= 0` 分支:值改 `snapNearest(hi)`,仍單一刻度。
`candle.ts` import `lib/stock-tick.ts` —— 兩者皆零 React 依賴純模組,`stock-tick.ts` 不 import
`candle.ts`,**無循環相依**(已查證)。

## 🔴 R-8 `frontend/src/components/stock/CandleChart.tsx`

- `:111` 刻度文字 `fmt(t.priceMilli)` → `fmtTickPrice(t.priceMilli)`(SC-10)。
- `:28` `DIMS` 改 props 驅動(R-6c),`width` 維持 1400。
- 其餘(hover 座標 W-4、memo 邊界 W-5、拖曳、`XAxisLabels` W-8)不動。

## 🔴 R-9 `WatchlistSidebar.tsx` / `rail/RightRail.tsx`(SC-5)

- `WatchlistSidebar.tsx:163`:`aside` 加 `border-r border-line pr-3`。
- `RightRail.tsx:189`:`aside` 加 `border-l border-line pl-3`。

## 🔴 R-10 `copycat/live/stock_source.py` — 等待策略(SC-9c/9d)

`_collect_history` 簽名加 `deadline_secs: float | None = None`:

```python
def _collect_history(self, sym, data_type, start, end, deadline_secs=None) -> list[dict]:
    self._sub_history(sym, start, end, data_type)
    budget = deadline_secs if deadline_secs is not None else max(self._poll_wait * 30, 1.0)
    deadline = time.monotonic() + budget
    wait = min(0.15, self._poll_wait)          # 退避起點
    while True:
        first = self._get_history(sym, start, end, "0", data_type)
        if first.get("HisData"):
            break
        # poll_wait=0(測試組態)= 不重試:原本會在 budget 內 busy loop 全速打 fake API,
        # budget 由 1s 拉到 10s 後那是 10 倍空轉(review R6)
        if wait <= 0 or time.monotonic() >= deadline:
            logger.info("history %s(%s): %.1fs 內未備妥,回空", sym, data_type, budget)
            return []
        time.sleep(wait)
        wait = min(wait * 2, self._poll_wait)  # 退避上限 = 原 poll_wait
    ...
```

- `fetch_bars_range` **三處**呼叫全部傳 `deadline_secs=_BARS_POLL_DEADLINE`(新常數 **10.0**):
  `:442`(tf=1)、`:444`(DK)、`:452`(DK 空 → 1K fallback)。
  `[amendment 2026-07-30: R7 — 原寫「兩處」是事實錯誤;漏掉 :452 會讓 tf=D 無資料路徑
  變成 10+30=40s,只省 1/3]`
- `fetch_day_minutes` / `fetch_daily_bars` **不傳** → 維持 30s 舊值(W-17 不受影響)。

`[auto-default: deadline 10s | reason: 實測有資料標的首頁 <1s 備妥,10s 給 10× 餘裕;
誤判為空時配合 R-11 的 15s TTL 可自動重試,不是永久釘死。殘餘風險見 §7]`

## 🔴 R-11 `copycat/server/bars.py` — 短 TTL 負向快取(SC-9a/9b)

```python
EMPTY_TTL_SECS = 15.0     # < 前端 60s 輪詢;斷線恢復最多等 15s(W-15 保留)

class BarsCache:
    self._empty: dict[tuple[str, str, int], float] = {}   # (code, tf, days) -> 寫入時刻
    def empty_fresh(self, code, tf, days) -> bool: ...
    def empty_mark(self, code, tf, days) -> None: ...
    def empty_clear(self, code, tf, days) -> None: ...
```
`[amendment 2026-07-30: R15(2) — key 加 days;否則 days=1 的空結果會把 days=30 一併釘住]`
(`tf="D"` 的 `days` 一律傳 0。)

`build_minute` / `build_daily` 開頭 `if cache.empty_fresh(...): return []`;
結尾空 → `empty_mark`,非空 → `empty_clear`。`prune` **只清已過期的** `_empty`
`[amendment 2026-07-30 phase5:實作時踩到 —— prune 在每次 build_* 開頭都會跑,
無條件 clear 等於負向快取從未生效,兩個測試抓出來]`。

**另加當日段的短 TTL**(`today_put` 空結果也存、`today_get` 對空 entry 用
`min(ttl, EMPTY_TTL_SECS)`)`[amendment 2026-07-30 phase5: B2(P1) — 上面那個
`empty_mark` 看的是「歷史 + 當日**合併後**」的 out。歷史有資料但今日零成交的冷門股
out 恆非空 → 永不 mark;而當日段自己的 don't-cache-empty 也不存空 → 每次請求都重付
一次 TC4 首頁等待。原 spec 的測試清單只有「兩段都空」的全空模型(9999),
完全沒涵蓋「歷史非空 + 今日空」這個組合]`。

**W-15 保留論證**:15s 後標記失效即自動重試,不是永久釘死;
**W-16 不受影響**:`put_hist_range` 的 per-day 負向快取一行不動。

## ~~R-12 逾時態誠實化~~ —— **本輪撤回**

`[amendment 2026-07-30 round2: R16(P0)/R17/R18/R19 — 整項撤回]`

round 1 的 R13(P2)指出「10s deadline 誤判 + 15s 負向快取」會讓畫面用肯定語氣說
「無 K 線資料」。當時的處置是加一個 `stale` 欄位,但 round 2 查出該欄位**無法落地**:
`_collect_history`(逾時 `return []`)→ `fetch_bars_range` → `stock_engine.bars_range`
(連 `ConnectionError` 都吞成 `[]`)→ `BarsFetcher` 型別,整條鏈都是 `list[Bar]`,
「逾時 / 真無資料 / TC4 斷線」在 `build_minute` 眼中同形;`_empty` 也只存時刻無從還原。
要做就得動整條 Protocol 型別 + `tests/server/test_bars.py` 20 個 call site +
`test_stock_routes.py` 的精確相等契約 + `StockChart.tsx` 的 data shape。

**撤回理由**:(a) 這不在 user 的 10 項內,是本輪自行追加的 scope(鐵則 B);
(b) 「慢的標的顯示無 K 線資料」是**既有行為**,現況等滿 60s 後顯示同一句話 ——
本輪只讓它更快抵達同一結論,並未讓訊息變差;(c) 撤回後 `/api/stock/bars` 回應
**完全不變**,W-14 由「加欄位相容」升級成「一字不動」。

**處置**:記入 §7 Known Risks 1 與 `docs/next-time.md`,不在本輪做。

---

## 5. 既有測試逐一標記

`[amendment 2026-07-30: R5 / R6 / R9 — 修正檔案路徑(tests/server/、tests/live/)、
把三個被錯標成「不該紅」的測試移進「該紅」、補 tests/live/test_stock_bars.py]`

### 該紅(🔴,依 spec 改 assertion)

| 檔:案名 | 為何該紅 | 正確修法 |
|---|---|---|
| `lib/stock-intraday-svg.test.ts` — `YTick.pct` 相關 | R-3 移除欄位 | 刪該斷言 |
| `lib/stock-intraday-svg.test.ts:212` `.map(l => l.label)` | R-3 改欄位 | 取值改 `l.level`,**語意斷言不得改** |
| `lib/stock-intraday-svg.test.ts:241` 域外跳過(ma5 溢出) | 同上(TS 編譯即失敗) | 同上 |
| `components/stock/StockIntradayChart.test.tsx` — 右緣 % / `pct-tag` / `AH`,`NH` label | R-4 | 依 SC-1/SC-2 改 |
| `lib/candle.test.ts` — yTicks 長度 / 等分值 | R-7 snap + 去重 | 改斷言「全為合法檔位」 |
| `components/stock/CandleChart.test.tsx` — y 刻度文字字面 | R-8 | 改 `fmtTickPrice` 預期值 |
| `components/stock/StockPage.test.tsx:129-131` — 下半列 `flex-1` / `self-start` | R-6a | 改 `h-56 shrink-0`,並保留「不塌陷」語意斷言 |
| `tests/server/test_bars.py:124` `test_empty_history_not_negatively_cached` | R-11 加 `empty_fresh` 早退 | **注入 clock 推進 >15s 後再斷言可恢復**(不是刪斷言) |
| `tests/server/test_bars.py:140` `test_today_empty_not_cached` | 同上 | 同上 |

### **不該紅**(打到就是動到無關東西 → 回 Phase 3)

- `lib/stock-intraday-svg.test.ts` 的 Y 域 / `toY`↔`priceAtY` 互逆 / 域外跳過**語意** / 去重(W-1~W-3)
- `lib/candle.test.ts` 的 `priceAtY` / `extraSeries` / 密集韌性(W-4)
- `components/stock/OrderBook.test.tsx` 全部(W-10;R-6a 只加 `h-full`,不動內容)
- `components/stock/TickTape.test.tsx` 全部(W-11)
- `components/rail/RightRail.test.tsx` 全部(W-13)
- `hooks/useStockBars.test.tsx` **全部**(W-14;R-12 撤回後回應 shape 一字不動)
- `components/stock/StockChart.test.tsx` **全部**(同上;R-6b 只動 wrapper class 不動 data shape)
- `tests/server/test_stock_routes.py` **全部**(精確相等的回應契約鎖,shape 不變)
- `tests/server/test_bars.py:149` `test_truncated_fetch_does_not_pin_later_days_empty`
  與 `:166` `test_existing_bars_not_overwritten_by_empty`(首次回**非空**,不觸發
  `empty_mark`)(W-16)
- `tests/live/test_stock_source.py` 的 `ConnectionError` 收斂(W-17)
- `tests/live/test_stock_bars.py` **全部**(`poll_wait_secs=0.0`,R-10 的
  「`wait<=0` → 單次探測即回」讓這些測試**更快**而非變慢;斷言值不變)

### 新測試清單(🟢)

| T | 檔 | 內容 |
|---|---|---|
| T-1 | `lib/stock-tick.test.ts` | `snapNearest` 跨級距取最近而非向下;`fmtTickPrice` 小數位分級 |
| T-2 | `lib/stock-intraday-svg.test.ts` | `overlayLines` 回 `level`、CDP 五級齊全且由上而下;`maxSide` 出口值;`energyBars` 高度分母已扣 `SUB_TOP_PAD` |
| T-3 | `lib/candle.test.ts` | yTicks 全部 `snapNearest(p)===p`;1000 元帶只出 5 倍數;去重;**極窄域保底 ≥1 根** |
| T-4 | `hooks/useContainerSize.test.tsx` | 無 `ResizeObserver`(jsdom)時回 `{0,0}` 且不拋 |
| T-5 | `components/stock/StockIntradayChart.test.tsx` | 右緣(x > width−60)無 `%` text、無 `pct-tag`;無漲跌停虛線;時間文字帶 `fill-time`;CDP label 為價位+`*` 且五色不同 |
| T-6 | `components/stock/StockPage.test.tsx` | `<main>` 保留 `overflow-y-auto`;下半列 `h-56 shrink-0`;「載入更多」可見(W-11 regression lock) |
| T-7 | `WatchlistSidebar.test.tsx` / `RightRail.test.tsx` | aside 帶 `border-r` / `border-l` |
| T-8 | `tests/server/test_bars.py` | 空結果 15s 內第二次呼叫**不再 fetch**(計次);注入 clock 過 15s 後重新 fetch(W-15) |
| T-9 | `tests/live/test_stock_bars.py` | `_collect_history` 帶 `deadline_secs` 時在預算內回空;`poll_wait=0` 時只探測一次(不 busy loop) |
| T-10a | `lib/chart-frame.test.ts` | `svgBox` 換算:padding/border 扣除、`minPx` 夾制、量測 0 → `usable:false`、`renderPx` 恆 ≤ 可用高(安全邊) |
| T-10b | `components/stock/StockIntradayChart.test.tsx` + `CandleChart.test.tsx` | **元件層 dims regression**(`[amendment 2026-07-30 round2: R20]`):同一份資料、只改 `dims` prop(height 260 vs 400)render 兩次,斷言 (a) svg `viewBox` 高度改變 **且** (b) 某條可指認的 y(價線第一點 / 第一條 yTick 的 `y` 屬性)也改變。缺 (b) 就抓不到 `useMemo` deps 漏寫 |

---

## 6. Commit 切分(🔵 → 🔴 → 🟢)

`[amendment 2026-07-30: R14 — 移除「最後一個純測試 commit」,測試併入各自 commit]`

| # | 類 | 內容 |
|---|---|---|
| 1 | 🟢 | R-1 + R-2 + R-2b 三個純新增模組 **+ T-1 / T-4 / T-10a** |
| 2 | 🔴 | R-3/R-4/R-5 江波圖 + T-2 / T-5 |
| 3 | 🔴 | R-7/R-8 K 線刻度合法檔位 + T-3 |
| 4 | 🔴 | R-9 兩側 border + T-7 |
| 5 | 🔵 | **R-6c 第 1 點的參數化**:`toX` / `BAR_W` / memo 子元件改吃 `width`/`height` props,值全部維持現行常數 → **測試一行不動、全綠**(`[amendment 2026-07-30 round2: R24]`) |
| 6 | 🔴 | R-6(a/b/d)高度自適應 + 幾何 `useMemo` deps 補尺寸 + T-6 / T-10b |
| 7 | 🔴 | R-10/R-11 後端等待策略 + 短 TTL 負向快取 + T-8 / T-9 |

TDD 節奏:每個 commit 內先讓測試紅 → 再改實作轉綠。

---

## 7. Known Risks

`[amendment 2026-07-30: R13 — 原為空]`

1. **「有資料但 TC4 慢」被誤判為空,且畫面用肯定語氣說「無 K 線資料」**(R-10 + R-11 疊加)
   `[amendment 2026-07-30 round2: R16 — 原本靠 R-12 緩解,R-12 已撤回,改為承擔]`:
   TC4 忙碌(回補 worker 佔 `api.lock` / 多 symbol 並行查)時某檔可能 >10s 才備妥 →
   `_collect_history` 回空 → 負向快取釘 15s → `CandleChart` 顯示「無 K 線資料」。
   **接受理由**:這是**既有行為**,現況只是等滿 60s 後顯示同一句話;本輪讓它更快抵達
   同一結論,沒有讓訊息品質變差。交易時段前端 60s 輪詢會自癒;非交易時段最壞需切走再切回。
   **要真正修好**必須把「逾時 / 真無資料 / TC4 斷線」沿
   `_collect_history → fetch_bars_range → bars_range → BarsFetcher` 整條型別鏈區分開,
   屬獨立一輪的工作 → 記入 `docs/next-time.md`。
2. **大螢幕明細列數固定**(R-6a):下半列改固定 224px 後,1920×1080 上明細不再比
   1440×900 顯示更多列。此為 user「圖表吃剩餘高度 + 貼底」要求的直接代價。
3. **五檔卡片底部留白**(R-8/R-6a):`h-full` 讓卡片撐滿 224px,內容約 200px →
   底部約 24px 留白。此為對既有 `self-start` 取捨的刻意推翻。

self_review_head: 0f23f0b137c3fba66a71572712e9c0e37957539b

self_review_head(rebase 後): adbe5c7851b3e7d90afa088f3f9c25b7dfcc4062
