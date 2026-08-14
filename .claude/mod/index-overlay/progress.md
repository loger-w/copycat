# progress — mod/index-overlay

對應 spec:`.claude/mod/index-overlay/change-spec.md`(現況:`current-state.md`)

## 計畫(dispatch 包,序列)

- 包 B(🔵 前端 refactor):stock-intraday-svg LEVEL_STROKE/FILL 搬家 + overlayLines 簽名放寬;StockIntradayChart import;MarketChart props 重塑;MarketPane 對齊。
- 包 A(🟢 後端):app.py GET /api/index/overlay + test_index_routes ×5。
- 包 C(🟢 前端):index-chart-svg 擴欄(avgLine/toY/rightEdgeLabels)+ 測試;useIndexOverlay + 測試;MarketChart IntradayChart 改造 + MarketChart.test。

順序 🔵 → 🟢(本輪無 🔴);包間序列(B 與 C 同動 MarketChart.tsx 不互斥)。

## Ledger

- 2026-08-14 baseline 全綠(pytest 2673 / vitest 1868)。spec review round-1:P0×2 P1×5 P2×4 全採納;P0-2 user 拍板「域外疊線=右緣掛牌」。
- round-2 限縮輪:新 P0×2(build_period 誤讀 / 堆疊半套)+ P1×4 + P2×4,全採納 reviewer 處方修畢(JSON 落檔 round-1/2);無第三輪(修復 = reviewer 自身處方,main session 已對 bars.py 逐行核實)。spec 收斂。
- 包 B(🔵×2 commit)完成:LEVEL_STROKE/FILL 上移 + overlayLines 簽名放寬 / MarketChart props 重塑;觸及範圍 838 tests 綠、tsc/eslint 0;main 快篩 diff PASS。
- 包 A(🟢 red b3927783 → green)完成:GET /api/index/overlay(build_period 鍵 IX0001|L);全量 pytest 2679 passed;main 快篩 diff PASS。
- 包 C(🟢×3 對:ca857a69/5e293b0f、f67592d0/8009b806、c90d266c/1494b302)完成:幾何層 avgLine/toY/rightEdgeLabels/outOfDomainLevels、useIndexOverlay、IntradayChart 改造 + MarketChart.test ×10;全套 vitest 114 檔 1891 passed(baseline +23 = 新增數);tsc/eslint 0。T2 red 為 resolve 層紅,以 mutation 驗證非 vacuous(refetchInterval 改恆 false → 2 條斷言紅 → 還原綠)。實作期決策 5 條已補 spec [phase-3 補註];localYmd 兩份重複記下次處理。
- §5 自評:correctness lens 0 findings;whitelist lens W-1~W-14 全 PASS + P2×3(G-1 槽共用無機驗 / G-2 error 態 toggle 死鎖(行為級)/ G-3 全 null 反灰零覆蓋)全 accepted;fix 波 2 commits(G-1 mutation 驗證有牙;G-2 紅先行)。self_review_head=1bcc7005。
- §6 自動化全綠:pytest 2680 / vitest 1894 / ruff / pyright / tsc / eslint / react-doctor 零新增。
- §6 真實環境:側車(fake index/OTC,port 8721,neutralize+隔離)curl happy/partial 剔除/regression ×2;UI 截圖 dispatch 5/5 PASS(SC-1/2/3/4/6),console 零新增 error。證據 evidence/ 齊。
- §7 對照表落 verification.md;check_feat_tags PASS(12 commits)。收尾中。
