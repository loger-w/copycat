# verification — fix/pr-152-review-followups(2026-08-31)

worktree `C:/side-project/copycat-wt-pr152-followups`;分支自 master `2873e004`,收尾前 rebase 到 origin/master `640add7b`(5 筆重放無衝突,
lockfile 上游未動);pytest 用主 tree `.venv`。commits(rebase 後):`13da057c` test 紅先行 → `789ec54e` fix → `0a033563` docs →
`21082372` review 收修 fix → `c346f08a` review 收修 docs → artifacts chore。

## 紅先行 / 反向驗證

- 修前紅:`test_store::test_borrowless_sell_offsets_cash_long_first_then_opens_short_with_residue`(F-02)、
  `test_client::test_borrowless_short_row_logs_info_once_per_stock_and_day`(F-11)、前端 `close-order.test.ts` closeKindLabel 兩條 +
  `CapitalPositionsList.test.tsx` 無券空單確認窗(F-14)。`test_borrowless_buy_side_fill_does_not_count_into_daytrade_today_qty`(F-08)
  第一版不紅 —— B08 拒套後 today_qty 要到下一輪快照落地才重算;補 `set_positions` 一步後紅。
- 反向驗證:`git stash push -- copycat/capital/store.py copycat/capital/client.py` → 三條紅(F-02 / F-08 / F-11);pop → `-k borrowless` 8 passed。
- 守門型(修前就綠、突變才紅):F-04 levelno DEBUG、F-10 margin 共存列、F-13 `test_position_kind_subset_of_trade_kind`、
  review 收修 `test_close_kind_label_parity_with_frontend`、F-11 跨日重印(monkeypatch `_today_ymd`)。

## 自動化 gate(rebase 後 HEAD `c346f08a`,依序不並跑)

| gate | 結果 | exit |
|---|---|---|
| vitest 全量 | Test Files 152 passed / 1 failed;Tests **2898** passed / 1 failed(`App.memo.test.tsx` 換主檔 railCtx)→ 單檔重跑 **8/8 passed** | 0(重跑) |
| tsc -b / eslint src | 無輸出 | 0 / 0 |
| react-doctor --scope changed | ✔ No issues found! | 0 |
| ruff / pyright | All checks passed! / 0 errors | 0 / 0 |
| pytest 全量 | **3203** passed, 1 skipped in 205.36s(+6:F-02 / F-08 / F-11 / F-13 / parity / 跨日) | 0 |
| copycat validate | 42/42 PASS(out/ 自主 tree 複製) | 0 |

rebase 前那一輪(HEAD `792b57a4`)同組 gate:pytest 3197 / vitest 2892 passed + `App.test.tsx` ×3 / `App.memo.test.tsx` ×1 紅 → 單檔重跑 61/61 綠。
兩輪的 vitest 紅都落在 ops-discipline 記錄的「剛 `npm ci` 的 worktree App 級 lazy `waitFor` flake(08-30 5/5、stash 全改動仍紅)」同三檔樣態,
本分支對 `App*` 零 diff;依該記錄歸環境,未再走 stash 差分 / 主 tree 對照兩步(已有 5/5 實證)。
targeted:`tests/capital + test_capital_api` 493 passed;`close-order.test / CapitalPositionsList.test` 25 passed。

## 真實環境節

真錢路徑(無券賣沖現股多單 / 確認窗文案 / 每日一次 INFO)本機無法重走(08-31 週一盤前,群益 COM 未登入);以下判準給 prod 重啟含本 PR 後:
1. 持現股多單時閃電梯選「無券」送賣 1 張 → 部位面板現股列張數立即 −1、**不出現**「無券 −1」列;快照落地後同(F-02)。
2. 重啟後帶無券空單開機 → log 一行 `庫存段 <股號> 現股負股數 −n 張 → 無券空單(daytrade_sell),平倉會送現股買`,同日不重印、次日再印一次(F-11)。
3. 無券空單按平倉 → 確認窗「種類:無券」「反向單:買回 n 張(現股)」;現股 / 融資 / 融券列確認窗文字**不變**(F-14 收窄後)。
4. `grep 成交未樂觀套用` 只剩「無券買向」字樣(F-12)。
5. 未改功能抽 2:現股買沖無券空單(`test_borrowless_short_buyback_fill_nets_to_zero_without_phantom_rows`)、多方 today_qty
  (`test_today_qty_is_per_kind_and_zero_for_futures`)—— 皆在 493 綠內。

## Blast radius

- `_apply_fill_locked` 新對稱段只在 `market == "sec" and kind == "daytrade_sell" and signed < 0` 進入;與買向段互斥(kind 單值);`applied_*` 在兩段前結清。
- `_today_net_lots_locked` 只多一條 `kind == "daytrade_sell" and buy_sell == "B" → continue`;其他 kind 桶零變動。
- `_on_balance_complete` 新 INFO 在 `_log_chain_stage` 之後、不改 pending 流程;`_short_row_logged` 換日清。
- `closeKindLabel` 只被 `CapitalPositionsList` 讀;`CLOSE_KIND` 由 `test_close_kind_label_parity_with_frontend` 鎖住與 `_CLOSE_MAP` 同值。
- `KIND_ORDER`(F-15)零 diff。
