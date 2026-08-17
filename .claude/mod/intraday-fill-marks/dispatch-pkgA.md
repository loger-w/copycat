# Dispatch 包 A — lib 層(🔵 ymdOf + 🟢 fill-marks.ts + 🟢 useChartToggles.fills)

你是 implementer(fresh context)。repo:`C:\side-project\copycat`,分支 `mod/intraday-fill-marks`(已切好,直接在主 tree 工作,**不要**開 worktree、不要 switch 分支)。前端在 `frontend/`(npm 指令在該目錄下跑)。

## 必讀(先讀再動手)
1. `C:\side-project\copycat\.claude\mod\intraday-fill-marks\change-spec.md`(規格;本包只做 SC-1、SC-2 與 §5 diff 表的 `ladder-lots.ts` / `fill-marks.ts` / `useChartToggles.ts` 三列 + 對應測試列;含 `[amendment]` 段一律以 amendment 為準)
2. `C:\side-project\copycat\.claude\mod\intraday-fill-marks\current-state.md`(現況與行號)
3. 專案 skills:`C:\side-project\copycat\.claude\skills\frontend-conventions\SKILL.md`(風格)、`C:\side-project\copycat\.claude\skills\frontend-testing\SKILL.md`(vitest 慣例)
4. 既有樣板:`frontend/src/lib/ladder-lots.ts`(+ `.test.ts`)、`frontend/src/lib/chart-extreme.ts`、`frontend/src/hooks/useChartToggles.ts`(+ `.test.ts`)、`frontend/src/lib/stock-accum.ts::minuteKey`、`frontend/src/lib/stock-intraday-svg.ts::minuteToX`、`frontend/src/lib/futures-ladder.ts::futExchangeContract`、`frontend/src/types.ts::CapitalOrder`

## 本包範圍(只動這些檔)
- `frontend/src/lib/ladder-lots.ts`(🔵 新增 `export function ymdOf(d: Date): string`,`ymdWindow` 改用它;輸出逐字不變)+ `frontend/src/lib/ladder-lots.test.ts`(ymdOf 2 案:補零、跨月末)
- `frontend/src/lib/fill-marks.ts`(新;SC-1 全部匯出)+ `frontend/src/lib/fill-marks.test.ts`(新;SC-1 驗證方式欄列的每一案)
- `frontend/src/hooks/useChartToggles.ts`(SC-2:`fills: boolean` 必填、`DEFAULTS.fills = true`、**不 bump TOGGLES_VERSION**,註解沿 `vp` 條說明免 bump 理由)+ `frontend/src/hooks/useChartToggles.test.ts`(SC-2 新兩案;既有 `:19` DEFAULTS 與 `:143-150` 整包比對補 `fills: true` — 這兩處是**事前標記該紅**,先跑紅再改)
- tsc 層該紅四檔(spec §5 [R1]):`frontend/src/components/index/MarketChart.test.tsx:40`、`components/index/MarketPane.test.tsx:40`、`components/index/MarketPane.size.test.tsx:73`、`components/stock/StockIntradayChart.variant.test.tsx:49` 的 `const TOGGLES: ChartToggles = {…}` 各補 `fills: true`(否則 `npx tsc -b` 紅)。**不動這四檔的其他內容。**
- **不動** `StockIntradayChart.tsx` / `CardIntradayChart.tsx` / `GroupGridView.tsx` / `StockChart.tsx`(包 B)。後端 `copycat/` 零改動。

## `fill-marks.ts` 介面(照 SC-1;型別要能被包 B 直接 import)
```ts
import type { CapitalOrder } from "@/types";
import type { XWindow } from "@/lib/stock-intraday-svg";  // 若 XWindow 未 export,改吃 {start:number; end:number} 結構型別
export type FillSide = "B" | "S";
export interface FillPoint { minute: number; priceMilli: number; side: FillSide; qty: number }
export interface FillMark extends FillPoint { x: number; y: number }
export interface FillMarkStyle { halfW: number; height: number; halo: number }
export const FILL_MARK: FillMarkStyle = { halfW: 3.5, height: 6, halo: 1 };
export const EMPTY_FILLS: readonly FillPoint[] = [];
export const EMPTY_MARKS: readonly FillMark[] = [];
export interface FillDates { today: string; yesterday: string }
export function fillDates(todayYmd: string): FillDates;  // 解析 YYYYMMDD 減一日(用 ymdOf 回格式)
export function fillPoints(orders: readonly CapitalOrder[] | undefined, key: string | null, dates: FillDates, excludeUnit?: string): readonly FillPoint[];  // key null → EMPTY_FILLS
export function fillsByCode(orders: readonly CapitalOrder[] | undefined, dates: FillDates, excludeUnit?: string): Map<string, readonly FillPoint[]>;
export function stkfutFillKey(prod: string, ym: string): string | null;
export function clampFillX(x: number, w: number, style?: FillMarkStyle): number;
export function fillTrianglePoints(cx: number, tipY: number, side: FillSide, style?: FillMarkStyle): string;
export function projectFills(fills: readonly FillPoint[], geo: { toY: (p: number) => number; yDomain: readonly [number, number] }, w: number, xw: { start: number; end: number }): readonly FillMark[];
export function fillsAtMinute(fills: readonly FillPoint[], minute: number): readonly FillPoint[];
export function fillLabel(points: readonly FillPoint[], fmt: (priceMilli: number) => string): string;
```
語意細節(過濾條件、元→毫元換算、加權合併、排序、零筆回 EMPTY 常數、窗外 / 域外不畫、文案格式)**全依 SC-1 / SC-4 / AD-2 / AD-4 / AD-6 / AD-7**;檔頭 docstring 寫明「近似版:每張委託一點(最新事件時間 × 均價)」與 `aggregateLots` 的差異(本函式吃 avg_fill_price/time,梯吃 price)。註解風格沿 `ladder-lots.ts`(解釋為什麼,不重述 code)。

## TDD 與 commit 規則(鐵則,逐條照做)
- 順序:🔵 先(ymdOf)→ 🟢。每個 SC:先寫紅測試 commit → 再實作到綠 commit。
- commit subject 格式(tag 在 subject,body 註記不能代替):
  - 紅:`🟢 test(frontend): add failing test for SC-1 [red]`
  - 綠:`🟢 feat(frontend): implement SC-1 [green]`,body 註 `red→green for <red-sha>`
  - 🔵:`🔵 refactor(frontend): extract ymdOf from ymdWindow [refactor]`(其測試同 commit 可)
  - 該紅既有測試的 assertion 更新(useChartToggles 兩處、tsc 四檔)併入對應 SC-2 的 `[red]` commit(它們是事前標記的預期變更)。
  - 一個 `[red]` 只配一個 `[green]`;三類 emoji 不混 commit。
- **禁止**:`.skip`、砍測試、改非事前標記的 assertion、mock 掉真依賴、`try/catch` 吞錯。
- 觸及範圍 gate(每包尾必跑,在 `frontend/`):`npx vitest run src/lib/fill-marks.test.ts src/lib/ladder-lots.test.ts src/hooks/useChartToggles.test.ts src/components/index src/components/stock/StockIntradayChart.variant.test.tsx` + `npx tsc -b` + `npx eslint src/lib/fill-marks.ts src/lib/ladder-lots.ts src/hooks/useChartToggles.ts`。全綠才回報。**不要跑全套 npm test**(main session 波尾親跑)。
- 既有測試若紅且**不在**該紅清單 → 停下,不改 assertion,回報哪個測試與你的判斷。

## 回報格式(純文字)
1. 逐檔改了什麼(1 行/檔)
2. `git log --format="%h %s" master..HEAD` 全文貼出(自檢 tag 規則)
3. gate 指令與各自 exit code / 測試數字
4. 未決或偏離 spec 之處(若無寫「無」)
