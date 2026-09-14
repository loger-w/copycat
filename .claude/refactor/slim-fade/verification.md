# verification — refactor/slim-fade

2026-09-14。worktree `.claude/worktrees/refactor-slim-fade`,分支 `worktree-refactor-slim-fade`,merge-base `cda8b849`。
七筆 commit(PR head 8e0a2470):e70d1a52(fade 家族刪除)/ c5fc290d(A3 A4)/ 4556da30(change-spec)/ 9e389873(前端 knip A5–A7)/ d850eae1(@eslint/js chore A8)/ f8543dde(two-axis round-1 收修)/ 8e0a2470(artifacts)。(原寫「四筆 … 0b435f48」;0b435f48 於 §1.5 拆成 9e389873 + d850eae1,pr-230 review F-04 回校抬頭。)

## 1. 自動化 gate(auto-verify 表,全部在 worktree 內跑、用主樹 .venv;`import copycat` 實證指向 worktree 路徑)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| pytest | `.venv\Scripts\python -m pytest -q -p no:cacheprovider` | **3349 passed, 3 skipped**, 1 warning, 207 s | 0 |
| replay four | `python -m copycat replay --watchlist watchlists/four_tigers.json --data-dir <主樹 data> --out <scratch>` | 完成 | 0 |
| replay five | 同上 five_tigers | 完成 | 0 |
| validate(golden gate) | `python -m copycat validate --run-five <scratch>/five_tigers --run-four <scratch>/four_tigers` | **42/42 PASS** | 0 |
| tsc | `npx tsc -b`(frontend/) | 無輸出 | 0 |
| eslint | `npx eslint src` | 無輸出 | 0 |
| vitest | `npx vitest run --reporter=dot` | **Test Files 156 passed / Tests 3074 passed** | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found! | 0 |

pytest 母數對照:merge-base cda8b849 **3635** collected → HEAD **3352**(3349 passed + 3 skipped);差額 283 = 25 支 fade 測試檔 264 + `test_cli_fade` 2 + `test_market_features` 8 + 特徵化測試移除的 9 條(quantiles 6 / fmt_num 1 / fmt_quantiles 1 / fade loader 1)。(pr-230 review F-01 回校:原寫「master 3566」是 09-09 記憶值,base 以 `git archive cda8b849` 實跑 `--collect-only` 得 3635;27 個刪檔零 parametrize,def 計數 3286 → 3003 同差 283。)
vitest 母數 3069(memory 09-09)→ 3074:本批動到的測試檔只有 `App.memo.test.tsx`(註解)與 `river-test-fixtures.ts`(一個 export 關鍵字),零 `it(` / `describe(` 增刪,母數不受影響;差額是主線 09-09 後新增。

中途紅過兩次、皆為刪除範圍未收齊,不是行為改動:
- pytest collection ERROR `tests/test_fade_tp.py` / `test_fade_trigger.py`(tests 根層兩檔漏刪)→ 補刪。
- tsc TS6196 `_KindDomainsMatch is declared but never used`(knip 拿掉它的 export;它是 TradeKind ⇄ PositionKind 型別機驗,靠 export 存活)→ 恢復 export。

## 1.5 two-axis round-1 收修後重跑(f8543dde;收修只動註解 / 檔尾空行 / skill 文字 / commit 拆分)

| gate | 結果 | exit |
|---|---|---|
| tsc | 無輸出 | 0 |
| eslint | 無輸出 | 0 |
| vitest | Test Files 156 passed / Tests 3074 passed | 0 |
| 後端 parity(11 支直讀前端原始碼的測試) | 538 passed | 0 |

後端其餘未動(自 e70d1a52 / c5fc290d 全量 pytest 3349 後,只改 .claude/skills 文字),不重跑。
commit 拆分:0b435f48 → 9e389873(refactor,knip)+ d850eae1(chore,@eslint/js),`git reset --soft` 於未推送分支。

## 2. 行為不變證據(對照 change-spec 五條承諾)

1. server 啟動路徑:`copycat/server/**` 零 diff(`git diff cda8b849...HEAD --stat -- copycat/server` 空)。
2. CLI:`sub.add_parser` 21 → 16、`if args.command ==` 20 → 15,兩者都恰減 5(五個 fade-*);其餘 parser / dispatch 逐字未動。
3. validate 42/42 與 master 同(replay / engine 未動;A4 只刪零 caller 方法)。
4. `backtest/report.py` import `fmt_cell` 不變;特徵化測試 `test_tday_fmt_semantics` 斷言值逐字沿用。
5. 前端:tsc / vitest 3074 全綠;拿掉 export 的符號皆仍在原檔使用(knip 判定 + tsc 未報 unused-local,唯一例外 `_KindDomainsMatch` 已恢復)。

## 3. 真實環境

本批不改任何 runtime 行為、不需重啟 prod(prod 跑 6cbf7cdd = 本分支 merge-base 之前的 code HEAD,merge 後也不必重啟)。
真實環境抽查改在 merge 後主樹做:`python -m copycat --help` 列 16 個子指令且無 fade-*;`python -m copycat validate` 於主樹 out/ 重跑一次。

## 4. 未做 / 知情

- `graphify-out/` 未 `--update`:每次 PR 重寫 15 MB 圖檔是盤點 C3 待拍板項,本批刻意不動(見收尾回報)。
- 前端 coverage 未跑(專案未裝 @vitest/coverage-v8,不順手裝)。
