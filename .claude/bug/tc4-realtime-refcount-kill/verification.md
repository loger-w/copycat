# verification — fix/tc4-realtime-refcount-kill

## 自動化(repo root,2026-08-18)
| gate | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | round-1 修復後 **2755 passed / 1 failed**(154.6s);唯一紅 = `tests/server/test_ws_disconnect.py::TestAbruptDisconnect::test_no_write_to_dead_transport` 既有 timing flake(memory 08-05 已記;單檔重跑 3 次 2 過,本分支未動 ws 程式碼);修復前基線 2725 passed |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! |
| `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations |
| `.venv\Scripts\python -m copycat validate` | 42/42 PASS |
| frontend | 未動 frontend/,不跑 |

## 紅測試(先紅後綠,commit 序見 git log 🔴 [red]/[green] 配對)
- tests/live/test_tc4.py:TestHealSessionSilence ×4 / TestHealSymbolSilence ×3 / TestHealWindowVariantEscalation ×3 / TestHealResilience ×3 / TestHealDisabledByDefault ×2
- tests/live/test_stock_source.py:TestNoDataResubscribes ×6 + TestHealDefaults;test_futures_source / test_corr_source TestHealDefaults
- tests/live/test_session.py:TestInTxoSession ×4
- tests/server/test_main_wiring.py::test_default_txo_source_wires_realtime_heal(還原 app.py → 1 failed 8 passed;恢復 → 9 passed)

## 反向驗證(/bug 步驟 7)
`git checkout dae30751 -- copycat/live/tc4.py copycat/live/stock_source.py`(fix 前、refactor 後)→
`pytest tests/live/test_tc4.py tests/live/test_stock_source.py` → **21 failed, 62 passed**;
`git checkout HEAD -- …` 恢復 → **83 passed**。加 session/app 兩檔還原時 test_session 收集期 ImportError(`in_txo_session` 不存在)= 紅。

## 真實環境
- **重現條件已在真 TC4 上以獨立 probe 決定性重現**(repro.md 實驗 G:A 退訂 → B 0 則 15s;B 重掛 → 125 則)。
- **止血已生效**:09:31:47 側車以變體窗持有 prod 333 把 key → 09:32 起 futures/stock/index/signals 全活(截圖:自選價格 + 五檔 + 閃電梯 + 訊號)。
- **修復版 prod 驗證(待 user 拍板重啟時機)**:重啟 `.\run.ps1` 後預期時間軸:boot → 舊 session 約 60s 被 reap → 各 session 靜默 →
  ≤ R1 門檻(stock/futures 30s、TXO 60s、corr 120s)內 log 出現 `TC4 REALTIME 零推播自癒:<symbol> 靜默 …s → 重掛`,
  之後 `/api/stock/state/<code>` `no_data:false, book!=null`、`/api/futures/state` TXF `t` 前進。
  TXF.HOT 日盤 key 由 TXO+futures 雙持 → 期貨 HOT 預期到 attempt 3(window_variant=1)才活(≈ 30+60s),
  或由 futures leaf fallback 先接手。停側車後同機制再驗一次(側車退訂 → symbol 斷 → 自癒接回)。

## Code review round-1(2 lens,見 code-review-round-1.json)
P0×1(variant 對全天窗 no-op)/ P1×9 / P2×8 → 全部 accepted 修畢(8 commits `6d8af274..0d504476`),rejected 1(加 `_subscribed` 鎖:CPython GIL 反證)。
修後 gate:pytest 2755 passed + 1 既有 flake;ruff All checks passed;pyright 0 errors。

## 真實環境(2026-08-18 15:23 prod 重啟 366bf238,兩輪自癒實證)
- 15:23:51 boot,五條 session 各起 watchdog(TXO R1=60 / stock+index 30-60 / futures 30-60 / corr 120-240)。
- **第一輪(舊 server 殭屍 reap)**:TC4 log 15:24:40 reap 舊 TXO session、15:24:50 reap 其餘四條;舊 futures session 的日盤 key `TXF.HOT|00–06` 歸零 → 上游退訂 → 夜盤 key(count 2)全斷。
  server log:15:25:25 期貨三檔靜默 35s → 重掛;15:25:52 TXO 277 檔 R1 整批重掛;MXF/TMF 第 1 次即活(獨持);TXF(TXO+futures 雙持,count 2↔1 兩次不救)**15:27:55 attempt 3 換窗 `06–23` → TC4 `GetSubQuoteCount count:0 → Add count:1`(重掛上游)→ 15:28:49 起即時**。
- **第二輪(側車硬殺)**:15:33:03 taskkill 側車 → 15:34:00 reap → 15:34:31 三檔靜默 30s → 重掛(TXF 已在 variant=1 獨持 key,attempt 1 即活)→ 15:36:03 三檔即時;NK225M 15:34:11 R2「訂閱久未推播」重掛(大阪 15:30 開盤,正常)。
- 零 `自癒重掛失敗`、零 ERROR;corr 六腿 stale=false;前端右上「版本落差」徽章消失。
- 個股面夜間閘關,個股 R3 / R1 的真環境驗證留待 08-19 08:30 開盤(側車 reap 已把個股日盤 key 上游退掉,明早開盤前個股 key 應為死態 → 開盤 R3 10s 內重掛;log grep `零推播自癒:TC.S.TWS`)。
