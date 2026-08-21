# verification — mod/txo-backfill-progress-tape0(R9)
## 自動化(2026-08-21 23:4x):pytest 2895 passed(baseline 2887 → +8)| ruff / pyright 0 | copycat validate 42/42 | vitest 136 files / 2528 passed(+18)| tsc / eslint 0 | react-doctor:新增 finding 0(tape effect 的 set-state-after-await 與既有 instrumentKey effect 同型,行內抑制對位;no-pass-data-to-parent 為 spec 否決 state 上提後的刻意抑制)
## SC
- SC-1 engine attempt/attempts_max/phase + _mark_changed:attempt 1 / 2 交握點、degraded、ConnectionError phase degraded、重試期間 phase=backfilling 推播(V3 mutant 紅)PASS。
- SC-2 ConnectionBadge「回補中(第 n 次)」(n>1)、tone 不變、斷線優先 PASS;App header 接線 PASS。
- SC-3 `/api/stock/state?tape=0`:ticks [] + tape_omitted、其餘鍵全等、set_main 仍呼叫、`tape=abc` 全量;`snapshot(tape=False)` 跳過展開(_ExplodingTick)PASS。
- SC-4 useStockStream tape(ref 化、預設無 query、false→true 補打一次、WS 閉包讀 ref、StrictMode)+ StockPage onViewChange(掛載一次 + 切換)+ App 接線 PASS。
- SC-5' 真環境:merge 後重啟 8721 → `curl -w size_download` 全量 vs `?tape=0` 對照(見收尾回報);TXO 重試態不可刻意觸發 → **user 過目**(回補中若重試會顯示第 n 次)。
## 白名單 W1(五欄只在 attempt 結束出現;例外路徑 phase 同步)/ W2 / W3(無參數位元不變)/ W4(六個觸發;CR1 不變;stateUrl 唯一)/ W5(view 留 StockPage,多一則通知)。
抽 2 未改:GroupGridView.test 綠;test_stock_routes 其餘綠。
## Migration 無。self_review_head = 見 change-spec.md 末尾
