# current-state — mod/ladder-pills-avgpct(R6 個股頁兩件小 UI)

來源:batch2 spec §2 R6(user 撰寫,/auto 預核准)。基底 master 0242c9c1(2026-08-17 重 grep)。
Worktree `.claude/worktrees/ladder-pills-avgpct`,artifact 主 tree `.claude/mod/ladder-pills-avgpct/`。

## (a) 閃電梯交易別 select → 四顆 pill
- `PriceLadder.tsx:39-45 TRADE_KINDS`(cash/margin/short/daytrade_sell;「無券」= daytrade_sell)、`:52 kindLabel`、
  `:338 buyLocked={tradeKind==="daytrade_sell"}`、`:392-407 <select aria-label="交易別">`(受控 tradeKind;RightRail 經
  props 上提 :146-149,無 props 用內部 state)。onChange 呼叫 `touchIdle()`(R5 後 = `arm.touch`)。
- 資料流 types.ts → useCapital.ts → capital_api.py → mapping.py sFlag:**全鏈不動**。
- pill 樣板:`StockPage.tsx:189-208`(aria-pressed + `border-accent text-accent` vs `border-line text-ink-dim hover:text-ink`)、
  `GroupGridView.tsx:250-260`(容器 `role="group"` + `aria-label`)。
- Caller(測試):`getByLabelText("交易別")` 出現在 App.test:328/345、RightRail.test:192/211/258/261/363/486/561、
  StkfutLadder.test:169、PriceLadder.test:401/1033。**存在性 / 缺席斷言**(容器沿用 `aria-label="交易別"` 於 role=group →
  仍命中)不該紅;**`fireEvent.change` + `.value` 兩處該紅**:PriceLadder.test:401、RightRail.test:258-261。

## (b) 自選群組列平均漲幅
- `WatchlistSidebar.tsx:294-333 sectionHeader({label,count,collapsed,listId,onToggle})`:順序 摺疊指示 → 組名 → 檔數;
  呼叫點 未分組 :578(不傳)/ 群組 :621(傳 avgPct)。`quotes[code]`(props,`WatchlistQuote{p,chg_pct,...}`,ref 與 p 互斥)。
- 顏色三態同 stockRow :418-431 / GroupGridView QuoteCell :73-79(>0 bull / <0 bear / 0 或 null ink-dim);`fmtPct(lib/format.ts:24)`。
- 測試:WatchlistSidebar.test.tsx:570-620 標題列視覺 describe;fixture `QUOTES`(:78)/ `quotesWith`。
- 白名單:群組展開收合 / 全部展開 / 底色帶 / 檔數 / 上限 50 文案 / 拖曳排序(PR #48)不變;未分組列無平均。

## 分級:兩件皆 S(各單檔 + 各自測試檔;無對外 API / 無 migration)→ spec review 0 輪、主 session 直做(2026-08-11 制)。
