# PLAN:閃電梯部位列 + 未實現損益 + 含成本打平價(v2)

依 design.md v2;`[amendment 2026-08-05: impl-spec review IS-1~IS-10 全 accepted 整併]`。
TDD 順序:lib 紅→綠 → 測試基建 🔵 → 元件 characterization 🟢 → dimmed 移欄 🔵 → 元件紅→綠。

## 0. 顯示契約(IS-1/IS-4 拍板,測試字串以此為準)

- **單位**:`fmt()` 吃毫元。打平 = `fmt(snapBreakEven(beMilli, qty))`;**均價 = `fmt(Math.round(avg_price * 1000))`**(avg_price 是元 — types.ts:100;直接 `fmt(avg_price)` 會印出 0.1,IS-1)。
- **kind 標籤**:複用本檔既有 `TRADE_KINDS` 查表(現股/融資/融券/無券),未知 kind 顯示原字串、排最後 — 不長第三份字彙(IS-4;`KIND_TEXT` 是部位 tab 的縮寫體系,不混用)。
- **文案定案**:多方第一行 `現股 2張 @100`;空方第一行 `融券 空2張 @100`;第二行 `打平 100.5`;pnl 右緣 `+3,284` / `-6,864` / `—`。
- **testid 契約(IS-2)**:部位條 section `data-testid="ladder-position-bar"`,逐 kind 列 `data-testid="ladder-position-row"`;測試一律 `within(getByTestId(...))`。

## 1. `frontend/src/lib/ladder-position.ts`(🟢 新檔)

- 常數:`FEE_BASE=0.001425` / `SELL_TAX=0.003` / `SHORT_BORROW=0.0008` / `FEE_DISCOUNT_DEFAULT=1.8`。
- `feeRate(discount)` = FEE_BASE × discount / 10。
- `positionEcon(qty, avgPrice, lastMilli, discount, kind): PositionEcon` — 完整口徑與五組手算例見 design「SC-2/SC-3」節;`|qty|` 計費;`avgPrice <= 0 || null` → 全 null;`lastMilli <= 0 || null` → pnl null(BE 照算);空方 kind==="short" 才加 b。
- `snapBreakEven(beMilli, qty)`:qty>0 → snapUp、qty<0 → snapDown。
- `avgTickOf(avgPrice): number` = `snapNearest(Math.round(avgPrice*1000))`(IS-5:avg 標記 key 單一定義,lib 內給、元件不自算)。
- `clampDiscount(raw: string | number): number | null`。
- `secPositionsOf(positions, code)`:filter sec/code/qty≠0;排序 cash→margin→short→未知殿後。
- 紅測試 `ladder-position.test.ts`:design 手算例五組逐字;feeRate;clampDiscount("" / "abc" / "0" / "-1" / "11" / NaN → null;"1.8" / 10 → 值);snapBreakEven 方向;`avgTickOf` 跨級距例(99.97 → 100_000,IS-5);secPositionsOf;D14/D15 案例。

## 2. `frontend/src/lib/constants.ts`(🟢 一行)

- `/** 手續費折數 — components/stock/PriceLadder.tsx */`+`export const FEE_DISCOUNT_KEY = "copycat-fee-discount";`(IS-10 註解格式)。

## 3. `frontend/src/components/stock/PriceLadder.test.tsx`

- 🔵 基建:抽 `mockCapitalFetch(extra?)` helper(預設 orders 空 + positions 空);既有全部 mockFetch 呼叫點改走 helper;市價單列 describe 補掛。既有斷言零改動、全綠。
- 🟢 characterization(IS-7,在 dimmed 移欄 🔵 之前):斷言 dimmed 列 row 容器 class 含 `opacity-35`;移欄後同測試改斷言三個 grid 欄皆含、row 無(此測試屬「該變」,兩段都明寫)。
- 🟢 紅測試(§0 字串逐字):
  - 部位條:`ladder-position-bar` 內文字(`現股 2張 @100`、`+3,284`、`打平 100.5`);空手 `queryByTestId` null;多 kind 兩列 `ladder-position-row`;空方列 `融券 空2張 @100` 與負 pnl 色;avg null → `2張 @—` 且打平 `—`;last null → pnl `—` 且打平照顯示照畫標記(D15)。
  - 標記:be/avg testid 落正確 priceMilli 列、title 帶 kind(`打平(現股)`);dimmed 列標記 class 不含 opacity-35 且自帶 opacity-100;**BE 超出梯域(avg 貼近漲停,snapUp 後 > upper)→ `queryAllByTestId("ladder-be-mark")` 空 且 部位條打平數字照顯示**(IS-3)。
  - 折數:改 "0.5" → 重算斷言 + `localStorage.getItem("copycat-fee-discount")` **字面 key** 斷言(IS-10);非法值用 number input 可承載的 "0" / "-1" / "11"(IS-6;"abc" 留 lib 層)→ 不寫入且計算沿用舊值;空手態改折數可寫入(D1);**改折數不影響張數 input 值**(IS-8)。
- fixture helper `capitalPosition(overrides)`(仿 capitalOrder)。
- RightRail.test.tsx **不改,跑綠確認**(其 positions fixture 2330 會讓部位條在閃電 tab 渲染 — IS-9 明確確認項)。

## 4. `frontend/src/components/stock/PriceLadder.tsx`

- 🔵(characterization 就位後):`r.dimmed` 的 `opacity-35` 從 row 容器移到三個 grid 欄。
- 🟢:
  - `useCapitalPositions()` + `secPositionsOf`;折數 state `{raw, value}` + localStorage(初值 `clampDiscount(getItem ?? "") ?? FEE_DISCOUNT_DEFAULT`)。
  - 武裝列第二行:折數 input(`aria-label="手續費折數"`,w-12,step 0.1)**帶可見後綴「折」小字與張數框區隔**(IS-8:相鄰同型數字框,一個是真錢張數 — 必須可辨識);寬度不足時折數移到第二行末獨立小段。
  - 卡片底部部位條 section(`ladder-position-bar`):逐 kind 兩行(§0 文案;第二行色點對應標記色)。
  - 標記:`Map<number, string[]>` be(key = snapBreakEven)/ avg(key = avgTickOf)兩份;row `relative` + `absolute inset-y-0 w-0.5 pointer-events-none opacity-100`,be `left-0 bg-warn`、avg `left-1 bg-ma20`,title 帶 kind,testid 依 §0。
- token 檢查:`bg-warn`(--color-warn 已存在)、`bg-ma20`(index.css 確認;無則選既有 semantic token,不寫 palette 字面色)。

## 5. 驗證

- gate:frontend `npm test -- --run` / `npx tsc -b` / `npx eslint src`;backend 四項照常。
- 真實環境取證(IS-9 擇一寫定):**vite dev + claude-in-chrome**,以瀏覽器端 fetch override(claude-in-chrome `javascript_tool` 對 `/api/capital/positions` 注入假回應)或 vite dev proxy bypass 腳本餵假部位(cash 2張@100 + short 空2張@100)截圖對照 SC-1/SC-4;腳本(若需)放 scratchpad 不進版控;真持倉 = user 盤中過目。盤中不起第二台連 TC4 的後端。
