# change-spec — 個股 UI 第四輪(stock-ui-round4)

Phase 1 現況表:`./current-state.md`(caller map / baseline / 逐項現況)。
規模分流:**L**(≥5 檔 + 新增對外 endpoint + 新增版控資料檔)→ Phase 3 預設 1 輪 review,accepted P0 觸發限縮加輪 1 次。

## 分流判定

**已成形改法** — 命中 `feat-phase0-2.md` 判準 1(6 項需求各自指名 UI 形式:「不要用 tab」/「可縮小或展開」/「拖曳改變群組」/「刻度移到右邊」/「顯示布林通道 5ma 20ma」)與判準 2(資料源、拖曳語意、BB 按鈕去留皆為可逐分支追問的決策點)→ 提問走 `grilling` 姿態(確認 + counter-proposal),user 已拍板 4 項決策。

## User 拍板紀錄(2026-07-30)

| 決策 | 選擇 |
|---|---|
| 項 1 名稱資料源 | **TWSE ISIN 全市場**(`isin.twse.com.tw` strMode=2 上市 / 4 上櫃) |
| 項 2 跨群組拖曳語意 | **移動**(來源移除;一檔多組仍可由 ⊞ 面板維護) |
| 項 6 BB 按鈕 | **保留按鈕但預設開**(需一次性強制升級既有 localStorage) |
| 項 2 新增落點 | **各組標題列自帶 `+` 鈕,取消「全部」** |

## Auto-default 決策(未問 user,可事後 audit)

- `[auto-default: 名稱表落 git 版控 `copycat/stock_names.json` | reason: 完全比照既有 `stkfut_map.json`(tracked + refresh CLI)。落 git-ignored `data/` 的話 merge 到 master 後 user 端沒有檔案 → 功能死在那裡直到手動跑 CLI]`
- `[auto-default: 名稱表整包給前端過濾,不做 server-side ?q= 查詢 | reason: 表僅 2,401 筆(落檔 59,727 bytes)一次載入即可,提示列零延遲;過濾邏輯落純函數可單測,免每次按鍵打 API]` **[amendment 2026-07-30: review R8 — 原寫「~3.4k 筆 / ~110 KB」與自列的分段實測矛盾 40%]** **[amendment 2026-07-30: review R24 — 改引用「實際落檔大小 59,727 bytes」(前端載入成本的真正基準);probe 的 57,363(big5)/ 57,322(cp950)是不同 dumps 參數的產物,三個數字的出處已在 probe-evidence.md 分開記清]**
- `[auto-default: ISIN 分類過濾用「排除法」— section 名含「權證」者剔除,其餘全收 | reason: 權證是唯一巨量段(上市 30,561 + 上櫃 9,438 = 39,999 列),排除後 2,401。允許清單反而會在 TWSE 改段名時靜默漏掉「股票」段。refresh 時 log 逐段筆數讓漂移可見]`
- `[auto-default: HTML 解碼用 cp950 不用 big5 | reason: review R12 實測同一份上市 HTML,big5 + errors=replace 解出 **447 個 U+FFFD**、cp950 解出 **0 個**。cp950 是 Big5 超集,名稱表的唯一用途是給人看/搜,靜默毀字不可接受]` **[amendment 2026-07-30: review R12]**
- `[auto-default: 名稱表 entry 需通過 `validate_code` 才收 | reason: 提示列只該提供「加得進自選」的代碼,否則點了才被後端 400 打回]`
- `[auto-default: 江波圖 gutter 寬 = 46 = PRICE_TAG.w | reason: hover 價位標(寬 46)恰好整格塞進 gutter,不再壓線;y-tick 文字(~24px)也綽綽有餘]`
- `[auto-default: 折疊狀態存 localStorage `stock-wl-collapsed`(群組名陣列) | reason: 與既有 `stock-wl-group` / `copycat-chart-mode` 同慣例;跨重載保持是 SC-3 明文要求]`
- `[auto-default: 折疊中的群組仍是 drop target(index 固定 = append 到尾) | reason: 否則折疊等於「不能拖進去」,是隱形陷阱;實作上 zone 取 section 外框而非只取 `<ul>`]`
- `[auto-default: 空群組保留 44px 最小高度 + 「拖曳股票到此」提示 | reason: 沒有高度就沒有 rect,空群組會變成拖不進去的死組]`
- `[auto-default: 舊 localStorage key `stock-wl-group` 不主動清 | reason: 讀取端移除即失效,清 key 屬破壞性且零收益]`

## 一、改完的成功條件(可驗收;UI 類為畫面可指認表述)

| SC | 條件(畫面可指認) |
|---|---|
| SC-1a | 側欄任一群組標題列的 `+` 鈕 → 該組下方出現輸入框。輸入 `台積` → 輸入框下方出現提示列,其中一列文字為 `2330` 與 `台積電`;輸入 `2330` → 提示列同樣出現該列。 |
| SC-1b | 點提示列的 `2330 台積電` → 該列消失、`2330` 出現在**該群組**的股票列中(不是別組)。 |
| SC-1c | 輸入框打完整股號後按 Enter,即使提示列無命中(例:新上市股不在表內)仍照加入該組 —— **既有行為保留**。 |
| SC-2 | 側欄同時看到**所有群組名稱各自成一段**;畫面上**沒有**「全部」按鈕、沒有橫排 tab 列(DOM 中 `role="tablist"` 不存在)。 |
| SC-2b | **[amendment 2026-07-30: review R6 — 零群組沒有新增入口是死路]** 一個群組都沒有時(冷啟動 / 全刪),側欄顯示「尚無自選,輸入股號新增」+ 一個搜尋框;在該框加入股票 → 自動建立名為「自選」的群組並把股票放進去(等同既有「全部」下新增的語意,只是落在空狀態)。 |
| SC-3 | 每個群組名稱左側有折疊指示符(`▾` 展開 / `▸` 收合)。點一下 → 該組股票列隱藏、標題列仍在、其他組不受影響。重新載入頁面後折疊狀態維持。 |
| SC-4a | 按住 A 組某列的拖拉握把,移到 B 組股票列範圍內放開 → 該股票**從 A 組消失**、出現在 B 組放開位置。 |
| SC-4b | 同一組內拖曳仍為排序(順序改變、組別不變)。 |
| SC-4c | **[amendment 2026-07-30: review R9 — 移動語意不可逆,缺誤觸護欄]** 拖著股票離開側欄水平範圍(例如放在中間 K 線圖上)放開 → **什麼都不發生**(股票留在原組);拖曳中按 Esc → 取消,股票留在原組。 |
| SC-5 | 江波圖**左緣** y 軸價位數字全部落在走勢線左側的空白帶內;走勢線、紅綠填色、格線、疊線的左端一律自該帶右緣(x=46)才開始。**右緣的 CDP/MA 價位標不在本 SC 範圍**(見 out of scope)。 **[amendment 2026-07-30: review R11 — 原絕對句「沒有任何價位文字壓在線上」與 out-of-scope 的右緣標籤直接衝突]** |
| SC-6 | 每個左緣價位對應**一條淡色虛線水平線**橫貫繪圖區(從價位文字右側到圖右緣),與既有整點垂直線同色系(`stroke-line`)。 |
| SC-7 | 內外盤能量副圖的兩個張數數字(頂端 = 當日單邊最大張數、中線 = 其一半)顯示在副圖**右緣**;副圖左緣不再有數字。**中線那個數字不被右緣的 bar 蓋住**(盤中右緣恆有 bar;頂端數字有 `SUB_TOP_PAD` 清出的空白保護,中線沒有等價保護)。 **[amendment 2026-07-30: review R15a — 原 SC 驗不到它想達成的可讀性]** |
| SC-8 | 切到「日K」或任一「分K」,**不必按 BB 鈕**就看到:布林上下軌兩條虛線 + 兩軌之間帶狀填色 + MA5 / MA20 兩條實線。BB 鈕仍在、仍可按掉;按掉後重新載入頁面維持關閉。 |
| SC-9 | 量化 gate:`npm test`(frontend/)+ `npx tsc -b` + `npx eslint src` 全綠;`pytest -q` + `ruff check copycat tests` + `pyright` 全綠。單位 = 測試通過數 / exit code,量法 = 直接跑指令看輸出。 |
| SC-10 | `python -m copycat refresh-stock-names` 實跑成功,stdout 印出收錄檔數且落在 **[1800, 6000]**(實測基準 2,401),log 中出現**被剔除的權證段列數**(實測 39,999);`GET /api/stock/names` 回同一份表(`count` 相符)。 **[amendment 2026-07-30: review R7/R8 — 原「≥ 2,000」單側門檻對「段標題偵測失效 → 權證全收(~42,000 筆)」完全不觸發,而那正是最可能的漂移方向]** |

## 二、不能破壞的既有行為白名單(**優先於新行為**)

| W | 行為 | 現況出處 |
|---|---|---|
| W-1 | **一檔可同屬多組**;每列 `⊞`(`aria-label="移組 <code>"`)展開 checkbox 面板可勾選/取消所屬群組 | `WatchlistSidebar.tsx:121-130,286-296,312-327` |
| W-2 | 後端 v2 schema `{groups:[{name,codes}]}` 不變、union 30 檔上限、v1 讀時遷移、群組內去重保序、`BAD_CODE`/`BAD_GROUP`/`WATCHLIST_FULL` 錯誤碼與中文文案 | `stock_watchlist.py`、`WatchlistSidebar.tsx:28-33` |
| W-3 | 群組刪除 PUT 失敗(4xx)→ 顯示錯誤文案、**沒有發第二次 PUT**、該組的**折疊狀態與展開中的搜尋框(`adding`)不變** | `WatchlistSidebar.tsx:113-119` + 既有測試 `:142-155`。**[amendment 2026-07-30: review R14 — `activeGroup` 消失後,原本的「不切走 active tab」失去實體,「兩組 section 仍在」在任何實作下都成立 = 不可證偽的空斷言]** |
| W-16 | **零群組時仍有新增股票的入口**(既有「全部」下新增自動建「自選」的語意不得消失,只換落點) | `WatchlistSidebar.tsx:78-87` + 既有測試 `:102-110`。**[amendment 2026-07-30: review R6 — 原 spec 直接刪掉這條路徑,冷啟動撞死路]** |
| W-4 | 直接打完整股號 → Enter / 「新增」即加入,**不強制先選提示列** | `WatchlistSidebar.tsx:69-90` |
| W-5 | 點股票列觸發 `onSelect(code)` 換股;拖拉握把 / 折疊鈕 / `⊞` / `×` / 提示列的點擊**不得**冒泡成換股 | `WatchlistSidebar.tsx:257,264-265,290,301` |
| W-6 | 江波圖 hover:垂直線與資料點**只在該分鐘有成交時**畫(`minuteOf` 不 snap 最近);水平線與左緣價位標**恆畫**(自由量尺) | `StockIntradayChart.tsx:467-497`、`stock-intraday-svg.ts:189-193` |
| W-7 | `ChartStatic` / `EnergySub` 維持 `memo`,尺寸 props 維持**純量**(`w`/`h`,不可傳物件) | `StockIntradayChart.tsx:87-104,254-266` |
| W-8 | `toY` ↔ `priceAtY` 互逆(共用同一組 `PAD_Y`/`X_LABEL_H`);**新增 gutter 後 `toX` ↔ `minuteOf` 亦須互逆** | `stock-intraday-svg.ts:8-9,131-137` |
| W-9 | 主圖與內外盤副圖**同一分鐘 x 對位**(hover 垂直線貫穿兩圖仍對準同一根 bar) | `StockIntradayChart.tsx:546-558` |
| W-10 | `useChartToggles` 兩個 instance 交替 `set` 不互相覆蓋(`set` 先重讀 localStorage 再 merge) | `useChartToggles.ts:30-38` + 既有測試 `:48-59` |
| W-11 | 使用者**手動**關掉 BB 後,重載維持關(一次性升級只做一次,不得每次 load 都打開) | 本輪新增語意(對應 `useChartToggles.ts:13-14` 的「不強制升級」原則) |
| W-12 | 江波圖無漲跌停 → 對稱 autofit fallback;退化域(upper==lower)→ `flat` 常數特判 | `stock-intraday-svg.ts:116-137` |
| W-13 | K 線 MA/BB **以完整序列算完再裁切**(左緣不斷頭、y 域不被視窗外極值撐開) | `CandleChart.tsx:318-334` |
| W-14 | 江波圖 y 域恰為 `[lower, upper]` 不留 2% 邊;y-tick 由上而下 ±10/8/…/0/…/−10%、域外刻度跳過、snap 去重 | `stock-intraday-svg.ts:110-186` |
| W-15 | K 線圖既有互動:滾輪縮放(原生 listener + `passive:false`)、拖曳平移、`key={code}-{mode}` 換股重掛 | `CandleChart.tsx:349-402`、`StockChart.tsx:106` |

## 三、Backward compat / migration 策略

| 面 | 策略 |
|---|---|
| `/api/stock/watchlist` GET/PUT 契約 | **零改動**(shape、驗證、錯誤碼全不動) |
| 自選 JSON schema | **零改動**(v2 `groups`;v1 讀時遷移不動) |
| 新增 `GET /api/stock/names` | 純新增,無既有 caller;回 `{"names":[{code,name}],"count":N}`。表不存在 → `{"names":[],"count":0}`(不 500);前端表空時提示列不出現,SC-1c 的直接輸入路徑照常可用 |
| `copycat/stock_names.json` | 新增**版控**檔(比照 `stkfut_map.json`);`refresh-stock-names` CLI 重生,抓取/解析失敗保留舊檔並拋出 |
| localStorage `stock-wl-group` | 讀取端移除 → 自然失效。**不清 key**(破壞性且零收益) |
| localStorage `copycat-chart-toggles` | 加 storage-only 欄位 `v`;`v` 缺或 < 2 → 一次性把 `bb` 設 true **並立即落檔**(否則使用者關掉 BB 後每次重載又被打開,違反 W-11)。`vwap`/`cdp`/`ma` 的既有選擇不動 |
| `StockChart` → `CandleChart` props | `showBb`/`onToggleBb` 保留(BB 鈕不移除)→ 零改動 |
| `StockPage` → `WatchlistSidebar` props | `active`/`onSelect`/`quotes` 三個 props 語意與型別**不變** |

## 四、Out of scope

- 權證 / ETN / 受益證券 進名稱表(排除法剔除「權證」段;ETN 等雖被收進表但不特別驗證)
- 名稱表自動 / 定期更新(只有手動 CLI;`GET /api/stock/names` 不觸發抓取)
- server-side 模糊搜尋 / 拼音 / 注音輸入
- K 線圖新增量刻度數字(現在沒有,本輪不加)
- 江波圖右緣 CDP/MA 價位標的位置與配色
- 期貨 / 指數 / TXO / 相關係數 / 下單面板任何改動
- 個股期對映 `stkfut_map.json` 不動
- 觸控裝置上的跨群組拖曳手感調校(pointer events 天然支援,但不列 SC)
- `futures_engine` 間歇性零推播(CLAUDE.md §8 既有 P1),本輪不碰

---

# Phase 3 — Diff 級 spec(逐檔)

順序遵循 /mod Phase 4:**🔵 → 🔴 → 🟢**。

## 🔵-1 `frontend/src/lib/stock-intraday-svg.ts` — 抽出共用 `minuteToX`

**動什麼**:把目前分散在 lib(`buildIntradayGeometry` 內的區域 `toX`)與元件(`StockIntradayChart.tsx:49-51` 的模組級 `toX`)的**兩套同式** x 映射,收斂成單一 export。

```ts
export function minuteToX(minute: number, width: number): number   // 新 export
export function plotWidth(width: number): number                   // 新 export(= width − Y_AXIS_W,本步先回 width)
```

- 本步 **不改數值**:`minuteToX` 實作等同現行公式,`buildIntradayGeometry` 內部改呼叫它,元件改 import 它。
- 為什麼:`StockIntradayChart.tsx:47-48` 的註解已自認「模組級純函數也一併參數化以免兩套來源漂移」—— 🔴-3 要在這條公式加 gutter,兩套來源同時改對的風險不必承擔。

**測試**:完全不動(純重構,行為零差異)。既有 `stock-intraday-svg.test.ts` / `StockIntradayChart.test.tsx` 應維持全綠。

## 🔵-2 `frontend/src/components/stock/StockIntradayChart.tsx` — 改用共用 `minuteToX`

**動什麼**:刪除本地 `toX`(`:49-51`),全部呼叫點改 `minuteToX(minute, mainW)`;`barW`(`:53-55`)改吃 `plotWidth(width)`。
**測試**:不動。

## 🔴-3 `frontend/src/lib/stock-intraday-svg.ts` — 左側 gutter(SC-5)

**動什麼**

```ts
export const Y_AXIS_W = 46;   // 新增:左緣價位帶寬度(= 元件 PRICE_TAG.w,hover 價位標恰好整格塞進)
export function plotWidth(width: number): number { return Math.max(1, width - Y_AXIS_W); }
export function minuteToX(minute, width) {
  return Y_AXIS_W + ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * plotWidth(width);
}
```

- `buildIntradayGeometry` 內 `minuteOf` 同步改為 gutter 版反演,且**必須與 `minuteToX` 共用 `Y_AXIS_W` / `plotWidth`**(W-8):
  `x < Y_AXIS_W || x > width → null`;否則 `round((x − Y_AXIS_W) / plotWidth(width) × span) + X_START_MIN`,再查 `haveMinutes`。
- `priceLine` / `vwapLine` / `energyBars` / `areaPolygon` 全部經 `minuteToX` → 自動平移,**主副圖同 width(800)故 x 對位守恆(W-9)**。
- `toY` / `priceAtY` / `yTicks` / `yDomain` / `maxSide` **不動**(W-8 / W-12 / W-14)。

**既有測試逐一標**

| 測試 | 判定 |
|---|---|
| `stock-intraday-svg.test.ts` 中斷言 `priceLine[i].x` / `energyBars[i].x` / `minuteOf(x)` 具體數值者 | **🔴 該紅** → 改期望值為 gutter 版 |
| 同檔 `:121-130`「areaPolygon 以 refY 封閉」(字串比對 `pts[0] === "0.0,<refY>"`) | **🔴 該紅** —— **[amendment 2026-07-30: review R10]** 原 pattern 只寫「斷言 x 具體數值者」漏了字串比對。補通則:**凡以字串比對座標的斷言(`areaPolygon` / `pts()`)一律該紅**;另 `:33-51` 的註解「x:每分鐘 1px(width = 分鐘數)」前提失效,fixture width 要改成 `Y_AXIS_W + 270` 才維持 1px/分 |
| 同檔 y 相關(`toY`/`priceAtY`/`yTicks`/`refY`/`maxSide`/`outerH`)斷言 | **不該紅**;若紅 → 打到不該動的東西 |
| `StockIntradayChart.test.tsx` 中 `y-tick-price` 文字內容 / crosshair 存在性斷言 | **不該紅**(文字與 y 不變) |

**新測試**

- `minuteToX(X_START_MIN, 800) === Y_AXIS_W`、`minuteToX(X_END_MIN, 800) === 800`
- **往返一致**:對每個有成交的分鐘 `minuteOf(minuteToX(m, w)) === m`(gutter 版互逆,W-8)
- `minuteOf(Y_AXIS_W - 1) === null`(gutter 內不對應任何分鐘)
- `energyBars[0].x === Y_AXIS_W`(副圖與主圖同起點,W-9)

## 🔴-4 `frontend/src/components/stock/StockIntradayChart.tsx` — 線起點退到 gutter 右側 + 價位水平線 + 量刻度靠右(SC-5/6/7)

**動什麼**(逐處)

| 位置 | 現況 | 改為 |
|---|---|---|
| `:128` 平盤虛線 | `x1={0} x2={w}` | `x1={Y_AXIS_W}` |
| `:141-153` y-tick | 只有 `<text x={2}>` | **新增** `<line data-testid="y-grid" x1={Y_AXIS_W} x2={w} y1={t.y} y2={t.y} className="stroke-line" strokeDasharray="2 3" strokeWidth={0.5} />`(風格對齊 `CandleChart.tsx:105-113`);text 維持 `x={2}` 與既有 y 夾制 |
| `:172-193` 疊線 | `x1={0}` | `x1={Y_AXIS_W}`(`x2={w-34}` 不動) |
| `:488-497` crosshair-h | `x1={0} x2={mainW}` | `x1={Y_AXIS_W}` |
| `:270-278` EnergySub 量刻度 | `<line x1={0}>`、兩個 `<text x={2}>` | `<line x1={Y_AXIS_W}>`;兩個 text 改 `x={w-2}` + `textAnchor="end"`(**SC-7**) |
| `:499-516` hover 價位標 | `translate(0, …)` | 不動(x=0 寬 46 恰為 gutter) |

`X_LABELS` 垂直線、`XAxisLabels` 文字、crosshair-v、副圖 hover 線皆走 `minuteToX` → 不必逐處改。

**既有測試逐一標**

| 測試 | 判定 |
|---|---|
| `StockIntradayChart.test.tsx` 若有斷言 crosshair-h 的 `x1="0"` 或疊線 `x1` | **🔴 該紅** → 改期望為 `Y_AXIS_W` |
| **`StockIntradayChart.test.tsx` 以 `clientX: 3` 觸發 hover 的 6 處(`:236` / `:274` / `:285` / `:294` / `:296` / `:317`)** | **🔴 該紅(純座標平移)** —— **[amendment 2026-07-30: review R1(P0)]** 原表把這些歸在「memo / hover 退化 → 不該紅」,實際上 gutter 後 x=3 落進價位帶 → `minuteOf(3)` 回 `null` → `time-tag` / `crosshair-v` / hover 資訊列全消失,**5 支必紅**。改法:`clientX` 改 **49**(minute 541 的新落點 ≈48.8,合法區間 [47.4, 50.2)),**斷言內容與語意一字不改**。⚠ 誤把它當「打到不該動的東西」而回頭加 snap,會直接破壞 W-6 |
| 同檔 `clientX: 400`(「~11:15 無資料」那支) | **不該紅** —— 新座標下 `minuteOf(400) = 667` 仍無成交,W-6 的分解退化仍被鎖住 |
| `y-tick-price` 文字數量 / 內容 | **不該紅** |
| memo / toggle 反灰 相關 | **不該紅**(W-7) |

**新測試**:y-grid 線條數 === `y-tick-price` 文字數且 `x1 === Y_AXIS_W`(SC-6);量刻度 text 的 `text-anchor === "end"` 且 `x === w-2`(SC-7)。

**[amendment 2026-07-30: review R15b]** 元件的 `PRICE_TAG` 改為 `{ w: Y_AXIS_W, h: 14 }`(直接 import 而非另寫一份 46)—— 兩份 46 靠註解維持相等,任一方改動就讓「hover 價位標壓線」這個本輪要修的症狀復發,且沒有測試會發現。加一支測試鎖 `price-tag` 的 `width === Y_AXIS_W`。

**[amendment 2026-07-30: review R15a → R20 更正]** 量刻度兩個數字都以 **`paintOrder="stroke"` + `stroke-surface`** 描邊拉對比(**不是** `fill-bg-deep` 底 —— 江波圖容器背景是 `bg-surface` `#10161f`,`bg-deep` 是 `#060910`,照原文做會畫出比背景更深的錯色光暈)。理由:bar 一路畫到右緣,右緣數字必然與 bar 同區域;頂端數字之所以看得見是 `SUB_TOP_PAD` 清空了頂 10px,中線沒有等價保護。同時修掉元件內「bar 從 Y_AXIS_W 起,不會壓到右緣數字」那句自相矛盾的註解(本輪自己寫錯的)。

## 🔴-5 `frontend/src/hooks/useChartToggles.ts` — BB 預設開 + 一次性升級(SC-8 / W-11)

```ts
const TOGGLES_VERSION = 2;
const DEFAULTS: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true };  // bb false → true
```

`load()`:讀 raw → 壞 JSON 回 `DEFAULTS`;取出 storage-only 的 `v`(**不得混進 `ChartToggles` 物件**);
`(v ?? 1) < TOGGLES_VERSION` → `upgraded = {...DEFAULTS, ...saved, bb: true}` **並立即 `persist(upgraded)`**(帶 `v: 2`)後回傳;否則回 `{...DEFAULTS, ...saved}`。
`set()`:`persist({...load(), [key]: value})`,寫入時附 `v: TOGGLES_VERSION`(W-10 的「重讀 localStorage 當基底」不變)。

**既有測試逐一標**

| 測試 | 判定 |
|---|---|
| `:19-22`「預設 vwap/cdp 開、ma/bb 關」 | **🔴 該紅** → `bb` 期望改 true |
| `:24-31` set 持久化(斷言整包 === `{...DEFAULTS, cdp:false}`) | **🔴 該紅**(多了 `v:2`、`bb` 變 true)→ 改期望 |
| `:33-37` 壞 JSON 回預設 | **🔴 該紅**(DEFAULTS 變了)→ 改期望 |
| `:39-44`「既有存檔不被新預設覆蓋(cdp 曾關過維持關)」+ 同案 `bb` 期望 false | **🔴 該紅**:`cdp: false` 仍須維持(**不可退讓**),但同案 `:43` 的 `bb` 期望改 true(這正是本次刻意的一次性升級) |
| `:48-59` 兩 instance 交替 set 不互相覆蓋 | **🔴 該紅(僅因期望值多 `v: 2`)** —— **[amendment 2026-07-30: review R2]** 它以**整包 `toEqual`** 斷言 localStorage,`set()` 寫入 `v` 後必紅(與 `:24-31` 同因)。期望改 `{vwap:true, cdp:false, ma:false, bb:…, v:2}`;**「`cdp:false` 沒有被 b 的 stale prev 還原」這條語意不可退讓**(W-10 的真正斷言)。⚠ 誤判成「打到 merge 基底邏輯」而去改 `set()` 的重讀行為 = 直接拆掉 W-10 的保護。通則:**凡以整包 `toEqual` 斷言 localStorage 內容者皆因 `v` 欄位該紅** |

**新測試(W-11)**:存 `{...,bb:true,v:2}` → `set("bb", false)` → **重新 mount** → `bb` 仍為 false(升級不再觸發);且升級路徑跑完後 localStorage 內 `v === 2`(證明已落檔)。

## 🟢-6 `copycat/stock_names.py`(新檔)— 全市場 code↔name 表

比照 `copycat/stkfut_map.py` 形狀(module 級 `_CACHE_VERSION` / `DEFAULT_PATH` / `load_*` / `write_*` / `refresh`)。

**[amendment 2026-07-30: review R22 — 原簽名做不到 R7 的守門(需逐段筆數)也做不到 R12 的注入(需 fetcher)]**

```python
_CACHE_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parent / "stock_names.json"
ISIN_URLS = ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",   # 上市
             "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")   # 上櫃

@dataclass
class ParseStats:                       # 漂移可見性的載體(refresh 的守門與 log 靠它)
    per_section: dict[str, int]
    warrant_rows: int
    dropped: dict[str, int]             # cells / no_separator / bad_code / empty_name
    duplicates: list[str]

def parse_isin_html(html: str) -> dict[str, str]                              # 便利包裝
def parse_isin_html_with_stats(html: str) -> tuple[dict[str, str], ParseStats]
def load_names(path: Path = DEFAULT_PATH) -> dict[str, str]
def write_names(path: Path, names: dict[str, str]) -> None
def refresh(path: Path = DEFAULT_PATH,
            urls: tuple[str, ...] = ISIN_URLS,
            fetcher: Callable[[str, float], bytes] = _default_fetcher) -> dict[str, str]
```

刻意做成**兩支函式**而不是一個 `with_stats: bool` flag —— union 回傳型別在呼叫端無法窄化,只能靠 `assert isinstance` 補,那是把型別檢查推回 runtime(pyright 實測會擋)。

`parse_isin_html` 規則(**2026-07-30 實測**:上市段 = 股票 1054 / 權證 30561 / 特別股 28 / 創新板 29 / ETF 236 / ETN 15 / TDR 10 / 受益證券 6;上櫃段 = 權證 9438 / ETF 118 / ETN 6 / 股票 890 / 特別股 1 / 受益證券 8):

1. `<tr>` 逐列;**單一 `<td>` 的列 = 分類段標題**,更新「當前段名」。
2. 當前段名含「權證」→ 該段所有列略過(唯一巨量段)。
3. 資料列:`cells[0]` 形如 `"2330　台積電"`(全形空格分隔)→ **`cells[0].split("　", 1)`**(明訂 maxsplit=1,name 端 `strip()`);缺分隔或欄數 < 4 → 略過並計數。 **[amendment 2026-07-30: review R13 — 未指定 maxsplit,名稱本身含全形空格會被切碎或整列誤剔。實測上市段目前 0 筆這種名稱,但版控產物的差異會進 diff,規則不能留白]**
4. `validate_code(code)`(複用 `copycat.stock_watchlist.validate_code`)為假 → 略過(auto-default:只收加得進自選的代碼)。
5. 名稱 strip 後為空 → 略過。
6. 重複 code → 保留**先出現**者,**筆數 > 0 時 `logger.warning` 印出重複清單(不只計數)**(上市優先於上櫃,因 URL 順序)。 **[amendment 2026-07-30: review R13]**

`refresh`:逐 URL 抓(`urllib.request`,`User-Agent: copycat/stock-names`,timeout 60 —— 實測 7.5 MB + 2.5 MB)、**`decode("cp950", errors="replace")`**、合併;成功則 `write_names` + `logger.info` 印**逐段筆數與總數**(auto-default 的「漂移可見」承諾;禁止靜默截斷)。

**[amendment 2026-07-30: review R7/R12(1) — 守門改雙側 + 語意檢查;解碼改 cp950]**

- 解碼 **`cp950` 不是 `big5`**:實測同一份上市 HTML,`big5` 解出 447 個 `U+FFFD`、`cp950` 解出 0 個。另在 refresh 對「名稱含 `U+FFFD` 的筆數」`logger.warning`(> 0 即代表又有新字元超出 cp950)。
- 守門三條,任一不成立 → `raise ValueError` **保留舊檔**:
  1. 總筆數落在 **[1800, 6000]**(實測 2,401)。**上界是關鍵** —— 段標題偵測靠「單一 `<td>` 的列」,一旦 TWSE 改成 `colspan` + 空 `<td>`,段名永遠不更新 → 「含權證 → 略過」整條失效 → 39,999 筆權證全收,總數 ~42,000 遠大於任何下界,單側門檻完全不觸發而靜默覆寫版控檔。
  2. 段名**含**「權證」者的剔除列數**跨 URL 合計** > 5,000(實測 39,999)—— 直接把「段落偵測還活著」變成可驗證的前置條件。
  3. 段名**含**「股票」者的收錄筆數**跨 URL 合計** > 500(實測 1,944 = 1,054 + 890)。

  **[amendment 2026-07-30: review R21]** 守門 2/3 一律 **substring 比對 + 跨 URL 合計**,不是精確段名、不是逐段。精確段名比對會在 TWSE 把「股票」改成「上市股票」這種無害微調後讓 CLI 整條死掉,而本節 auto-default 選排除法的理由正是要避開段名耦合;逐段門檻則會在權證拆成認購/認售兩段(各 < 5,000)時誤觸。
except 集合含 `TimeoutError`(CLAUDE.md §8:SSL read timeout 不包在 `URLError`)—— 但 `refresh` 是 CLI 一次性動作,**原樣拋出**不吞(比照 `stkfut_map.refresh`)。

**新測試** `tests/test_stock_names.py`(離線,餵 HTML 字串):
段標題切換正確;權證段被剔除;全形空格解析(**含「名稱本身有全形空格」→ maxsplit=1 切分正確**);`validate_code` 不合格列被剔除;重複 code 取先出現;段內欄數不足列不炸;`load_names` 檔不存在回 `{}`、**壞 JSON / 缺 `names` 鍵回 `{}` 不拋**;`write_names`/`load_names` round-trip;`refresh` 在**下界不足**、**上界超出(模擬段標題偵測失效 → 權證全收)**、**沒有偵測到權證段**三種情形皆拋錯且**不覆寫舊檔**(注入 fake fetcher)。 **[amendment 2026-07-30: review R7/R12(2)/R13]**

**[amendment 2026-07-30: review R12(2)]** `load_names` 的韌性:比照 `stkfut_map.load_map` 只擋「檔不存在」是不夠的 —— 壞 JSON 會拋 `JSONDecodeError` 讓 `/api/stock/names` 回 500,與 🟢-8 的「不 500」承諾矛盾。改為 `except (json.JSONDecodeError, OSError, TypeError, AttributeError)` → 回 `{}` + `logger.warning`。

## 🟢-7 `copycat/cli.py` — `refresh-stock-names` 子命令

`sub.add_parser("refresh-stock-names", help="重抓 TWSE ISIN 全市場股票名稱表(搜尋提示用)")`(比照 `:137` 的 `refresh-stkfut-map` 無參數形式);dispatch 段比照 `:344-348` 印 `f"股票名稱表更新完成:{len(names)} 檔\n"`,回 0。

**新測試**:`tests/test_cli.py`(若已存在則追加)以 monkeypatch 攔 `refresh`,驗 exit code 0 與 stdout 含檔數。

## 🟢-8 `copycat/server/app.py` — `GET /api/stock/names`

放在 `# ---- stock` 區塊內(`:416` 附近),**不經 `_stock(request)` 閘**(名稱表與 TC4 連線無關,達錢 4 沒開也該能搜尋):

```python
# app.py 頂部:from copycat.stock_names import load_names as load_stock_names
# create_app(..., stock_names_path: Path | None = None) → names_path = stock_names_path or NAMES_DEFAULT_PATH

@app.get("/api/stock/names")
async def stock_names() -> dict:
    names = load_stock_names(names_path)
    return {"names": [{"code": c, "name": n} for c, n in names.items()], "count": len(names)}
```

檔不存在 / 壞 JSON → `load_names` 回 `{}` → `{"names": [], "count": 0}`(不 500)。
`[auto-default: 每次請求重讀檔 | reason: 57 KB、單機單使用者、前端 staleTime Infinity 只打一次;省掉 cache 失效這條路徑]`

**[amendment 2026-07-30: review R12(3)]** 兩處修正:(a) 函式名統一為 `load_names`(app 端以 `as load_stock_names` alias,不在兩處各寫一份);(b) `create_app` 加 `stock_names_path: Path | None = None` 注入點 —— `copycat/stock_names.json` 是**版控檔必然存在**,沒有注入點的話 spec 指定的「表為空時回空陣列不 500」與「壞檔」兩個案例**根本沒有製造手段**(比照既有 `stock_watchlist_path` 的慣例)。

**新測試** `tests/server/`(比照既有 app 測試檔):200 + shape;`stock_names_path` 指向不存在的檔 → 空陣列不 500;指向壞 JSON → 空陣列不 500。

## 🟢-9 `frontend/src/lib/stock-search.ts`(新檔)— 提示列過濾純函數

```ts
export interface StockName { code: string; name: string }
export function searchStocks(query: string, table: readonly StockName[], limit = 20): StockName[]
```

規則:trim;空 → `[]`。比對用 `query.toUpperCase()`:
1. **代碼前綴命中**優先(`code.startsWith(q)`),按 code 升序;
2. 其次**名稱子字串命中**(`name.includes(原始 trim 後 query)`,中文不做大小寫轉換),按 code 升序;
3. 兩段合併去重後取前 `limit`。

**新測試**:`2330` → 首列 2330;`台積` → 命中 2330;`23` → 前綴多筆且 2330 在內;小寫 `00679b` 命中 `00679B`(大小寫不敏感);空字串 / 全空白 → `[]`;`limit` 生效;代碼命中排在名稱命中之前。

## 🟢-10 `frontend/src/hooks/useStockNames.ts`(新檔)

TanStack Query:`queryKey: ["stock-names"]`、`staleTime: Infinity`、`gcTime: Infinity`、`retry: 1`;`fetch("/api/stock/names")` → `body.names`;失敗回 `[]` 由呼叫端當「表不可用」處理(錯誤解析比照 `useStockWatchlist.ts:8-15` 的 `detail.error`)。

**新測試**:比照 `useStockWatchlist.test.tsx` 的 fetch stub;成功回陣列、404 → error 態。

## 🟢/🔴-11 `frontend/src/lib/list-drag.ts` — 跨群組 drop 目標 + move(SC-4)

**🟢 新增**(既有 `reorder` / `insertIndexFromPointer` **不動**,仍為同組排序與既有測試所用):

```ts
export interface DropZone {
  group: string;
  /** section 外框上下緣(含標題列;折疊時只有標題列) */
  top: number;
  bottom: number;
  /** 股票列第一列上緣。**折疊時不使用**(見 collapsed) */
  listTop: number;
  count: number;
  /** 折疊中 → 一律 append 到尾,不走 rowHeight 公式 */
  collapsed: boolean;
}
/** pointer (x, y) → 落點群組 + 插入 index。
 *  x 落在側欄水平範圍外 → `null`(整個拖曳作廢);y 落在 zone 之間的縫隙 → 取最近 zone。 */
export function dropTargetFromPointer(
  p: { x: number; y: number },
  zones: readonly DropZone[],
  rowHeight: number,
  bounds: { left: number; right: number },
): { group: string; index: number } | null;

/** 把 code 從 fromGroup 移到 toGroup 的 index(from === to 時等價於同組重排)。 */
export function moveCode<G extends { name: string; codes: string[] }>(
  groups: readonly G[], code: string, fromGroup: string, toGroup: string, index: number,
): G[];
```

- `dropTargetFromPointer`:**先驗 x** —— `p.x < bounds.left - 16 || p.x > bounds.right + 16` → `null`;再命中 `top <= y < bottom` 的 zone;無命中 → 取到區間距離最小者;`zones` 空 → `null`。
  `index = collapsed ? count : clamp(round((y − listTop) / rowHeight), 0, count)` —— **上界是 `count` 不是 `count−1`**(跨組要能 append,與 `insertIndexFromPointer` 的同組語意刻意不同)。

**[amendment 2026-07-30: review R4]** 折疊分支原本寫「`listTop = bottom` → index 恆為 count」是**算術上錯的**:命中條件是 `y < bottom`,所以 `y − listTop < 0` → `round(負)` → clamp 成 **0**(prepend),與註解和 spec 自己指定的新測試(`index === count`)相反。改為 `collapsed` 明確分支。

**[amendment 2026-07-30: review R9]** 函式簽名加 `x` 與 `bounds`:原本只吃 `y` + 「縫隙取最近 zone」+ pointerup 一律 mutate,等於**在畫面任何位置放開都會把股票搬組**(只要 y 恰好與某群組同高,放在中間 K 線圖上也算)。移動語意是不可逆的,舊行為最壞只是同組換位(可逆),不能無護欄。

**[amendment 2026-07-30: review R5]** `moveCode` 的 `Group` **不從 `@/hooks/useStockWatchlist` import** —— `lib/` 全域零 `@/hooks/` 依賴(grep 實證),改用結構型泛型 `G extends { name: string; codes: string[] }` 保留呼叫端型別。
- `moveCode`:`from !== to` → 來源組 filter 掉 code(**移動語意,user 拍板**);目標組先 filter 再 clamp 插入(`from === to` 時這一步同時完成移除與插入,index clamp 到 `[0, base.length]`)。**其他群組的 codes 不動 → W-1 的多組成員關係在別組保留。**

**新測試**:zone 命中 / 縫隙取最近 / 空 zones 回 null / **折疊 zone → index === count** / **展開的空群組(count=0)→ index === 0** / **x 落在側欄外 → 回 null**;`moveCode` 跨組(來源移除、目標插入位置正確)/ 同組重排 / index 溢出 clamp / 目標組已有該 code 不重複 / 不影響第三組。

## 🔴-12 `frontend/src/components/stock/WatchlistSidebar.tsx` — 群組全列出 + 折疊 + 跨組拖曳 + 搜尋提示(SC-1~4)

**移除**:`activeGroup` state、`GROUP_KEY`(`stock-wl-group`)讀寫、tab 列(`role="tablist"` 整段 `:169-226`)、`unionCodes`、頂部單一輸入框(`:227-242`)、「全部」相關分支(`add` / `remove` 的 `else` 路徑、`onHandleDown` 的 `if (!currentGroup) return`)。

**新增結構**(每個 group 一個 `<section>`):

```
<aside aria-label="自選清單">
  {error 文案}{save.error 文案}
  {groups.map(g =>
    <section data-testid={`wl-group-${g.name}`}>
      <header>
        <button aria-label={`折疊 ${g.name}` | `展開 ${g.name}`}>▾/▸</button>
        <span>{g.name}</span><span>{g.codes.length}</span>
        <button aria-label={`新增到 ${g.name}`}>+</button>
        <button aria-label={`刪除群組 ${g.name}`}>×</button>   ← 文案沿用(既有測試 W-3 靠它)
      </header>
      {adding === g.name && <搜尋框 + 提示列>}
      {!collapsed.has(g.name) && <ul ref>{該組 codes 逐列}</ul>}
      {展開且 codes 空 → <p className="min-h-11">拖曳股票到此</p>}
    </section>)}
  <button aria-label="新增群組">+ 群組</button>   ← 文案沿用
  {movingCode 的 ⊞ checkbox 面板}                 ← 整段保留(W-1)
</aside>
```

- **折疊**:`collapsed: Set<string>` state,初值讀 `localStorage["stock-wl-collapsed"]`(JSON 陣列,壞值 → 空 Set);每次變更寫回。
- **每列**:握把 `aria-label={`拖拉 ${code}`}`(文案沿用)**恆存**(不再有「全部停用拖拉」);`⊞` / `×` / 點列 onSelect 全部沿用,`stopPropagation` 維持(W-5)。
- **`×` 移除**:語意變為「從**該群組**移除」(不再有「全部」下的跨組移除分支)。
- **`+` 新增**:`adding` state 記哪一組展開了搜尋框。輸入框 `placeholder="股號或名稱"`,**右側保留一顆文案「新增」的按鈕**(與 Enter 同一 handler);
  - 提示列 = `searchStocks(input, names, 8)`,逐列 `<button aria-label={`加入 ${code} ${name}`}>`;點擊 → 加入**該組** + 關閉搜尋框 + 清空輸入。
  - Enter / 點「新增」:提示列**有**命中 → 取第一筆;**無**命中 → 用 `input.trim().toUpperCase()` 原樣加入(**W-4 / SC-1c**)。
  - 該組已含該 code → 不動作(沿用現行 `codes.includes` 早退)。

  **[amendment 2026-07-30: review R16]** 「新增」按鈕是 **W-4 明列的兩條路徑之一**,原 spec 的移除清單把 `:227-242`(含該按鈕)整段刪掉,而唯一覆蓋它的兩支既有測試(`:86-100` / `:102-110`)本輪都被判該紅改寫 → 按鈕消失不會有任何測試發現,W-4 被靜默削一半。改寫那兩支時**仍以點「新增」觸發**,Enter 路徑另有測試。零群組 fallback 的搜尋框同樣要有這顆按鈕。
- **跨組拖曳**:`onHandleDown(group, index, e)`;**每次 `pointermove` 都由各 section 的 ref 重算 `DropZone[]`**(section rect + list rect + count + collapsed)**並同時重取 `asideRef.current.getBoundingClientRect()` 當 `bounds`**,`dropTargetFromPointer` 更新 `dragTo: {group,index}` 供**落點高亮**;`pointerup` → `dropTargetFromPointer` 回 `null` → **不發 PUT**;目標與來源相同且 index 相同 → 不發 PUT;否則 `save.mutate(moveCode(...))`。

  **[amendment 2026-07-30: review R17]** `bounds` 的來源必須明訂為 **`asideRef`**(原 spec 加了必填的 `bounds` 卻沒說從哪來)。且 **jsdom 的 `getBoundingClientRect()` 全為 0** → 不 stub 的話 `bounds = {left:0, right:0}`,護欄退化成「`clientX > 16` 一律回 null」,SC-4c 的負向測試在**任何**實作下都會綠(恆真空斷言),而正向的跨組拖曳測試會因所有 section rect 相等(nearest-zone 距離全同)而無法指定目標組。**測試必須 stub 各 `wl-group-*` section 與 aside 的 rect**(先例:`StockIntradayChart.test.tsx:30-33`),且 SC-4c 的負向測試**必附一支同座標序列但落在側欄內會發 PUT 的對照**,證明護欄不是恆真。

  **[amendment 2026-07-30: review R18]** `keydown Escape` 走**與 pointerup 完全相同的 teardown**(移除 `pointermove` / `pointerup` / `keydown` 三個 listener)**並設 `cancelled` 旗標讓任何後續 pointerup 早退** —— 只清 drag state 的話,使用者按 Esc 後放開手指仍會走 pointerup 分支照樣搬組。測試序列固定為 `pointerdown → pointermove(落在另一組) → keydown Escape → pointerup(同座標)` → 斷言零 PUT。

  **[amendment 2026-07-30: review R23]** `⊞` checkbox 面板改渲染在**該列正下方**(不再是所有 section 之後)—— 捲動容器搬到 `<aside>` 且群組全列出後,原位置會落到整個側欄底部、常在可視範圍外,W-1 名義保留但實際難以到達(jsdom 測試抓不到位置問題)。
  - 現行「拖曳中即時 reorder 預覽」的 `displayed` 邏輯移除,改為落點高亮(理由:跨組即時預覽要同時搬兩個 list 的 DOM)。

  **[amendment 2026-07-30: review R5 — 原寫「zone 幾何在 pointerdown 當下算一次(拖曳中 DOM 不重排)」,但那個前提沒有任何約束保證]**:
  - **改成每次 `pointermove` 重算**。N = 群組數(個位數),成本可忽略,而且對捲動與版面變動天然免疫 —— 現行實作本來就是每次 move 重讀 `list.getBoundingClientRect().top`(`WatchlistSidebar.tsx:140,146`),單次計算是**退步**。
  - 明訂**捲動容器 = `<aside>`**(`overflow-y-auto` 從原本掛在唯一那個 `<ul>` 移到 aside;群組全列出後側欄高度不再受單組限制)。
  - 落點高亮**只能用不影響版面的樣式**(border 顏色 / outline / 絕對定位),**禁止插入佔位元素** —— 插入一條落點線就會撐開版面讓 rect 失效。現行 `border-accent` 之所以安全正是因為它只換顏色不改盒模型。
  - 錯誤文案(`save.error` / `error`)的出現與消失也會改變所有 section 的 top;重算即免疫。

- **[amendment 2026-07-30: review R6 — 零群組是真實冷啟動狀態,原 spec 拿掉唯一入口]** `groups.length === 0` 時渲染 fallback 區塊:沿用既有文案「尚無自選,輸入股號新增」+ 一個搜尋框(同項 1 的提示列),送出時 `mutateGroups([{ name: DEFAULT_GROUP, codes: [code] }])` 自動建立「自選」組。**`DEFAULT_GROUP` 常數因此保留不成 dead code**(否則 eslint no-unused-vars 會擋 SC-9)。對應 SC-2b 與白名單 W-16。

- **[amendment 2026-07-30: review R14]** `removeGroup` 的 `onSuccess` 要收斂衍生狀態:`collapsed` 刪掉該群組名(否則 localStorage 累積孤兒名,日後建同名群組會意外呈折疊)、`adding` 若等於該名則清空。

**既有測試逐一標**(`WatchlistSidebar.test.tsx`)

| 測試 | 判定 |
|---|---|
| `:50-55` aside `border-r` / `border-line` | **不該紅** |
| `:59-68` 群組 tab 列 + 全部聯集 | **🔴 該紅** → 改寫為「所有群組 section 同時可見、2330 在兩組各出現一次」 |
| `:70-76` 點 tab 只顯示該組 | **🔴 該紅** → 刪除(tab 概念消失),以 SC-3 折疊測試取代 |
| `:78-84` 點列觸發 onSelect | **🔴 該紅** —— **[amendment 2026-07-30: review R3(a)]** `getByText("2330")` 在全群組同時列出後有 **2 個**節點(GROUPS 的 2330 同屬主力與觀察)→ 拋 multiple elements。與本表 `:59-68` 的改寫描述「2330 在兩組各出現一次」本來就互相矛盾。改法:`getAllByText("2330")[0]` 或 `within(screen.getByTestId("wl-group-主力"))`;**W-5 的語意(點列換股)不變** |
| `:86-100` 群組下新增只加該組 | **🔴 該紅**(改走該組 `+` 鈕 + `placeholder="股號或名稱"`)→ 期望 PUT body 不變 |
| `:102-110`「全部」下新增自動建「自選」 | **🔴 該紅 → 改寫不刪除** —— **[amendment 2026-07-30: review R6]** 原標「刪除,auto-default 已記」是錯的:auto-default 清單裡**根本沒有這一條**,白名單也沒有,等於靜默拿掉既有可用路徑。改寫為「**零群組**時輸入股號 → PUT `[{name:"自選",codes:["2317"]}]`」(fetchMock 的 GET 回 `{groups: []}`) |
| `:112-124`「全部」下移除 = 全組移除 | **🔴 該紅** → 改寫為「該組 `×` 只從該組移除,另一組保留」 |
| `:126-133` 新增群組 | **🔴 該紅(僅前置守衛)** —— **[amendment 2026-07-30: review R3(b)]** `await waitFor(() => getByRole("tab", {name:"主力"}))` 在 `role="tablist"` 整段移除後永遠找不到 → timeout。守衛換 `getByTestId("wl-group-主力")`;**被斷言的 PUT body 與 `aria-label="新增群組"` 不變** |
| `:135-140` 刪除群組 | **🔴 該紅(僅前置守衛,同上)** → 守衛換 `getByTestId("wl-group-觀察")`;PUT body 與 `aria-label="刪除群組 觀察"` 不變 |
| `:142-155` 刪除群組失敗不切 tab | **🔴 該紅**(斷言 tab 的 `aria-selected`)→ 改為 **W-3 修訂後的有實體斷言**:錯誤文案出現、**沒有發第二次 PUT**、該組折疊狀態與展開中的搜尋框(`adding`)不變。 **[amendment 2026-07-30: review R14 — 原改寫「兩組 section 仍在」在任何實作下都成立 = 不可證偽的空斷言]** |
| **`fetchMock` 本身(`:21-28`)** | **🔴 該紅** —— **[amendment 2026-07-30: review R3]** 側欄現在會打 `/api/stock/names`,而 mock 對非 PUT 一律回 `{groups: GROUPS}` → `body.names` 為 `undefined`。需加 `/api/stock/names` 分支;`useStockNames` 與呼叫端也要容得下缺欄位(回 `[]` 不炸)。**[amendment 2026-07-30: review R19 — 分支不能回空表]** 預設分支回**小 fixture** `{names:[{code:"2330",name:"台積電"},{code:"2317",name:"鴻海"}], count:2}` —— 回空表會與同節「名稱命中」新測試及 SC-1a 互斥(空表下名稱命中永遠不成立)。「表為空 → 提示列不出現、Enter 直接加入」由**單獨一支**以 `mockImplementation` 覆寫的測試驗 |
| `:157-163`「全部」停用拖拉 | **🔴 該紅** → 改為「每組每列都有握把」 |
| `:165-180` ⊞ checkbox 切換所屬群組 | **不該紅**(W-1) |

**新測試**:折疊 → 該組列隱藏 + localStorage 落檔 + 重 mount 維持;搜尋提示列(名稱命中 / 代碼命中 / 點擊加入該組 / Enter 無命中走原樣代碼);跨組拖曳 pointer 序列 → PUT body 為 `moveCode` 結果;空群組顯示「拖曳股票到此」;**零群組 → 顯示「尚無自選,輸入股號新增」+ 加入後 PUT 建「自選」組**(SC-2b / W-16);**拖到側欄外放開 → 零 PUT**、**拖曳中按 Esc → 零 PUT**(SC-4c);**刪除群組成功後 localStorage 的折疊清單不留該組名**(R14)。

## 檢附:🔴 / 🟢 / 🔵 commit 切分

| commit | 範圍 |
|---|---|
| 🔵 | 🔵-1、🔵-2(`minuteToX` / `plotWidth` 抽出,測試零改動) |
| 🔴 a | 🔴-3、🔴-4(江波圖 gutter + 價位水平線 + 量刻度靠右;先改測試轉紅再實作) |
| 🔴 b | 🔴-5(BB 預設開 + 一次性升級) |
| 🟢 a | 🟢-6、🟢-7、🟢-8(後端名稱表 + CLI + endpoint) |
| 🟢 b | 🟢-9、🟢-10、🟢/🔴-11 的新增部分(純函數 + hook) |
| 🔴 c | 🔴-12(WatchlistSidebar 改寫:tab → section + 折疊 + 跨組拖曳 + 搜尋) |

self_review_head: b67565e358811542129cd8e62a9acea17cebdb97
