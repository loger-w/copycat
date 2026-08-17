# verification — mod/signal-denoise(2026-08-18)

## 自動化 gate(全套,fix 波後 HEAD)

| 指令 | 結果 | exit |
|---|---|---|
| `.venv\Scripts\python -m pytest -q` | 2696 passed, 1 warning(baseline 2652) | 0 |
| `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| `npm test -- --run`(frontend) | 127 files / 2220 passed(baseline 2200) | 0 |
| `npx tsc -b` / `npx eslint src` | exit 0 / exit 0 | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 7 files / No issues found(0 新增) | 0 |
| `.venv\Scripts\python .claude/mod/signal-denoise/replay_cdp.py`(SC-6) | actual jsonl 120;baseline(dwell 0)=127 → new(dwell 300)=89,−29.9%;2408/3006/3037/8064 不變 → PASS | 0 |

證據檔:evidence/gate-backend.txt、gate-frontend.txt、SC-6-replay.txt。
(尾修 groupRuleNames 段序 commit 後前端子集 gate 見 progress.md 追記。)

## 真實環境(verify server 8722 = 新碼 HEAD,fake TC4;vite 5175 proxy → 8722)

環境:`data/market-verify/` 注入 prod 真實 `signal_rules.json`(v1)複本 + 2026-08-17 真實 jsonl(192 則)
複製為 `signals/20260818.jsonl`;prod 8721 / `data/signal_rules.json` 未動。

| 項 | 證據 | 結果 |
|---|---|---|
| happy SC-8:v1 規則檔啟動載入 | health `{git_sha:1602a739}`;log「訊號規則檔 v1→v2:規則 r-…-000 補 rearm_dwell_secs=300.0」;`GET /api/stock/signals/rules` cdp params 含 `rearm_dwell_secs:300.0`;檔案未回寫(v1) | PASS |
| happy SC-5:今日訊號 rail 合併 | 192 row → 178 `<li>`,13 組合併(= 08-17 實際 13 個同秒時點);樣本「12:02 6451 突破 CDP AH・爆量 5.9 倍 ｜ 爆量・CDP 穿越」;段各自著色(突破=text-bull、爆量=muted);分隔符 aria-hidden ×14 | PASS(evidence/SC-5-rail-merged*.jpg / -closeup.png)|
| happy SC-7:規則 UI | 列表摘要「AH+NH+中軸+NL+AL · 重新武裝 5 tick · 駐留 300 秒 · 冷卻 600 秒」;編輯開啟「線外駐留秒數 300」欄 | PASS(evidence/SC-7-rules-summary.jpg / SC-7-rules-edit-dwell.jpg)|
| edge SC-8 前滾:UI 儲存規則 → upsert | `data/market-verify/signal_rules.json` 變 `_cache_version: 2` + 含新鍵;prod `data/signal_rules.json` 仍 v1 | PASS |
| edge SC-5:單則列外觀 | 178 列中 165 單則列 DOM 與改前同構(既有測試 + 目視) | PASS |
| edge W6:today 端點 | 仍 192 row 逐則(合併只在前端) | PASS |
| 未改功能抽 1 | `/api/health` 200 | PASS |
| 未改功能抽 2 | 規則 dialog 其他 kind 摘要(爆拉爆跌 ±2% / 300 秒 · 冷卻 1800 秒)不變 | PASS |
| SC-4 Discord 合併真發 | verify 模式 Discord env 壓制,無法真發;以 TestDiscordMerge 6+3 條 + mutation 為據;**真 Discord 待 prod 重啟後盤中過目** | 驗證窗口外(降級:測試)|
| SC-1/2/3 真 tick 減量 | 驗證窗口 = 2026-08-18 盤中 jsonl 對照;窗口外以 SC-6 回放為準 | 驗證窗口外(降級:回放)|

## 既有測試紅綠對照 spec §6

- 該紅且已改:`test_rearm_released_at_five_ticks`(dwell 語意)、`test_saved_file_carries_cache_version`(1→2)、
  `test_two_rules_same_kind_both_fire`(bot 2→1)、rearm_ticks 精確集合 fixture 補鍵、SignalRail 本輪自加斷言段序修正。
- 不該紅:全套 2696 / 2220 綠,無預告外紅。白名單 W1–W10 由 correctness lens 逐條對照 ok(code-review-round-1.json)。

## Migration 可逆性

- 前滾:v1 載入補鍵不回寫(sha 前後同,Pkg B 真檔驗證);upsert 後落 v2(verify 複本實測)。
- 回退:刪 cdp 規則 `rearm_dwell_secs` + `_cache_version` 改 1 → 舊碼可讀(舊碼讀 v1 = baseline 行為);
  未 upsert 前無需任何動作。
