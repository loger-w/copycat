# verification — fix/borrowless-short-calibration(2026-08-30)

worktree `C:/side-project/copycat-wt-borrowless-short`,自 master `09cc3e63`;pytest 用主 tree `.venv`(Python 3.13)。
commits:`fc809e83` test 紅先行 → `1ae9c2ad` fix → `e5e6fe1e` docs chore → review 收修(code)→ 收修 docs + artifacts chore。

## 自動化 gate(auto-verify;專案 CLAUDE.md §1)

| gate | 指令(worktree 根 / frontend) | 結果 | exit |
|---|---|---|---|
| Phase 1 loop(修前) | `.venv/Scripts/python -m pytest -q -p no:cacheprovider tests/capital/test_store.py -k borrowless` | **2 failed, 1 passed** in 0.19s(today_qty 0≠1;ValueError 無法平倉) | 1 |
| Phase 1 loop(前端,修前) | `npx vitest run src/lib/ladder-position.test.ts` | **1 failed** \| 39 passed(breakEvenMilli 510201.8 ≠ 510969.6,差 767.8 毫元) | 1 |
| 反向驗證 | `git stash push -- copycat/ frontend/src/lib/ladder-position.ts` → 同兩條 loop → `git stash pop` | stash 後後端 **5 failed** / 2 passed、前端 **1 failed**;pop 後 412 / 40 passed | — |
| pytest capital | `pytest -q -p no:cacheprovider tests/capital tests/server/test_capital_api.py` | 487 passed | 0 |
| pytest 全量 | `pytest -q -p no:cacheprovider` | 3176 passed, 1 skipped in 198.03s | 0 |
| ruff | `ruff check copycat tests` | All checks passed! | 0 |
| pyright | `pyright` | 0 errors, 0 warnings | 0 |
| validate | `python -m copycat validate`(out/four_tigers + five_tigers 自主 tree 複製) | 42/42 PASS | 0 |
| vitest 全量 | `npx vitest run` | Test Files 153 passed;Tests 2886 passed | 0 |
| tsc | `npx tsc -b` | (無輸出) | 0 |
| eslint | `npx eslint src` | (無輸出) | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | ✔ No issues found! | 0 |

備註:第一次 vitest 全量與 3 分鐘 pytest 全量**並跑**時 2 failed;單獨重跑 2886 全綠(memory `pr-review-fixes-three-rounds-shipped`
已記「vitest 與 pytest 全量不並跑」,本次再證一次)。

## 真實環境節(/bug 特有:重走原始重現步驟)

原始重現 = 08-28 prod 一筆**真錢**無券當沖(賣 8358 @512 → 買回 @523)。08-30 週日 TC4 / 群益 COM 離線,且 `--verify` server
只 fake TXO source、不 fake capital(`copycat/server/__main__.py` :8),**無法在本機重走**。替代 = 把 08-28 的實錄逐列灌進真鏈:

- `tests/capital/test_client.py::test_borrowless_short_profit_row_labeled_cash_pairs_with_daytrade_sell_row`:
  `CapitalClient` + `FakeCom`,餵 `RAW_T_BORROWLESS_SHORT`(= log :2425 整列去敏)→ 損益列標籤「現股」(= :2427 沒印種類不符)
  → 落地列 `kind=daytrade_sell / qty=-1 / avg_price=512 / avg_source=broker`、無「種類不符」log、無 cash 列。
- `tests/capital/test_store.py::test_borrowless_short_*` 三條 + `test_cash_buy_offsets_borrowless_short_first_then_opens_long_with_residue`:
  reply `S08`(= :2417 成交)→ 負列快照 → today_qty 1 / 平倉組出 `buy cash 1` / `B00` 回補(= :3650)歸零無幽靈列。
- Happy:上述;edge ≥ 2:部分沖銷(空 2 買 1 → -1 留、無 cash 列)、餘量開多(再買 3 → cash +2 @523 fill)、無券**買向** B08 不套 + WARNING、
  負融資列仍鎖 + WARNING;未改功能抽 2:`test_short_sell_fill_is_negative_lots_under_short_kind`(融券路徑)、
  `test_today_qty_is_per_kind_and_zero_for_futures`(多方 / 期貨 today_qty)—— 皆在 487 綠內。

**prod 判準(user / agent 於下一筆無券當沖,prod 重啟含本 PR 後)**:
1. log:無券賣成交那行印 `成交樂觀套用部位: seq=… stock=<股號>`(修前是「成交種類 '無券' 不在樂觀套用表」);損益段印
   `損益列回填 <股號> kind=cash 部位=daytrade_sell avg=…`;**不得**出現「方向記空、平倉暫鎖」(現股列)或「profit row 種類不符」。
   (review F-03 後 parser 那行是 DEBUG,prod INFO 看不到;`grep "balance line 負股數"` 對現股列 0 筆是預期。)
2. `curl -s localhost:8721/api/capital/positions`:該列 `"kind":"daytrade_sell"`、`"qty":-1`、`"today_qty":1`、`"avg_source":"broker"`。
3. 畫面:閃電梯 / 單檔 header / 自選 chip 部位標籤印「無券」;部位面板該列種類欄印「無」、平倉確認窗「種類」列印「無券」
   (Spec F-01);平倉鈕可按,POST body 帶 `"kind":"daytrade_sell"`,送出的是現股買(audit `trade_kind:"cash"`, `buy_sell:"buy"`)。
4. 買回成交後 positions 立即歸零(不出現 `8358 cash +1` 幽靈列);快照落地後仍為零。
5. 打平線:比 08-28 同價位往有利側移約 0.77 元(0.15% vs 0.3%)。
6. 留尾:`損益列回填 8358 kind=cash avg=…` 那行的 avg 是否 = 賣出價 → 決定倉位線語意(next-time 08-26 節)。

## Blast radius

- `_FILL_KIND` / `parse_balance_line` 無 store / balance 之外的 caller(grep copycat tests)。
- `position_for(kind)` 放寬到 `TradeKind`;review Spec F-01 後 wire 兩端(`server/capital_api.py::PositionCloseBody.kind`、
  `models.PositionCloseRequest.kind`)同放寬 —— 唯一外部 caller 就是 close route,四值全部進得來;`_CLOSE_MAP` 對 `(daytrade_sell, True)`
  無鍵 → 正向 daytrade_sell 列(不可達)仍 `ValueError` → `_close_blocked` → 403 `ORDER_BLOCKED` 不猜單種(pr-152 review F-06 校正:原寫 400)。前端 `PositionKind` 型別讀者:`close-order.ts`(KIND_TEXT / kindOf)、
  `types.ts::CapitalCloseBody.kind`;`grep -rn PositionKind frontend/src` 無第三處。
- 前端 `kind === "cash"` 假設:只有 `positionEcon` 一處與稅相關(已改);`PriceLadder.tsx:77` 是交易別 pill 樣式,與部位無關。
- `today_qty` 讀者:`PriceLadder.tsx:148`、`position-summary.ts:149` 直傳 `positionEcon`,無第二條算式。

## Round 2:review 收修 + rebase 到 origin/master 25312d79 後(2026-08-30)

收修 commit `058e95f5`(rebase 後 SHA);分支 5 筆重放無衝突。依 branch-lifecycle 收尾節 2 重跑自動化節(依序,不並跑):

| gate | 結果 | exit |
|---|---|---|
| vitest 全量 | Test Files 153 passed;Tests **2893** passed(含 close-order 三條新測、無券空單 econ 一條) | 0 |
| tsc -b / eslint src | 無輸出 | 0 / 0 |
| react-doctor --scope changed | ✔ No issues found! | 0 |
| ruff / pyright | All checks passed! / 0 errors | 0 / 0 |
| pytest 全量 | **3177** passed, 1 skipped in 191.43s(+1 = `test_close_body_kind_daytrade_sell_sends_cash_buy`) | 0 |
| copycat validate | 42/42 PASS | 0 |

收修前中途的一輪全量(rebase 前、與 pytest 並跑)已作廢不採計;上表為 rebase 後單獨依序跑的唯一一輪。
