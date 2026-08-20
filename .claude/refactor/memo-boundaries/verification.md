# Verification(refactor/memo-boundaries,2026-08-20)

## 自動化 gate(全 PASS)

| Gate | 結果 |
|---|---|
| `npm test`(frontend/) | **134 檔 2340 passed**(baseline 2323;+17 = characterization 4 + 計次 lock 與守門 13) |
| `npx tsc -b` / `npx eslint src` | PASS |
| `npx react-doctor@latest --scope changed --no-telemetry` | 10 檔,No issues found(零新增) |
| 後端 | N/A:diff 零 .py(純 frontend/src) |
| check_feat_tags | 🔵×4 [refactor] / 🟢×5 [lock](含 fix 波),三類分明 |

## 行為不變(refactor 核心紀律)

- 行為 lens 結論 **PASS**:三步 memo deps 逐項對照完整;上游 hook(useStockStream /
  useIndexStream / useFuturesStream / useRiver)+ applyTick 全 immutable(memo 不會讀舊參照
  凍畫面);readout(cursor 依賴)留 memo 外;RiverPanel useMemo 上提早退前、null 分支安全。
- 既有 2323 條測試零改動全綠(唯一例外:無 — 沒有任何既有 assertion 被改)。
- S3 前置 hover characterization 先拍現狀再動(R1 的 P0 守門),refactor 後仍綠。

## 可量化改進(計次,evidence/baseline-render-counts-S{1,2,3}.txt)

| 邊界 | 改前 | 改後 |
|---|---|---|
| 停個股 tab,期貨推播 ×2 → PriceLadder 重繪 | +2(每 tick +1) | **+0** |
| 停台股綜合 tab,期貨推播 → rail 葉子重繪 | +4(每 tick +2) | **+0** |
| 江波圖 hover ×3 → buildOverlayGeometry | +3 | **+0** |
| 單腿 tick → 對照腿幾何 / 並排卡重繪 | +1 / 三卡全重繪 | **+0 / 僅該卡** |
| 重疊開啟,期貨 tick ×3 → 疊圖幾何 | +3 | **+0** |
| 真變更(分鐘點 / 該腿 tick) | +1 | +1(該動的照動) |

Mutation 抽驗(全部 Edit 成對還原,無殘留):拔 memo(RightRail)/ memo(RiverCard)/
OverlayCard useMemo → 對應計次案紅;deps 缺項 mutant(去 accum / 去 stockCode / 去
futProd / entries 去 legs / deps=[] / deps 加 cursor)→ 對應內容或計次案紅。

## 殘留預期(plan R13/F5;真 trace 對照以此為準)

- 期貨 tab 的 rail 仍隨 futProd 10Hz、個股 tab 的 rail 仍隨 accum 每 tick(正確行為)。
- 江波圖 hover 仍重跑 RiverOverlay render body(timeTicks / polyline 字串重組)——
  只有幾何被 memo 擋住;收斂 polyline 留 next-time。
- OverlayCard 收益僅在「重疊」toggle 開啟時(預設關;evidence 檔已記 toggle 狀態)。

## 真實環境層

- 驗證窗口:真 tick trace(DevTools performance)= 夜盤期貨或次一交易日盤中,prod build
  (`npm run preview`)分頁對照 scripting 佔比;量測當下 preview/後端未跑(14:27 日盤已收)
  → 降級策略生效:計次測試 + user 過目「畫面與 refactor 前完全一樣」(閃電梯下單、
  江波圖 hover 讀值列、加權/櫃買重疊圖三處)。
- 動機核對:handoff R6 的放大因子(每則 WS 全樹 re-render 無 memo)已在三個邊界歸零
  (跨流串擾),殘留均為「該動的本來就要動」。
