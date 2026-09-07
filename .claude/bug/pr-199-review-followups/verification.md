# pr-199 review 收修(`fix/pr-199-review-followups`)— verification

來源:`docs/superpowers/specs/pr-199-review.md`(/pr-review #199,CC 單軸 + 同軸內部複查)findings F-01–F-50:
Must 0 / Should 0 / Nice 47 / 參考用 3。user 2026-09-07 拍板:45 條 auto-fix 全修;ask-user 兩條 **F-01 → A(code 不動、改文件「同伴沒人鎖過、自己鎖過不擋」)**、
**F-09 → A(回填改逐行 bytes)**;no-op 四條(F-14 / F-48 / F-49 / F-50)不動。
分支自 master `1e58a083` 切出(worktree `.claude/worktrees/fix-pr-199-review-followups`,前端 `npm ci` 自裝,後端用主 tree venv)。

## 1. commits(🔵 refactor → 🔴 fix(+ 對應測試)→ 🟢 test → chore docs,三類不混)

> 「sha(分支)」是 PR #200 rebase merge **前**的分支 commit(dangling);「merged sha」是落地 master 的同一筆
> (`git log 1e58a083..60137dae`;2026-09-07 整體 review F-36)。

| sha(分支) | merged sha | 類 | 內容 |
|---|---|---|---|
| `706e4b16` | `b66c072e` | 🔵 refactor | F-02 fileio 三 helper 判準表 / F-03 evaluate docstring / F-04 detail 不可雜湊註記 / F-01 signal_policy docstring / F-13 hits 固定序契約 / F-17 前端 `peerPhrase` / F-19 wire 存證欄註記 / F-21 `beepFor`;零行為 |
| `ae750d3b` | `380cbdaf` | 🔴 fix | F-08 `outcome_bars` 整顆 `BarsResult`、status ≠ ok WARNING、刪 prod 走不到的 `except HistoryTimeoutError` / F-09 逐行 bytes / F-10 guard / F-11 `policy_quotes(codes)` + `peers_fn(peer_codes)` / F-12 no_data 保名 / F-13 迭代 `ctx.hits` / F-15 刪 sweep 專屬分支 / F-16 撞名 WARNING + 後果 / F-20 chip 移到 merged 容器外 / F-07 刪 `live_engine` 別名;同 commit 含對應測試(F-27 / F-28 / F-29 / F-30 / F-31 / F-32 / F-33 / F-34 / F-35 / F-36 / F-37 / F-38 / F-40 / F-41 / F-42 / F-43 / F-44 / F-45 / F-46 / F-47 + F-16 撞名 WARNING 案 + F-09 壞行案 + F-11 codes 子集案) |
| `f068cadf` | `2b75c1fa` | 🟢 test | F-23 掃單簇清狀態五案重寫 / F-24 golden self-check ms 配對 / F-25 參考碼 loader session gate + fixture 重錄 / F-26 參考碼 docstring 分兩半 / F-39 `_RULE_PARAMS` import / F-18 `policyTitle` 三條字面 / F-22 規則視窗選擇器 |
| `32fd0e52` | `1a8bfb66` | chore docs | F-01 CONTEXT.md / F-05 fake_server.py + vite.sidecar 自我定位 / F-06 verification.md 如實記跑法;pr-199-review.md + .audit.md 入 `docs/superpowers/specs/` |
| `01de3a12` | `f498508b` | 🔵 refactor | two-axis round-1:std F-01 app.py `peers_fn` 註解 / std F-02 `_sweep_seed_rule` docstring / spec S-01 `_fetch_outcome_bars` docstring / spec S-02 `peerPhrase` `??`;零行為 |
| `9f13b8c9` | `44665bd6` | 🟢 test | two-axis round-1:std F-03 / S-05 guard 一案(突變體 m9 殺)/ std F-04 合併列 chip 位置一案 / spec S-03 `_EMPTY_PEER` 替身同形 / std F-06 `_PollClock` 前提 docstring |

## 2. 紅 → 綠(突變體;`scratchpad/mutate.py` 套用 → 跑 → 還原,每個突變體恰一條紅、其餘綠)

| finding | 突變體 | 紅的測試 |
|---|---|---|
| F-23 | `reset_day` 不清 `_sweeps` | `TestSweepClusterState::test_reset_day_clears_sweeps`(1 failed, 4 passed) |
| F-23 | `reset_day` 不清 `_lookback` | `test_reset_day_clears_lookback` |
| F-23 | `drop_code` 不清 `_sweeps` | `test_drop_code_clears_only_that_code` |
| F-23 | `drop_code` 不清 `_lookback` | `test_drop_code_clears_lookback` |
| F-27 | 回填行尾硬寫 `"\n"` | `test_fills_t1_t2_and_leaves_other_lines_byte_identical[crlf]`(lf 案仍綠 = 原覆蓋缺口實證) |
| F-33 | `peers_fn` 例外不再吞(`except ZeroDivisionError`) | `TestPeersFnFailure::test_peers_fn_error_degrades_to_s_only_logs_once_and_resets_on_rollover` |
| F-33 | `peers_fn` 例外逐 tick 印(`if True`) | 同上 |
| F-28 / F-08 | status ≠ ok 改 `logger.exception` | `test_failure_leaves_null_and_continues_other_codes[timeout]` / `[disconnected]` |

F-25 fixture 重錄:三案 ticks 各只掉毫秒 48600000(13:30:00.000 收盤撮合)一筆,`expected_prefix` / `expected_research` / `_note` / `params` 逐字不變(以 git diff 解 JSON 逐案比對)。

## 3. 完成前 gate(全綠;`32fd0e52` 工作樹)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q` | **3493 passed, 3 skipped**(212.47 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings | 0 |
| `… -m copycat validate --run-five …/out/five_tigers --run-four …/out/four_tigers` | **42/42 PASS** | 0 |
| `npm test`(frontend/) | **154 files / 3005 passed** | 0 |
| `tsc -b` / `eslint src` | 零輸出 | 0 |
| `react-doctor --scope changed --base master --no-telemetry` | No issues found(5 files) | 0 |

**review 收修後最終重跑(`9f13b8c9` 工作樹)**:pytest **3494 passed, 3 skipped**(208.79 s)/ ruff All checks passed / pyright 0 errors /
vitest **154 files / 3006 passed** / tsc 0 / eslint 0 / react-doctor No issues found(6 files);validate 42/42 沿 `32fd0e52`(round-1 未動 replay 相關碼)。

`ruff format --check` 對 6 個觸碰檔報 would reformat:逐一 `--diff` 比對皆為 master 既有未 format 行(`signal_hub.py` 三處 log、`test_signal_hub.py` 三個簽名、`test_stock_engine.py` StockTick 建構、`test_signal_rules.py` 一處 make),本 PR 新增行手動對齊,不順手整檔 format(backend-conventions)。

## 4. 真實環境

本批不碰政策門檻 / 規則檔 / jsonl 形狀,影子期第一天(2026-09-07)跑著的 prod server(`1e58a083`,08:03 起)不需重啟。今日實錄(截至 13:24):政策列 29(S 22 / P 6 / B-b 1)、notify=true 18、佇列滿 0、政策行情快照失敗 0,與 CLAUDE.md §1 判準相符。
下次重啟後可觀測差異:(1) TC4 忙時 13:40 log 多一行「T+1/T+2 回填日 K timeout(留 null 下輪再補):<code>」;(2) 壞 UTF-8 行 log 一行「n 行不是合法 UTF-8,原樣保留、其餘列照補」且其餘列照補;(3) rail 合併列 chip 與 kind 段同行(**無新截圖**,spec 軸 S-04 知情:結構由 `SignalRail.test.tsx` 合併列 chip 位置案釘住,視覺以下一交易日盤中「政策 + 爆拉同 tick」的 rail 列目視為判準);(4) 規則檔早有「掃單簇」時啟動 WARNING 帶「影子期零政策列」後果。

## 5. Review(two-axis,fixed point `1e58a083`,reviewed head `32fd0e52`;兩 sub-agent 皆 opus)

- 標準軸 6 條(MED 3 / LOW 3):F-01 app.py `peers_fn` 型別註解未跟 F-11 / F-02 `_sweep_seed_rule` docstring 仍說與 `default_rules` 共用 / F-03 F-10 guard 零測試 / F-04 chip 外移零測試 / F-05 內層 span 純轉手(judgement)/ F-06 `_wait_polls` 代理脆弱。**修 5、否決 1**(F-05:兩分支 DOM 形狀要一致,零成本包裝不拆)。F-03 新案以突變體 m9(刪 guard)實證會紅。
- spec 軸:**缺漏 0 / scope creep 0**,no-op 四條區域與硬限制逐字未動;5 條 LOW:S-01 `_fetch_outcome_bars` docstring「失敗 → None」失真 / S-02 `peerPhrase` `peers_up` 改 `??` / S-03 `_Watch.peers_fn` 替身對未知 code 要回全 None 列(與 engine 契約同形)/ S-04 無新截圖(知情,見 §4)/ S-05 = std F-03。修 4、知情 1。
- 處置全文 `code-review-round-1.json`;收修 commit 見 §1 末兩列。收修後全 gate 重跑見 §3 末列。
