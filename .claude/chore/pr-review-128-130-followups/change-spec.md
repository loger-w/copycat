# copycat handoff — 2026-08-28:三份 /pr-review(#128 / #129 / #130)共 22 條 finding 合一支分支收掉

新 session 的目標:**一支分支**把 `docs/superpowers/specs/pr-128-review.md`、`pr-129-review.md`、`pr-130-review.md` 的 22 條
finding 全部處理掉(user 2026-08-27 深夜拍板「三個 review 都直接收成一個分支做」)。22 條**全 Nice to Have、零 Must / Should**,
沒有急的;三條 `ask-user` 要先問。

## 0. 先讀什麼(不重抄,照路徑讀)

- 三份主報告(拍板表 + inline block 複製即可用):`docs/superpowers/specs/pr-128-review.md`(6 條)、`pr-129-review.md`(8 條)、
  `pr-130-review.md`(8 條);同目錄 `.audit.md` = 完整證據(4.3b 主 agent 實查備註、reviewer 原文 search-proof)。
  每條有 `F-0n`、`finding_uid`、File / Line / Comment、Action 理由;**不要重審,直接修**。
- 三個 PR 的 artifact(要一併改的 verification / change-spec 就在裡面):`.claude/mod/heal-gate-per-consumer/`、
  `.claude/bug/breakeven-review-followups/`、`.claude/bug/sparse-review-followups/`;被點名的舊 artifact:
  `.claude/bug/breakeven-avg-source-prod-chain/verification.md`、`.claude/bug/corr-sparse-leg-heal-exempt/verification.md`。
- memory:`~/.claude/projects/C--side-project-copycat/memory/pr-review-128-129-130.md`(三份結論 + 流程教訓)、
  `pr-review-fixes-three-rounds-shipped.md`(這三個 PR 是怎麼來的)、`heal-gate-per-consumer-shipped.md`。
- 專案 skills:`backend-conventions`、`frontend-conventions`(#129 F-05 / F-08 動 `types.ts`)、`frontend-testing`(若補 parity
  測試)、`tc4-market-facts`(#128 F-01 重掛 snapshot 事實在 :74 / :180)、`ops-discipline`(prod 重啟)。

## 1. 環境現況(08-27 23:5x)

- master = `c37e0401`(= a8cacf72 + 三份報告落檔);working tree 只有他 session 未提交的 `.claude/skills/ops-discipline/SKILL.md`
  (+7 行)—— **不要碰、不要 commit、rebase 用 `--autostash`**;根目錄有未追蹤 `node_modules/`,不動。
- **prod 8721 = `f8232339`(孤兒 SHA)**:user 08-27 19:26 從自己的 PowerShell 視窗起的,當時 tree 停在第二輪分支中途、該
  commit 後被 rebase 改寫、不在 master 歷史(`git log f8232339..HEAD` 找不到)。行為 = #128 + #119 初版。**明早開盤前重啟請確認
  在 master 上起**(`git status` 看分支;run.ps1 或獨立 console `python -m copycat.server` 皆可)。dist 已重 build。
- `.worktrees/` 已清空;review 用的 lock 檔已清。

## 2. 開場要問 user 的三條 ask-user(一次問完)

1. **#128 F-06**:`TestIndexHealWindowGate::test_end_matches_index_engine_watchdog_window` 要不要從 `tests/live/test_stock_source.py`
   搬到 `tests/server/test_index_engine.py`(依賴方向 server → live;live 側唯一一筆 `from copycat.server` import)?搬的話
   CLAUDE.md §4 那條的測試路徑同步改。建議:搬(獨立 🔵 commit)。
2. **#129 F-02**:`tests/capital/test_client.py::_PNL_3357` 與 `tests/capital/test_balance.py::RAW_PNL_MARGIN` 逐 byte 相同 ——
   要不要把 `RAW_PNL_MARGIN` / `RAW_PNL_ROW` 搬進 `tests/capital/profit_rows.py` 讓兩檔都 import?(動到 test_balance,測試重組 🔵;
   `_BAL_3357` 12 處內嵌是同型但不在本輪,記 next-time。)建議:搬。
3. **#129 F-05**:要不要補 `AVG_SOURCES`(`frontend/src/types.ts`)↔ `copycat/capital/models.py::AvgSource` 的跨語言 parity 測試
   (照 `tests/fixtures/overlay_parity.json` / `signal_param_specs.json` 樣板,或後端測試直接讀 `types.ts` 字面比 `get_args`)?
   超出 pr-119 範圍、是新 seam。建議:補(一條測試 + CLAUDE.md §4 avg_source 契約補 pin 位置)。

## 3. 分支與 commit 分組建議(三類不混)

分支名建議 `chore/pr-review-128-130-followups`(走 /mod 或 /chore;白名單 = 三個 PR 的行為逐 bit 不變,除下列一條)。

### 🔴 行為(唯一一條,紅先行)
- **#130 F-01** `copycat/corr_config.py::_parse_legs` 的 sparse WARNING 改成蒐集後、`load_config` 過完 legs / base 兩道降級
  才印(或最低限度註明「可能先於降級印出」);補一條「壞 sparse + 後面腿缺欄」的 caplog 測試(現有 :185 / :191 降級測試無此組合)。

### 🔵 測試 / 重構(行為不變)
- **#129 F-03** kind=None 哨兵 `[25]="3"` → `"9"`(`balance.py:153-156` 寫「融券疑 3」),並補 `assert any("種類標籤未知" …)`
  把 kind=None 路徑釘死(`balance.py:203` 那條 log)。
- **#130 F-05** `tests/server/test_main_wiring.py` 三條不看 sparse 的 wiring 測試(`always_on_session_gate` /
  `leg_gate_only_taifex` / `tws_leg_gate_ands_calendar`)改傳 `DEFAULT_CONFIG`(:504 已 import)或 `tests/helpers/corr_legs.py::CFG`,
  不再各自 `load_config()` 讀真檔。
- **#128 F-06**(問過 user 後)parity 測試搬 `tests/server/test_index_engine.py`。
- **#129 F-02**(問過 user 後)`RAW_PNL_MARGIN` / `RAW_PNL_ROW` 搬 `profit_rows.py`。
- **#129 F-05**(問過 user 後)`AvgSource` 跨語言 parity 測試。
- **#129 F-08** `frontend/src/types.ts:106` `/** Position asdict… */` 搬到 `export interface CapitalPosition {` 正上方(一行位移)。
- **#130 F-02** 刪 `copycat/server/app.py:412` 與 `copycat/corr_config.py:105` 的 `(review S-1)` / `(review S-3)` 尾綴(或改成
  可解析路徑);`copycat/server/verify.py:204` 既存的同型尾綴順手一起改(PARTIAL 那條)。

### chore(文件 / 註解 / artifact)
- **#128 F-01** `copycat/live/stock_source.py:49-51` 代價段改口:分時自癒會連帶重掛 IX0001(`index_engine._subscribe_and_backfill`),
  現價欄**應會**跟著回來(**未實測**,08-28 以 `/api/index/state` 核);`docs/next-time.md:40` 同句。
- **#128 F-02** `CLAUDE.md:269-272` §4 那條:descriptor 改「推播靜默(stale)watchdog 凍結點」+「分時自癒窗反而從這一點開始」;
  漂掉症狀改可觀測(「兩把值不同 → 13:25 後 IX0001 自癒又出現 / 加權 stale 徽章 13:2x 提早熄滅」);
  `tests/live/test_stock_source.py:1270-1271` docstring 同句同步。
- **#128 F-03** `stock_source.py:43` 與 :480「IX0001 / 櫃買」→「IX0001;櫃買走 MIS poll 不吃這把」。
- **#128 F-04** `stock_source.py:38-39` 個股重補路徑補「漲跌停值變」(`stock_engine.py:1106-1113`)+ 逾時重排,加情境限定語;
  next-time 與兩份 artifact 同句。
- **#128 F-05** `.claude/mod/heal-gate-per-consumer/verification.md:42` M4 列補「(選集 = 兩個 live 檔 103 tests)」。
- **#129 F-01** `CLAUDE.md:248` 「fut 列恆 null」改有界:OI 快照來源恆 null;`_apply_fill_locked` 樂觀套用新建的 fut 列是
  `"fill"`,下一輪 OI 落地即覆蓋(OI 連續失敗時 `_stale_fut_positions()` 沿用更久)。
- **#129 F-04** `tests/capital/profit_rows.py:8-14` docstring「六份 → 七份」、刪「配 `_BAL_3357` 的 155.63」因果句(155.63 是
  維持率);`.claude/bug/breakeven-review-followups/change-spec.md:11` 同數字。
- **#129 F-06** `.claude/bug/breakeven-avg-source-prod-chain/verification.md:60` 末句改引 `isAvgSource` / `AVG_SOURCES`,
  不引已被取代的 `raw === "broker"` 字面。
- **#129 F-07**(no-op,流程層)artifact 引 rebase 前 SHA:不回改;在 next-time 既有「artifact SHA dangling」條目下加一行
  「#129 重演;處置候選 = merge 後補寫最終 SHA / 改引相對順序 + subject」。
- **#130 F-03** `.claude/bug/sparse-review-followups/verification.md:27` 「型別守住不變量」→「型別守住『必須傳 config』;
  『與 engine 同一份』仍由 `_make_corr` 單一區域變數保證」。
- **#130 F-04** 同檔 :31 事故記錄註明 `2e31a9bc` 已被 `reset --soft` 丟棄、僅存本機 reflog、不可覆核(或貼當時
  `_default_corr_source(trading_calendar)` 差異片段)。
- **#130 F-06** `.claude/bug/corr-sparse-leg-heal-exempt/verification.md:23`、:48 「三條」→「當時 3 條;`r1_takes_over…` 為
  review 追加,現為 4 條」。
- **#130 F-07** `configs/correlation.json` `_comment` 補「值只認 JSON 字面 true;打成 "true" / 1 / null 一律無效並印 WARNING 點名該腿」。
- **#130 F-08** `.claude/bug/sparse-review-followups/change-spec.md:27` 白名單第 1 條改不綁長度措辭(「原五腿逐字不變;新增案只准尾端追加」)。

## 4. 紀律提醒(這一輪學到的)

- 修 review finding 時最容易再犯同型錯:代價 / 兜底寫重(#128 F-01 / F-04)、判準寫成絕對語(#129 F-01)、數字沒重數(#129 F-04)、
  修「文件與 code 相反」時引了會被取代的字面(#129 F-06)。每句「只剩 X」「恆 Y」寫之前 grep 一次。
- 主 agent 自己立的 CLAUDE.md §4 契約條,descriptor 要對照 code 的**實際消費者**(#128 F-02 把 stale watchdog 寫成分時 watchdog)。
- mutation 腳本要 `try/finally` 還原,commit 前 `git diff --cached` 對照預期範圍(08-27 突變體差點進 commit 的事故)。
- `/pr-review` 報告合約:表格 cell 不能有裸 `|`(含 `\|\|` 與 shell pipe),撞了 projection helper 直接拒發布。
- 每輪收尾:`pytest -q` / `ruff` / `pyright` / `copycat validate` + 動到 frontend 時 `npm test` / `tsc -b` / `eslint` /
  react-doctor(**全量 vitest 與全量 pytest 不要並跑**,`src/App.test.tsx` capital WS 那條會負載 flake);two-axis review dispatch
  顯式 `model=opus`;verification.md + code-review-round-1.json 落 artifact 目錄;PR merge 走 `--rebase --delete-branch`。

## 5. 08-28 交易日待驗(誰在場誰做,與本分支無關但別忘)

- `grep "零推播自癒" logs/server-20260828-*.log | grep IX0001` 13:25 後 0 筆;13:25–13:35 個股五檔 / 現價照常跳、該窗個股自癒只有
  6949 型冷門檔;13:36 `curl /api/index/state` 記 twse 最後更新時戳 + 現價欄(順便驗 #128 F-01 的「重掛 snapshot 讓現價欄回來」);
  `| grep SXF` 全日 0 筆;`curl /api/capital/positions` 證券列 `avg_source == "broker"`。

## Suggested skills(Skill tool)

`mod`(或 `chore`;含 caller map + 白名單:三個 PR 行為逐 bit 不變,除 #130 F-01)、`branch-lifecycle`(開工 / 收尾)、`tdd`
(#130 F-01 紅先行)、`code-review-two-axis`、`receiving-code-review`、`auto-verify`、`verification-before-completion`、
`backend-conventions`、`frontend-conventions`、`frontend-testing`、`tc4-market-facts`、`ops-discipline`。
