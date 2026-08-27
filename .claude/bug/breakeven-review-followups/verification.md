# fix/breakeven-review-followups — verification

主 tree 直做;branch 自 master `7f4bc98d` 開。來源 `docs/superpowers/specs/pr-119-review.md` F-01 ~ F-07(全 Nice,
全 auto-fix);三輪 pr-review 修復鏈第二輪。無 UI 變更、無 API、無 migration。

## 1. 紅先行

- F-01(`15fcfd09` 前半):`test_balance_chain_marks_avg_source_broker` 補三欄斷言 → 紅
  `AssertionError: assert (12345.0 == 12345.0 and 156.0 == 156.0 and 0.0 == 451650.0)` —— 正是 F-05 指的 25 欄 fixture
  成交價金落 [11]、`_PNL_IDX_COST` 取 [12] 得 0;換 30 欄 fixture → `tests/capital` 402 passed。
- F-02(`9e8de3a1`):vitest 「avg_source 值域外字串」case → `1 failed | 38 passed`;`ce05f592` 白名單歸一 → 39 passed。

## 2. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `15fcfd09` | test | F-01 三欄斷言;F-05 fixture 30 欄常數 + kind=None 第二輪 [25]=3;F-04 test_store 去重 |
| `9e8de3a1` | test | F-02 紅先行 |
| `ce05f592` | 🔴 | F-02 `positionEcon` 白名單歸一 |
| `11f11923` | chore | F-03 CLAUDE.md §4 / F-06 store docstring / F-07 舊 verification |
| `e084b1e2` | test | review 收修:fixture 抽 `tests/capital/profit_rows.py`(六份 25 欄全清)、`pnl_variant`、撞名、`: str` |
| `196b1c89` | 🔵 | review 收修:`AVG_SOURCES as const` 推導 `AvgSource`,白名單吃同一陣列 |
| (本檔) | chore | artifacts + next-time(App.test 負載 flake) |

## 3. 反向 / 可達性驗證(mutation 級)

| 突變 | 紅的測試 |
|---|---|
| F-01 斷言存在、fixture 仍 25 欄 | `test_balance_chain_marks_avg_source_broker`(`0.0 == 451650.0`) |
| kind=None 第二輪 [25]="3" → "2"(對映 margin) | `test_profit_row_unknown_kind_skipped_keeps_previous_broker_avg`(999 蓋掉 150.55)—— 證明 [25] 備援分支現在**走得到** |
| F-02 歸一改回 `?? null`(= 9e8de3a1 當下) | vitest 值域外字串 case NaN |

## 4. 白名單核對(change-spec §白名單;主 session)

1. 合法四輸入逐 bit 不變 —— `ladder-position.test.ts` 既有 38 條 + `position-summary.test.ts` 全綠(72)。
2. switch 無 default、exhaustive —— diff 未動 switch;`AvgSource` 由 `AVG_SOURCES` 推導,tsc 0。
3. 後端零行為改動 —— `copycat/` 只有 `store.py` docstring。
4. `test_store` 合併後斷言 `c.avg_price is None and c.avg_source is None` 保留(強於被刪的那行)。
5. 紅先行兩條見 §1。

## 5. pr-119 finding 對帳(Spec 軸 + 收修後)

F-01 PASS / F-02 PASS(S-2 同源後)/ F-03 PASS / F-04 PASS / F-05 PASS(S-1 後 `grep -rn "468000,464000" tests/` = none)
/ F-06 PASS / F-07 PASS。

## 6. 自動化 gate(最終 HEAD,主 tree)

```
3132 passed, 1 warning in 212.29s (0:03:32)   # pytest 全量
All checks passed!                             # ruff
0 errors, 0 warnings, 0 informations           # pyright
42/42 PASS                                     # copycat validate
Test Files 152 passed / Tests 2848 passed      # vitest 全量(單獨跑)
tsc exit=0 / eslint exit=0
✔ Scanned 3 files ✔ No issues found!           # react-doctor --scope changed
```
**vitest 全量與全量 pytest 並跑時 `src/App.test.tsx` capital WS 那條 3/3 紅(1.8 s > waitFor 1 s)、單獨跑 3/3 綠** ——
負載型 flake,與本 diff(純函式)無關,已記 next-time(exceptions.md 條文:記錄 + 重跑一次)。

## 6a. two-axis review round 1(`code-review-round-1.json`)

Standards 6 條(P2×2 / P3×4,含鐵則 B 併筆)+ Spec 2 條(P2 / P3),零 P1;全部收修(`e084b1e2` / `196b1c89` / commit 拆分)。
增量 diff 由主 agent 機械快篩(§6 全套 gate 在收修後 HEAD 重跑)。

## 7. 真實環境

- 無 UI 變更、後端零行為改動;prod 不需為本輪重啟(下次重啟自然帶上)。08-28 `curl /api/capital/positions`
  證券列 `avg_source == "broker"`(F-03 判準最終版;期貨列 null 既知)。
