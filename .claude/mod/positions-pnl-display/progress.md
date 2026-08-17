# progress — mod/positions-pnl-display

plan: `.claude/mod/positions-pnl-display/change-spec.md`(對照 `current-state.md`)
branch: `mod/positions-pnl-display`(自 master `cdaee027`)

| # | 包 | 內容 | commit 範圍 | review |
|---|---|---|---|---|
| 0 | baseline | pytest capital 390 / vitest 2100 全綠 | — | — |
| 1 | spec review | round-1 17 findings 全 accepted(P0×1 TradeKind caller)→ amendment;round-2 限縮 7 條全 accepted(P1×2 useFeeDiscount 矛盾 / out-of-scope);退出無 P0 | — | change-spec-review-round-1/2.json |
| 2 | 包 A(dispatch opus) | 🔵 lib 搬家(pnl-format / trade-kinds / fee-discount)+ 🟢 後端 stock_code_of + positions code + 🟢 types/fixture | 2aa84d28..8ab4f8ac(4) | main 機械快篩 diff OK;gate:vitest 2100 / pytest 392(子樹)/ ruff / pyright 0 / tsc / eslint 綠;fixture 實補 9 檔(spec 列 10,`:29` 是委派非 literal) |
| 3 | 包 B(dispatch opus) | 🟢 useFeeDiscount + position-summary lib / 自選 chip SC-2 / header SC-3 / 群組卡 SC-4 / API mini 案補 | 1dc5b18c..3aa2f426(9;4 對 red/green) | vitest 2148 / tsc / eslint / doctor 零新增;memo lock mutation 實證 |
| 4 | 自評 review(2 lens opus) | C-1/SPEC-1 P1 期貨態 header 現股段吃合約價(CONFIRMED)+ P2×3 | code-review-round-1.json | fix 波 dispatch 中 |
| 5 | 真實環境(側車 8721 + vite 5173) | SC-1 API code 反查(CDFI6/QFFI6→2330,EE1I6→null)✓;SC-2/3/4 截圖 evidence/;SC-3 同瞬 DOM 對照 header==ladder(-12,436/+24,789)✓;ROW_H 52 全列 ✓;W-5 實測 3 observer 15s 窗 1 請求(319610/334619/350616 ms)✓ | — | fix 後補期貨態 header 截圖 |
| 6 | fix 波(dispatch opus) | C-1 [red]04ed8532→[green]3b83d08c;C-2 afc087b6;C-3 5675063f;TEST-2 77810ab3 | 04ed8532..77810ab3(5) | 主 session 快篩增量 OK;全套 gate 綠(verification.md) |
| 7 | 期貨態 header 真機反證 | 合約 CDF:202608 主圖 1180 / 側欄 1190 → 現股段 +17,466 = positionEcon@1190 | — | evidence/SC-3-header-contract-state.png |
