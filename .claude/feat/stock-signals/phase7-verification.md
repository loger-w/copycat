# Phase 7 verification:stock-signals

日期:2026-08-04。憑據:重讀 brainstorm.md(含全部 amendment)逐 SC 核對;
pytest **本 phase 新鮮重跑** `1658 passed`(exit 0,`evidence/pytest-phase7.txt`);
前端 `994 passed / 74 files`(`evidence/vitest-final.txt`,Phase 5);
real-env 全 PASS(`real-env-verification-round-1.json`)。

| SC | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 CDP 穿越 | `copycat/live/signal_state.py:177`(evaluate;CDP 三層去重/合併)、`copycat/server/signal_hub.py:317`(_emit payload) | `tests/live/test_signal_state.py` CDP 組 11 案(單線/橫盤/rearm 80.00 元組/cooldown/合併固定序/無基準)+ `tests/server/test_signal_hub.py::test_ws_payload_matches_contract` 等 SC-1 整合組 — 檔案合計 41+29 案全綠 | `evidence/SC-1_ws-signal.txt`(WS 全文)+ `evidence/SC-1_discord-push.txt`(真頻道文案)+ 截圖 `SC-9_signal-rail.png` | `/api/health`(`evidence/regression_sample.txt`) |
| SC-2 爆拉/爆跌 | `signal_state.py:177` 內 surge/crash 段(300s 窗) | test_signal_state surge-crash 5 案(±2.1 發/+1.9 不發/cooldown) | `evidence/SC-2_SC-4_detector.txt` + `SC-7_today-api.txt`(2317 +2.20%) | `/api/stock/names` count=2401 |
| SC-3 爆量 | `signal_state.py` vol_burst 段(ratio 3.0 + 兩道地板) | test_signal_state vol_burst 5 案(達標發/<15 分不發/低量地板/關 surge_crash 照發/day_volume=0) | pytest 層(brainstorm 定義之驗證方式;`evidence/pytest-phase7.txt`) | 同上 |
| SC-4 鎖板/打開 | `signal_state.py:455`(_limit_event 複合簽名)、`:213`(evaluate_book 簿路) | test_signal_state limit 組 10+1 案(複合簽名/首攻反例/兩路 open/latch/跌停對稱/重啟語意/冷卻分桶) | `evidence/SC-2_SC-4_detector.txt`(含市價佇列 0 檔位路徑) | — |
| SC-5 回補不誤發 | `copycat/server/stock_engine.py:430-447`(掛點只在 live 路徑;apply_backfill 零接觸) | `tests/server/test_stock_engine.py::TestSignalHubHooks` 回補重放零呼叫 + `test_signal_hub` SC-5 案 | 結構保證 + pytest(brainstorm 定義);fake E2E 未觸發回補誤發 | 既有 stock_engine 663 行測試零改動全綠 |
| SC-6 盤別 gate | `signal_state.py:245`(_in_session 半開區間)+ gate 2 trade_date + engine 試撮短路 | test_signal_state gate 4 案(盤外不推進/13:30 端點/舊 trade_date/首 tick)+ test_stock_engine 試撮 on_tick 0 次 | 注入時鐘 harness 即依賴此 gate(盤後真牆鐘被擋 → 覆寫才能點火,反向佐證 gate 有效) | — |
| SC-7 訊號歷史 | `signal_hub.py:392`(_append_jsonl)、`:401`(today_signals)、`app.py` GET today route | test_signal_hub SC-7 組(jsonl 落檔/跨重啟同 id/新訊號 id 不碰撞 [lock]/壞行跳過)+ test_signal_routes today 組 | `evidence/SC-7_today-api.txt`(注入前空/後三 kind 十欄) | — |
| SC-8 Discord bot | `copycat/server/discord_bot.py:161`(handle_add 等,模組層零 discord import)、`copycat/server/watchlist_service.py:51-56` | `tests/server/test_discord_bot.py` 28 passed(非 skip;defer 順序/文案/降級)+ `test_watchlist_service.py` 15+3 案 + 裝 extras 後 wiring 測 1 案(`evidence/pytest-with-discord-extra.txt`) | `evidence/SC-1_discord-push.txt`:bot 真上線、/watch sync 至 guild、三則真推;**slash 指令實發留 user 過目**(bot 已在你的伺服器,發 `/watch list` 即驗) | — |
| SC-9 左側訊號欄 | `frontend/src/components/stock/SignalRail.tsx:全檔`、`StockPage.tsx`(版面三欄) | SignalRail.test 10 案 + StockPage.test 整合 2 案(rail 在最左/點列切檔) | 截圖:`evidence/SC-9_signal-rail.png` / `SC-9_click-switch.png` / `SC-9_ui-verdict.txt` / `SC-9_console.txt` + **user 過目** | 側欄既有測試(WatchlistSidebar 797 行)零改動全綠 |
| SC-10 即時通知 | `frontend/src/components/ToastStack.tsx:16`、`hooks/useSignalAlerts.ts`(上限 4+溢出/Notification 脫離靜音閘/beep) | useSignalAlerts.test 13 案(連發 20 → 4+溢出/5s 消失/hidden 才 Notification/靜音只關聲音)+ ToastStack.test 4 案 + App.test 整合 | 截圖:`evidence/SC-10_toast.png` + **user 過目** | — |
| SC-11 自選同步 | `useStockStream.ts`(watchlist_changed → invalidate 單一註冊點)、`watchlist_service.py`(廣播) | useStockStream.test 追加 3 案 + test_watchlist_service 廣播案 | `evidence/SC-11_watchlist-sync.png/.txt`(REST PUT → 側欄未重整出現 2454) | — |
| SC-12 開關持久化 | `signal_hub.py:479`(set_enabled + lock)、`app.py` enabled routes、SignalRail toggles | test_signal_routes enabled 組 6 案(往返/重啟保留/非法鍵/非 bool 不寬鬆轉型/503)+ test_signal_hub 停用組 | `evidence/SC-12_enabled-api.txt`(關→零產出→開回復發,先跨冷卻反證)+ `SC-12_toggle-off.png` | — |

無 FAIL 項,四分流不觸發。rollbacks 全程零筆(state.json)。

補述:
- 盤中真 TC4 行情下的訊號點火屬驗證窗口外(今日已收盤),brainstorm 各 SC 標定的
  降級策略(fake source + 另 port + 注入時鐘)已全數執行;明日盤中 user 實際使用
  即為最終真實驗證,已列收尾報告提醒。
- SC-8 的 slash 指令人手實發、SC-9/SC-10 截圖之外的 user 過目,列收尾報告清單。
