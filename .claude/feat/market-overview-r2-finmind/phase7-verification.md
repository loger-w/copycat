# Phase 7 verification — market-overview-r2-finmind(2026-08-06)

重讀 brainstorm.md SC 節後逐條核對;targeted 新鮮跑:backend 8 檔 125 passed、
frontend 4 檔 46 passed(12:0x;全套見 automated-verification.md:pytest 2159 /
vitest 1410 / ruff / pyright / validate / tsc / eslint 全綠)。

| SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 家數對照一致 | copycat/market_breadth.py(compute_breadth / assemble_universe / dedup_sector_map)、copycat/market.py(limit_up_milli :95 / limit_down_milli :103 附近) | tests/test_market_breadth.py::test_breadth_parity(neigui 全管線 oracle,盤中錄 1954 檔全等、limit 桶 21↑3↓)+ 全檔 29;tests/test_market.py 13 — 合計於 125 passed 內 | evidence/SC-1_live-parity.txt(盤中 11:47 三方對照:neigui 現碼 vs copycat 十格全等;vs 側車 REST max diff=3 ≤ 相鄰輪變動量)+ SC-1_sidecar-first.json。註:對照對象為 neigui 現碼即時計算(neigui panel 未在跑),數字層等價 | tests/server/test_oi_levels.py(finmind_token 抽出後 21 綠,於 125 內) |
| SC-2 重啟序列不歸零 | copycat/server/breadth_engine.py(_restore / _save / _append,trade_date 三分法) | tests/server/test_breadth_engine.py(restore+首輪、T+1 不截短、畸形點防禦等,全檔 35 於 125 內) | evidence/SC-2_restart-series.txt(側車真重啟:4 筆 → restore 逐位元組同 + append = 5 筆)。prod 首次啟動後的自然驗證記收尾回報 | 落檔隔離:data/market-verify-real/ 不碰 prod data/market/ |
| SC-3 失效域隔離 | copycat/server/breadth_engine.py(stale/degraded/退避)、copycat/server/app.py(_boot 邊界 + 三態 route)、copycat/server/verify.py(fake + VERIFY_BREADTH_FAIL) | tests/server/test_breadth_routes.py(三態 + 隔離)、test_breadth_engine.py(保前值/退避/quota)、test_verify.py(fake 語意 + 注入)— 於 125 內;vitest BreadthBand stale 態(46 內) | evidence/SC-3_fail-injection.txt(注入 + runtime 翻轉:counts 保前值 + stale + 恆 200;txo/health/ws 不受影響)+ SC-3_edges.txt。側車 /api/index/state 503 = index_source None 設計,非 breadth 波及(對照組證明) | /api/txo/snapshot、/api/health、既有 vite dev(5173)未受打擾 |
| SC-4 UI 畫面可指認 | frontend/src/components/index/BreadthBand.tsx / AdvanceDeclineChart.tsx / IndexPage.tsx:插入中段、App.tsx、hooks/useBreadth.ts | vitest 46 passed(BreadthBand 11 / ADL 10 / useBreadth 10 / IndexPage 15) | 截圖: evidence/SC-4_full-page.png + SC-4_breadth-band.png + SC-4_adl-chart.png(盤中真數據:兩列五格順序、紅/綠底、戳記、0 軸、末值 -266;console 零新增 error)+ user 過目 | IndexPage 既有 12 例照綠;App.test 未動照綠 |
| SC-5 文件債 | CLAUDE.md §0 例外段(:18)/ 結構表(:93-100)/ §1 secret 段(:148) | (文件類,無測試)grep 新鮮跑:`FINMIND_TOKEN` 2 處(:96 結構樹 + :148 secret;SC amendment 已核)、`全市場廣度` 2 處含 §0 例外段 | anytime — grep 即證據(上方輸出) | — |

失敗分流:無 FAIL。

殘項(不阻塞,收尾回報列出):
1. SC-1 的「與跑著的 neigui panel 畫面同分鐘截圖」層未做(panel 未在跑);數字層已以
   neigui 現碼即時對照等價驗過。若 user 要求畫面層,任一交易日兩邊同開即可補。
2. SC-4 user 過目(雙層之二)待 user。
3. prod 8721 實測未在跑 — breadth 上線待 user 啟動 prod server(啟動即含本輪 code,
   無「盤後重啟」問題);屆時順手目視:綜合 tab 家數帶 + 指數圖並置、/api/index/state 正常。
