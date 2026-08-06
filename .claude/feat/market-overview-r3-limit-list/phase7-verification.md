# Phase 7 goal 核對 — market-overview-r3-limit-list(2026-08-06)

重讀 brainstorm.md §3(SC gate 含 amendments)後逐條核對;證據皆本日新鮮實跑
(pass count 於 Phase 7 當下重跑取得,非引用歷史輪)。

| SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|------|--------------|--------------------------|------------------|-------------------|
| SC-1 rows 端點 | copycat/server/app.py:1171(route)、copycat/server/breadth_engine.py:259(rows_state)、copycat/market_breadth.py(rows 三欄擴充) | tests/server/test_breadth_routes.py(TestBreadthRowsRest 三態+契約 13 欄)+ test_market_breadth.py — 與 test_verify 合跑 72 passed | evidence/SC-1_rows-first.json / SC-1_rows-ready.json / SC-1_truth-chain.txt(側車真 FinMind,3081 streak=5 真值鏈)| /api/market/breadth(R2 counts 端點)全程 200,家數帶截圖數字正常 |
| SC-2 連板數管線 | copycat/limit_streaks.py:42/67(純函式)、copycat/server/breadth_engine.py:567-798(武裝/掃描/快取)| tests/test_limit_streaks.py 12 passed + tests/server/test_breadth_engine.py 87 passed(restore 不重打 / 換日 / 前緣間距 / 回聲 / 跨午夜丟棄 全覆蓋)| evidence/SC-2_streak-truth.txt(真 EOD 10 交易日實跑 + 6727/4991 逐日鏈人工核對;oracle limitup_all 僅至 07-16 → design R12 備援路徑)| replay four/five + copycat validate 42/42 PASS(evidence/phase5_backend.txt)|
| SC-3 列表畫面 | frontend/src/components/index/LimitListSection.tsx(全檔)、IndexPage.tsx:137 | LimitListSection.test.tsx(收合/表頭九欄/名稱/連板文案/badge/紅綠)— R3 四檔前端合跑 90 passed | 截圖: evidence/SC-3_collapsed.png / SC-3_expanded.png / SC-3_expanded-down-rows.png / SC-3_filtered.png + user 過目(收尾回報列表述)| CorrSection 位置不變(截圖內「相關係數」照常在列表之下)|
| SC-4 篩選持久化 | LimitListSection.tsx(loadFilter/persist)| LimitListSection.test.tsx 持久化 describe(90 passed 合計內)| 截圖: evidence/SC-4_after-reload.png + user 過目(F5 後展開態+勾選保留)| localStorage 其他 key(tab / chart toggles)不受影響 — App.test 28 條既有全綠 |
| SC-5 跳轉 | frontend/src/App.tsx:256、IndexPage.tsx:137 | App.test.tsx「App 漲跌停列表跳轉個股」真鏈 2 條(90 passed 合計內;斷言 aria-selected + /api/stock/state/{code} + main-code 落檔)| 截圖: evidence/SC-5_jump.png(3081 → 個股 tab + 主圖標的)+ user 過目;五檔跳動 = 盤中限定,留 user 盤中確認(窗外降級已依 brainstorm 執行)| 個股 tab 既有 set_main 路徑(App.test 既有 D-16 測試綠)|
| SC-6 失效域隔離 | copycat/server/verify.py(四支注入)、breadth_engine 失敗分類 | tests/server/test_verify.py(injects_all_four + feed_the_real_pipeline touched 斷言;72 passed 合計內)| evidence/SC-6_fail-injection.txt(--verify + VERIFY_BREADTH_FAIL=1:rows 恆 200 stale、/api/txo/snapshot 照常)| fake TXO snapshot 端點於注入下正常(同檔證據)|

Edge cases(brainstorm §4)對應:1 除權息 → test_limit_streaks spread 案例;2 缺日 →
交集出局案例;3 EOD 資料日 → data_end 語意測試群;4 觸及未鎖 → test_market_breadth
touched 案例;5 rows/counts 同源 → rows_state 用 _rows_date(R14 測試);6 算不出顯示「-」
→ LimitListSection streak null 文案測試。

結論:6/6 SC PASS(SC-3/4/5 的 user 過目層 = 收尾回報請 user 確認;SC-5 五檔跳動
另留盤中)。無 FAIL 項,無分流敘述。rollbacks = [](零回退)。
