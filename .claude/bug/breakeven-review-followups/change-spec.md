# fix/breakeven-review-followups — change spec

來源:`docs/superpowers/specs/pr-119-review.md` F-01 ~ F-07(全 Nice,全 auto-fix;三輪 pr-review 修復鏈第二輪)。
小活分流:測試 / 文件 / 一行前端歸一,無 API、無 migration。

## 現況 vs 目標

| Finding | 現況(PR #119 後) | 目標 |
|---|---|---|
| F-01 | 真鏈測試只斷 avg_price / avg_source;pnl_base / pnl_base_price / pnl_cost 映射零覆蓋 | `test_balance_chain_marks_avg_source_broker` 補三行斷言 |
| F-05 | 25 欄字面複製六份(test_client ×5、test_fill_latency ×1),成交價金落 [11]、無 [25] | 30 欄 `tests/capital/profit_rows.py::PNL_3357_MARGIN` + `pnl_variant` 按欄變異;kind=None 第二輪 [25] 改未對映碼 |
| F-02 | `?? null` 只擋 nullish;值域外字串 → switch 三 case 全不中 → cost 未賦值 → NaN | 白名單歸一;`AVG_SOURCES as const` 與 `AvgSource` 同源(review S-2) |
| F-03 | CLAUDE.md §4 紅燈判準「持倉列 avg_source 非 null」對期貨列必誤報 | 「證券列非 null;fut 列恆 null 既知語意」 |
| F-04 | test_store carry 測試重複斷言 + 函式內冗餘 import | 刪 |
| F-06 | `store.positions()` docstring 只開 pending 列一個例外 | 補 set_positions carry-over / `_stale_fut_positions()` 已發布物件、`p is prev` 前提 |
| F-07 | 舊 verification §3 B / §4 寫「default」與出貨 code 相反;三筆收修不在表 | 改最終形態 + 補三列 |

## Caller map(前端 F-02 唯一行為改動)

| 讀者 | 影響 |
|---|---|
| `lib/ladder-position.ts::positionEcon` 的 `avgSource` 歸一 | 合法三值(`broker` / `fill` / `null`)逐 bit 不變;`undefined` 仍 → null;**值域外字串** NaN → null 口徑 |
| `positionEcon` caller:`PriceLadder.tsx`、`lib/position-summary.ts` | 合法輸入不變 |
| `types.ts::AvgSource` 讀者(`CapitalPosition.avg_source`、ladder-position) | 型別值域同前(由陣列推導);加值改一列 |

## 既有行為白名單(不得變)

1. `positionEcon` 對 `broker` / `fill` / `null` / `undefined` 四種輸入的輸出逐 bit不變(vitest 既有 38 條全綠)。
2. switch 本體不動、無 `default`、exhaustive(加值仍 TS2454)。
3. 後端零行為改動(只動 docstring / 測試 / 文件);`parse_profit_line`、`_on_profit_complete` 不在 diff。
4. `test_store` 只刪重複斷言與未用 import,合併後的斷言強度不降。
5. 紅先行:F-01 斷言先紅(`pnl_cost 0.0 == 451650.0`)再換 fixture;F-02 vitest 先紅(1 failed)再改歸一。

## 驗證 seam

- `tests/capital/test_client.py::test_balance_chain_marks_avg_source_broker`(三欄映射)、`::test_profit_row_unknown_kind_skipped_keeps_previous_broker_avg`([25] 可達性:突變 [25]="2" 紅)。
- `frontend/src/lib/ladder-position.test.ts`「avg_source 值域外字串 → 歸一成 null」。
- 真實環境:無 UI 變更;08-28 `curl /api/capital/positions` 證券列 `avg_source == "broker"`(F-03 判準最終版)。
