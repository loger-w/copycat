# Current State — 個股頁現價顯示(mod/stock-price-prominence)

日期:2026-08-04(baseline commit:master 同步點,分支 mod/stock-price-prominence)

## 現況

個股頁現價顯示在 `frontend/src/components/stock/StockPage.tsx:86-102`,
`data-testid="page-quote"` 的 `<span>`:

- 字級 / 字重:`font-mono text-lg`(**與左側股名 h2 的 `text-lg font-bold` 同字級,
  且股名有 bold、現價沒有 → 現價視覺上反而比股名弱**,這就是 user 覺得不明顯的根源)。
- 顏色語意(limitState 三態):
  - 漲停(`limit === "upper"`)→ `rounded bg-bull px-1.5 text-white` 整塊反白
  - 跌停(`limit === "lower"`)→ `rounded bg-bear px-1.5 text-white`
  - 未觸價(`limit === null`)→ 依 chg 正負 `text-bull` / `text-bear` / `text-ink`
- 內含漲跌 %:`<span className="ml-1 text-xs">`(fmtPct)。
- `last === null` 時整塊不渲染。
- 位於 `<header className="flex flex-wrap items-baseline gap-3">`,同列還有:
  股名+代號 h2、無資料/回補中 badge、股期價差、加入自選按鈕、總量/昨量(ml-auto)。

## Caller map

| 引用點 | 內容 | 影響 |
|---|---|---|
| `StockPage.tsx:86-102` | 唯一渲染點 | 改動目標 |
| `StockPage.test.tsx:186-206`(3 條) | 斷言 className 含 `bg-bull`+`text-white` / `bg-bear`+`text-white` / `text-bull` 且無 bg-* | 不斷言 `text-lg` → 字級改動**不會**讓既有測試紅 |

無其他檔案引用 `page-quote`;`text-lg` 在該檔僅此一處與 h2 一處。
動態用法(template string / 字串拼接)grep 無命中。

## Baseline

`npm test`(frontend/):**66 files / 914 tests 全綠**,10.4s(2026-08-04 實跑)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 現價字級 | `text-lg`(≒ 股名) | 加大為頁面最醒目數字(`text-3xl` + `font-semibold`) |
| 漲跌 % | `text-xs` | 同步放大一級(`text-sm`;非等比 — 主數字/% 比例刻意拉開,見 change-spec SC-2) |
| 顏色 / 漲跌停反白 | 三態如上 | **完全不變** |
| signature / API | 純 className 改動 | 無 API / props 變更,無 migration |
| backward compat | — | 不涉資料 / 契約;純視覺,可單 commit revert |
