# /bug breakeven-avg-source-prod-chain — spec(originating bug description)

來源:`pr-118-review.md` F-01(CRITICAL)/ F-02(HIGH);2026-08-27 11:2x prod `51b93006` 實證。

## A. `avg_source="broker"` 在 prod 是死的

- 症狀:`curl localhost:8721/api/capital/positions` 三檔持倉(2484 cash / 3026 margin / 6715 margin)`avg_source` 全 `null`,
  `today_qty` 有值(1 / 1 / 0)。前端 `positionEcon` `case null` 走修前口徑 → PR #118 宣稱修掉的「打平線落地跳格 /
  損益比群益 APP 少一筆買費」在 prod 原封不動。
- 根因:`avg_source="broker"` 唯一寫點在 `store.apply_profit_rows`,該方法 `copycat/` 零 caller(只有測試呼叫);
  prod 真鏈 `client._on_profit_complete` 就地回填 pending 列 `p.avg_price = r.avg_price`,沒寫 `avg_source`。
- 要求:
  1. `_on_profit_complete` 回填 `avg_price` 時同時寫 `avg_source = "broker"`。
  2. 死路徑 `apply_profit_rows` 刪除,`broker` 寫入點收斂到真鏈一處;store 側測試改吃真鏈產物。
  3. CLAUDE.md §4 契約條產生點改正(F-03)。
  4. 既有行為白名單:`set_positions` 沿用邏輯、`_apply_fill_locked` 的 `fill` / 加碼沿用、`_with_today_qty_locked` 逐字不動;
     `_on_profit_complete` 的 kind=None / 種類不符 / 查無股號三個分支不動。
- 驗證 seam:`tests/capital/test_client.py::test_balance_chain_marks_avg_source_broker`(真鏈 balance → profit → OI → finalize)。
  真實環境:prod 重啟後 `curl /api/capital/positions` 持倉列 `avg_source == "broker"`;首筆成交打平線不跳格。

## B. 前端 `positionEcon` switch 無 default

- 症狀:舊後端 payload 兩欄同缺(`avgSource` 執行期 `undefined`)→ `cost` 未賦值 → pnl / breakEven NaN 印到四處、打平線消失。
- 要求:`default` 併進 `case null` 分支(退回修前口徑,不退成假數字),與 `todayQty` 缺欄退 0 同一方向。
- 驗證 seam:`frontend/src/lib/ladder-position.test.ts`「payload 兩欄同缺 → 與 null 同口徑,不印 NaN」。

## 非目標

- 不動空方均價語意(仍無真樣本,next-time 08-26 節)。
- 不處理 pr-118-review 的 Should F-05(fill_date 跨日重播)與 11 條 Nice;#116 F-01 next-time 錯位一併順修(同檔一處,勾銷尾巴搬回原條目)。
