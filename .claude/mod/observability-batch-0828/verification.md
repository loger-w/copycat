# verification — mod/observability-batch-0828

分支 `mod/observability-batch-0828`(worktree `copycat-wt-obs`,自 master `e74b40c3`);commit 依 (b) 慣例引「第 n 筆 + subject」不引 SHA。

## 1. 自動化 gate(全部在 worktree 跑,venv = 主 tree `.venv`)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest 全量 | `python -m pytest -q -p no:cacheprovider` | **3155 passed, 1 skipped**(193.8 s;master 前次 3153 → +2 淨增:本批新增 3 + 1 + 2 + 1 + 3 條、改名 1 條,S1 去裝飾器不影響數) | 0 |
| ruff | `python -m ruff check copycat tests` | All checks passed | 0 |
| pyright | `python -m pyright` | 0 errors, 0 warnings | 0 |
| validate | `python -m copycat validate`(**主 tree**;`copycat/replay` / `engine` / `data` 本分支零 diff,`git diff --stat master -- …` 空) | 42/42 PASS | 0 |
| frontend | 未動 `frontend/` → 不跑 | — | — |

紅先行證據:第 1 筆 `test(live)` 單獨 3 failed / 1 passed(`_push_fp` 不存在、`_SNAPSHOT_GRACE_SECS` 不存在);第 3 筆 `test` sparse 集合 1 failed;實作後綠。
`ruff format --check` 對本批五個測試檔本來就不乾淨(既存),formatter 動到的非本批 hunk 已逐檔還原(scope 紀律),只留本批追加段。

## 2. Two-axis review(round 1)

`code-review-round-1.json`:Standards 11 條(硬 3 P3 / judgement 8)、Spec 8 條(P2×3 / P3×5)。接受修 15、spec 回填 3、記下不動 1(S3 commit 夾帶 skill 段,不重寫歷史)。
最重兩條都修了:Spec c1(落後用牆鐘分 → 每個開盤固定假警報)改以**可交易分鐘**計 + `test_session_open_is_not_lag`;Standards J2(strptime 在 event loop)→ `_fetch_and_check` 進 executor。
收修 = 第 9–12 筆(fix(server) / refactor(live,server,capital) / chore(docs) / fix(capital) pyright)。

## 3. 真實環境

**本批改的是 log 行為,真環境證據只能在 prod 跑新版之後取**;08-28 15:00 起夜盤開著、盤中不重啟 prod(ops-discipline),重啟時機 user 拍板。重啟後的判準(寫進 next-time 08-28 節):

| 條 | 驗法 | 期望 |
|---|---|---|
| L106 + L171 指紋 | 次一交易日 `grep 零推播自癒 logs/server-<date>.log \| grep 6949` | 由 92 發/日降到 ≤ 10 發,且 attempt 1 → 2 → 3 遞增、300 s 間隔;`grep "同指紋 snapshot"`(DEBUG,需 log level)|
| VX sparse | `grep 零推播自癒 \| grep "CFE.VX"` | 0 發(08-28 為 7 發)|
| L3 日曆誤標 | 只在日曆誤標時出現;正常交易日 `grep 可能誤標` 應 0 筆 | 0 筆 |
| L262 期貨 1K | `grep "期貨 1K"`:15:01 / 08:46 開盤後第一分鐘**不得**出現落後行(Spec c1 那條假警報);真落後 / 缺格時才有 | 開盤零假警報 |
| 損益列 INFO | `grep 損益列回填`:每 (股號, 種類) 首輪一行、值變才再印;下一筆無券空單即可讀到群益均價 | 每檔 1 行/日 |

盤後可做的替代驗證(已做):`spikes/stock_backfill_parallel_probe.py`(/perf 步驟 ①)用真 TC4 走 `StockQuoteSource.backfill` 20 檔,證明本批沒動的回補路徑在真 TC4 上仍正常(三法 tick 數逐檔相等、零逾時)—— 這是 tc4.py 改動後對同一個 source 類別的真連線 smoke;REALTIME 推播路徑(`_note_push`)真環境要等 prod。

Edge(測試層):同指紋但超過寬限 → 照清(五檔簿更新證明活著);指紋變 → 照清;`_unsub` 清指紋;休市日 4 相異價 / 重複價不印、交易日 / 09:00 前 / 無日曆零 log;歷史窗 / 日 K / 門檻內 / 開盤段界零落後 log;冷門開盤首根延後 2 分不算缺格。
未改功能抽查:全量 pytest 3155 綠(含 corr routes / market routes / stock engine);probe 走真 TC4 history 路徑正常。

## 4. 白名單逐條

1 真推播照清 ✓(`test_changed_fingerprint_clears_attempts` / 既有 `test_push_resets_attempts` 逐字不改)2 `_unsub` 清 ✓ 3 R1 / R2 / cap / VARIANT_AFTER / sparse 語意不動 ✓(test_tc4 91 條全綠)4 index 交易日 / 無日曆零新 log ✓ 5 `bars_range` 回傳與三態不變、timeout / disconnected 零新 log ✓(既有 `TestBarsRange*` 綠)6 配對規則 / 寫入欄位不變 ✓ 7 SXF 仍 sparse、非 bool WARNING 不變 ✓ 8 畫面 / wire 零改動 ✓(frontend 零 diff、payload builder 未動)。

## 5. 留尾(已寫 next-time 08-28 節)

- L171 本條留 `[ ]` 到次一交易日 6949 ≤ 10 發驗過再勾。
- /perf 開盤回補並行:實驗數字已落 next-time;下一步 = 改 `backfill` 首頁 poll 退避 + 出隊前整批 `_sub_history`(或 worker 並行 N=4),另診斷 09:00→09:02 空檔。
- B8 run.ps1 第二次 Ctrl+C:需要 prod 停下(run.ps1 佔 canonical 8721),今天做不到;併到下次 prod 重啟。
