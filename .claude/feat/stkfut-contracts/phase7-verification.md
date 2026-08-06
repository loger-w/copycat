# phase7 verification — stkfut-contracts(HEAD e8f54009)

fresh 證據:六 gate 全綠(pytest 2319 / vitest 1556(finding 修後)/ ruff/pyright/tsc/
eslint 0;validate 42/42);SC-4/5/6 截圖 + 幾何量化交叉。

| SC | 實作 | 自動化測試 | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 合約發現 | tc4.list_stock_futures/stkfut_catalog/route | test_tc4_stkfut 9 / test_stkfut_catalog 8 / test_stkfut_routes(價差反例雙鎖) | fake server contracts route 200/404 實測 | — |
| SC-2 乘數 | stkfut_map v2 + lookup_product + mapping fallback | test_stkfut_map 14 / TestMultiplierStkfutFallback / B4 金額閘邊界 ×2 / A8s 不變式釘版控檔 | refresh 實跑 270 檔(50 mini)零壞列 | 台指 MULTIPLIERS 零改測試 |
| SC-3 期貨主圖 | _symbol_to_key/set_main_contract/雙保險/健檢 | TestInstrumentRouting/TrialWindow/SessionGate/RolloverIsolation/MainSlotTransfer(四轉移零洩漏)/HealthCheck + A1 夜盤整則早退 | 合約分時/五檔實畫(SC-5 截圖) | 現貨主圖/自選/訊號全家測試零改綠 |
| SC-4 下拉 | App state/useStkfutContracts/StockPage | StockPage 7 / App 2 / hook 4 / stkfut.test.ts(B3) | SC-4 截圖 + user 過目待列 | 換股重置/404 隱藏 |
| SC-5 分時/五檔切換 | XWindow 參數化/stkfut prop/D10 停用 | D9 lock 全套 + B1 x 軸元件斷言 + 元件層四條 + A6 模式還原 | SC-5 兩張截圖(量化間距證據)+ user 過目 | index/現貨呼叫端零改斷言 |
| SC-6 下單 | LadderView/StkfutLadder/RightRail fut 貫穿/後端三閘 | StkfutLadder 12 / TestOrderStkfutGates 11 / R2-5 武裝 / A5 口數分槽 / R4 market=fut | SC-6 截圖(未武裝);**真送單 = user prod 安全首單(§7)** | PriceLadder 47 條零改(🔵 證據)/ FuturesLadder 零改 |
| SC-7 零退化 | — | 六 gate + validate 42/42 | duplicate-key 未再現 | 全家 2319/1556 |

無 FAIL → 不分流。SC-6 real-env 欄 = user 過目層(§7 紀律,brainstorm 明文);
SC-4/5 = 截圖 + user 過目。
