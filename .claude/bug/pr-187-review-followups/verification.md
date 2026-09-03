# pr-187 review 收修(`fix/pr-187-review-followups`)— verification

來源:`pr-187-review.md`(repo root)Should Fix #1–#8(user 拍板「8 條 Should Fix 開收修分支修掉」)。
分支自 master `8d42098d` 切出(worktree)。

## 1. commits(🟢 紅測試 → 🔴 fix → 🔵 refactor)

| sha | 類 | 內容 |
|---|---|---|
| `d8baf94f` | 🟢 red | #1 快照前 flush(engine)+ 快照已含重複不重拉(useStockStream / useGroupLiveAccums 各兩案)/ #2 側欄盤前篩選列不切組 / #3 GroupGridView→setTickView 登記兩案 / #5 route 測試 `_wait_until` poll 化 / #6 訂閱池不變補正控 / #7 `_tick_flush_secs == 0.1` 接線層 + close 不再送 / #8 丟包本窗計數 + 過窗重記兩案 |
| `64578727` | 🔴 fix | #1 `snapshot()` / `group_snapshot()` 取值前 `_flush_ticks()`(並取消在飛 timer)+ `stock-accum.ts::seqsByCode / isSeededDuplicate`(打包內含 `acc.seq` 的 ≤ acc.seq 項 = 快照已含重複 → 丟;rollover 型回退仍重拉)/ #2 `group === SCREEN_GROUP_NAME` 只換右欄 / #8 `WsBroadcaster.window_dropped` + 過窗重記印上一窗筆數 |
| `ccd39ed2` | 🔵 | #4 `visibleGroups` export、pill 清單改用同一份過濾(順帶 Nice #14 註解歸位);零行為 |

處置說明:#3 / #5 / #6 / #7 為測試面 finding,修法即測試本身(紅測試 commit 內 #3、#7 是 lock,首跑即綠;#5 / #6 是改寫既有測試)。
#8 的「`dropped` 掛 `/api/health`」**未採**:health 的 docstring 明文「刻意不含引擎健康度」,量改走 log(過窗重記印上一窗筆數)+ `window_dropped` 屬性;WARNING 仍含 `佇列滿` 子字串(CLAUDE.md §4 grep 判準不變)。
#1 前端規則的已知盲點(昨日恰好只有 `acc.seq` 筆的薄股跨日)寫在 `isSeededDuplicate` docstring,60 s 輪詢重播種一分鐘內修正。

## 2. 紅 → 綠

- 後端(`-k "flushes_pending or close_cancels_flush or window_count or window_total or TestStockWsView"`):**3 failed / 5 passed**
  (`test_snapshot_flushes_pending_ticks_first…` `assert [] == [('2317', 1), ('2330', 1)]`;`test_drop_warning_reports_window_count…` 第二則無「上一窗」;
  `test_drop_warning_first_of_window_then_window_total` `AttributeError: window_dropped`)→ 實作後三檔全量 **357 passed**。
- 前端(四檔):**4 failed**(`useGroupLiveAccums` 小幅回退案 / `useStockStream` 小幅回退案 / `StockPage` 盤前篩選列案 /
  `GroupGridView` 同一組不重送案 —— 最後一條紅因是測試自己少包 provider,修測試)→ 實作後十檔 **10 passed**。
- 刻意寫下即綠(lock):`test_prod_wiring_keeps_default_tick_flush_interval`、`test_close_cancels_flush_and_never_publishes_pending`、
  GroupGridView「掛載送成員、換組換集合、卸載送 []」、兩支「大幅回退(rollover 歸零)仍是跳號 → 重拉」。

## 3. 完成前 gate(全綠;`ccd39ed2` 工作樹)

| 指令 | 結果 | exit |
|---|---|---|
| `C:/side-project/copycat/.venv/Scripts/python -m pytest -q` | **3366 passed, 3 skipped**(222.59 s) | 0 |
| `… -m ruff check copycat tests` | All checks passed | 0 |
| `… -m pyright` | 0 errors, 0 warnings | 0 |
| `… -m copycat validate --run-five …/out/five_tigers --run-four …/out/four_tigers` | **42/42 PASS** | 0 |
| `npx vitest run`(frontend/) | **154 files / 2965 tests passed** | 0 |
| `npx tsc -b` | PASS | 0 |
| `npx eslint src` | PASS | 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | 僅 `StockPage.tsx:78` 基準既有複雜度,零新增 | 0 |

**收修後最終重跑(`8ac2ab81` 工作樹)**:`npx vitest run` **154 files / 2965 tests passed**(exit 0);`npx eslint src` 0;
`react-doctor --scope changed` 只剩 `StockPage.tsx:79` 基準既有複雜度(exit 0);ruff / pyright 0;
全量 `pytest -q` **3367 passed, 3 skipped**(221.73 s,exit 0)。
**rebase onto origin/master `33aba77e`(上游只動一行文件)後再重跑**:pytest 3367 passed / pyright 0 / ruff 0 / validate 42/42 /
vitest 2965 passed / tsc 0 / eslint 0(全部 exit 0)。
**二次 rebase onto origin/master `97ab0600`(上游 3 筆只動 `.claude/mod/group-grid-ticks/` 文件與證據檔,零衝突;新 session 接手收尾)後重跑(`385dc99f` 工作樹)**:
pytest **3367 passed, 3 skipped**(222.89 s)/ ruff 0 / pyright 0 / validate **42/42** / vitest **154 files / 2965 passed** / tsc 0 / eslint 0 /
react-doctor 僅 `StockPage.tsx:79` 既有基準(全部 exit 0)。之後唯一 commit `57ab085b` = `ws.py` 註解三行 + review JSON 追記(零行為),`ruff check ws.py` 0。

## 4. 真實環境

本批為 review 收修(時序 / 測試 / UI 一行守門),無新盤中判準;PR #187 原四判準(卡片同步動 / grep 佇列滿 / trace / UI 過目)不變,
#1 修後盤中可加驗:`grep "group-state?codes=" logs/server-*.log` 在 60 s 輪詢後**不應**緊跟單檔重拉(收修前每輪活躍檔各一發)。

## 5. Review(two-axis,fixed point `8d42098d`,reviewed head `ccd39ed2`)

- 標準軸 6 條(MED 2 / LOW 4):F-01 契約補句 / F-02 字面值斷言 / F-03 舊 poll 遷移 / F-04 warning 去重 / F-05 註解改述 → 修;F-06 否決(共用 helper 刻意)。
- spec 軸 5 條(MED 2 / LOW 3):F-01 窗到期在 publish 入口結算(#8 才算修完)/ F-02 close 斷言搬到 sleep 前(#7 突變殺)/ F-03 / F-04 / F-05 → 全修。
- 收修 commit:`03ed3227`(🟢 test)/ `d48713fc`(🔴 fix)/ `8ac2ab81`(🟢 docs)。收修後 gate:後端三檔 **358 passed**、ruff / pyright 0;前端六檔 passed、tsc / eslint 0;全量重跑見 §3 末列。
- 逐條原文與處置:`code-review-round-1.json`。
- review 後增量(收修三筆)main-agent 機械快篩:I-01 LOW(`window_dropped` 註解仍是結算搬到 publish 入口前的口徑)已修;記於 JSON `increment_screen`。
