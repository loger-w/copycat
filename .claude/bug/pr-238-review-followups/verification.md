# fix/pr-238-review-followups — verification(pr-review #238 收修;報告 `docs/superpowers/specs/pr-238-review.md`)

寫於 2026-09-14 晚(worktree `.claude/worktrees/fix-pr-238-review-followups`,merge-base `d9c39023`;handoff
`%TEMP%\copycat-handoff-2026-09-14-batch-a-review-followups.md`)。

user 拍板(AskUserQuestion 兩輪):F-01 ~ F-12 全收、一支 PR 三筆 commit;F-13 / F-14 等第一個交易日 log 再定;
F-15 只改文案 + docstring;F-16 只做 recv 緩衝那半(KoD 不做);F-17 ~ F-20 併下一個 test-hygiene 批;F-21 / F-22 no-op。
自查(receiving-code-review):F-01 / F-02 / F-09 對照碼確認成立;其餘 auto-fix 全在文件 / 註解 / 測試韌性層,報告的
突變體與實跑證據無反對理由。

## 1. 紅先行 / 突變體

### commit 1 `b08fc477` test(capital):既有 code 上加強測試,以突變體證明新斷言真的擋得住(scratchpad `mutants_c1.py`,讀寫還原不走 checkout)

| finding | 突變體 | 結果 |
|---|---|---|
| F-01 | `__main__.py` basicConfig format 加 `[%(threadName)s]` | KILLED(1 failed, 6 passed) |
| F-01 | basicConfig format 搬到變數 `fmt`(產生點搬家) | KILLED(2 failed:`_prod_log_format` 找不到字面 + parity 案) |
| F-02 | `_probe_reply` 值翻 0 時偷插 `self._com.connect_reply(...)` | KILLED(1 failed, 1 passed) |

3/3 KILLED;還原後 `test_chain_stats` 7 passed / `test_reply_watch` 2 passed,`git status` 原始碼零殘留。

### commit 2 `f48607c1` fix(backend,frontend):紅先行

先寫齊七條的測試 → 跑:**pytest 10 failed / 149 passed**(chain_stats 3 / fill_latency 2 / client 1 / clock_monitor 3 /
shutdown_budget 1)+ **vitest 1 failed / 3 passed**(query-client)→ 實作後 **209 passed** / **4 passed**。
F-16 的 loopback 案(`TestUdpExchangeOnLoopback`)在 Windows 上修前真的紅在 `WinError 10040`,不是合成的失敗。
F-07 的案用 exchange 內 sleep 0.2 s 模擬 DNS:修前 offset 偏 −100 ms(abs=1.0 斷言紅),修後 −1000 ± 1。

## 2. Two-axis review → `code-review-round-1.json`(本目錄)

Standards 零硬違反 + 6 判斷題(S-01 ~ S-06);Spec 1 MED(P-01 基線數字沒用新尺重算)+ 3 LOW,零越界、白名單五項全未動、
「做錯」零條。收修兩筆:`refactor(backend,test)`(S-02 + P-03:`__main__` 抽 `PROD_LOG_FORMAT` / `PROD_LOG_DATEFMT`
常數、parity 案 import 同一顆 + 子字串斷 basicConfig 真的引用;S-05 sleep 0.05;S-06 `object`)+ `chore(docs)`(S-01 註解 /
S-03 P-02 docstring 順序 / S-04 檔頭例外 / P-01 基線實跑重算)。S-02 突變體(常數改值 / datefmt 改 ISO / basicConfig 繞過常數)
3/3 KILLED。P-04(`NTP_PORT` + loopback 案)知情保留:那是 F-16 在 Windows 上唯一的真證據。逐條處置見 JSON `disposition`。

收修後最終輪:觸及六檔 192 passed;ruff / format(觸及檔)/ pyright 0 errors 全過;全量 pytest 重跑見 §3。

## 3. 最終輪(worktree 無 .venv,用主樹 venv;前端 worktree 內 `npm ci`)

| 指令 | 結果 | exit |
|---|---|---|
| `pytest -q -p no:cacheprovider`(全量,背景;7748e55d 259 s / two-axis 收修後 6d66353c 231 s 各跑一次) | **3391 passed**, 3 skipped(master 3386 + 本批新增 5:parity 守門 / 重連清欄 / t0 在 DNS 後 / loopback 68 bytes / 探針預算項)—— 兩次同值 | 0 / 0 |
| `graphify . --update` | 與 handoff §6 同:無 LLM key exit 1、只動 `graphify-out/cache/stat-index.json`,已 checkout 還原、未計入 | 1 |
| `ruff check copycat tests` | All checks passed | 0 |
| `ruff format --check`(觸及檔) | 只剩 master 既有未 format 行(`clock_monitor.sntp_query` 簽名、`test_client.py` 三處、`test_fill_latency._run_chain` 簽名 + 舊 assert),本批新寫行全為 ruff 形式,不重排既有區段 | — |
| `pyright` | 0 errors, 0 warnings | 0 |
| `copycat validate --run-five … --run-four …`(主樹 out/) | 42/42 PASS | 0 |
| `npx vitest run`(全量) | 157 files / **3078 passed** | 0 |
| `npx tsc -b` / `npx eslint src` | 無輸出 | 0 / 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 3 files, No issues found | 0 |
| `run_grace_secs()` | 83 → **89**(`CLOCK_PROBE_WORST_SECS` = 6.0;run.ps1 同源自動跟) | — |

## 4. 真實環境

本批 runtime 改動五處,對照原 T1 ~ T5 判準:

- F-07 / F-16(SNTP):下次重啟後 `grep 時鐘偏差 logs/server-<日>.log` 首行 RTT 不再含 DNS(冷 DNS 那一發 RTT 應 < 100 ms);
  緩衝 512 對三台公開伺服器無可觀測差異(它們回 48)。
- F-06(關機預算):`run.ps1` Ctrl+C 後 graceful 上限 89 s(原 83);健康路徑仍 1–3 s,零可觀測差異。
- F-03 / F-15(chain-stats / 落地行):重啟後 `chain-stats` 輸出多一種排除桶 `partial_chain`(當日應接近 0);落地行文案
  「累計 n 筆成交」—— **原 T4 判準要多看「鏈條數 > 0」**(CLAUDE §1 已改)。舊 log 的「涵蓋」字樣 `_STAGE_RE` 不讀,不影響回算。
- F-05(重連清點):今天零 caller 差異(`_init_com` 全初值),接重連前的預留;無真環境判準。
- F-09(前端):`npm run build` 後行為與修前相同(兩個呼叫端都不傳 `mutations`);差異只在「呼叫端傳 online 也蓋不掉」。

**prod 未重啟、dist 未 build**(prod 仍 `6cbf7cdd`,落後 #238 + 本 PR);user 的三個手動動作(校時四行 / build / 重啟)
與本批合併後一起做最省。
