# verification — fix/tc4-realtime-refcount-kill

## 自動化(repo root,2026-08-18)
| gate | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | **2725 passed**, 1 warning(150.6s);implementer 基線 2724 + 本 session 補 TXO 接線 1 |
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
