# fix/pr-152-review-followups — /pr-review #152 十四條收修(2026-08-30)

分支自 master `2873e004`;worktree `../copycat-wt-pr152-followups`。來源 = `docs/superpowers/specs/pr-152-review.md`
發現總覽 F-01 ~ F-16(零 Must / Should;Nice 14、參考用 2)。user 拍板「直接全修」;四條 ask-user 取建議選項:
F-02 走 (a) 對稱沖銷、F-08 做、F-11 DEBUG 保留 + 每 (股號, 交易日) 一次 INFO、F-14 做(檔不在原 PR,順手併)。
F-15 不動(既有刻意 + next-time F-09 已記)、F-16 補一句註解。

## 紅先行(diagnosing-bugs Phase 5 seam = tests/capital + frontend lib/component tests)

| finding | 測試 | 修前 |
|---|---|---|
| F-02 | `test_store.py::test_borrowless_sell_offsets_cash_long_first_then_opens_short_with_residue` | 紅(cash 5 + 無券賣 1 → cash 仍 5、另開 daytrade_sell −1) |
| F-08 | `test_store.py::test_borrowless_buy_side_fill_does_not_count_into_daytrade_today_qty` | 紅(B08 後快照落地 today_qty 0 ≠ 1;第一版未含快照步驟不紅 —— finding 顯形點是重算時刻) |
| F-11 | `test_client.py::test_borrowless_short_row_logs_info_once_per_stock_and_day` | 紅(0 筆 INFO) |
| F-14 | `close-order.test.ts` closeKindLabel 兩條 + `CapitalPositionsList.test.tsx` 無券空單確認窗 | 紅(`closeKindLabel is not a function` / 找不到「買回 1 張(現股)」) |
| F-04 | `test_balance.py` 加 `levelno == DEBUG` | 綠(強化既有斷言;debug→info 突變現在會紅) |
| F-10 | `test_capital_api.py` 多種 margin 列 | 綠(mutation guard:route 掉 kind 才紅) |
| F-13 | `test_models.py::test_close_kind_wire_parity_with_frontend` | 綠(parity 現成立;單邊收窄才紅) |

反向驗證:`git stash push -- copycat/capital/store.py copycat/capital/client.py` → F-02 / F-08 / F-11 三條紅;pop → `-k borrowless` 8 passed。

## 修法落點

- F-01 `models.py` 兩處註解;F-02 / F-08 `store.py`;F-11 / F-12 `client.py`;F-14 `close-order.ts::closeKindLabel`(鏡像 `_CLOSE_MAP`)+ `CapitalPositionsList.tsx` 反向單列;
  F-05 `types.ts` 註解;F-16 `balance_rows.py` 註解;F-03 `docs/next-time.md`;F-06 `.claude/bug/borrowless-short-calibration/verification.md`;F-09 `CLAUDE.md`;F-07 `test_client.py` / `test_store.py` import 併模組級。
- 報告本體 `pr-152-review.md` / `.audit.md` 自 repo root 移入 `docs/superpowers/specs/`。
