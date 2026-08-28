# verification — bug/futures-tail-index-zero-bar(2026-08-28)

分支 commit(引「第 n 筆 + subject」):第 1 筆 `test(frontend): gate 5 尾根遇 0 價 bar 應跳過…(紅先行)` →
第 2 筆 `fix(frontend): 期貨分時 gate 5 的尾根跳過 0 價 bar,與 adapter 同一把尺…` →
第 3 筆 `refactor(frontend): 「哪根 1K 畫得出來」收成 adapter 單一定義 drawableIndexOf…`(review S F-01 / F-02)→
第 4 筆 `fix(frontend): live 點入口「有沒有資料」改與 tailIndex 同一把尺…`(review Spec P3)→ 第 5 筆 artifacts。

## 1. 自動化 gate(worktree `.worktrees/a3-tail-zero-bar/frontend`,`npm ci` 自裝 node_modules)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行(第 1 筆,fix 前) | `vitest run FuturesChart.test.tsx -t "0 價 bar"` | **1 failed**(`expected 3 to be 2`:舊碼 tailIndex 取 10:05 → lag 1 → 架橋) | 1 |
| 綠(第 2 筆後) | `vitest run FuturesChart.test.tsx` | 55 passed | 0 |
| 收修後同檔 + adapter | `vitest run FuturesChart.test.tsx futures-accum-adapter.test.ts` | 78 passed | 0 |
| 全量(最終樹) | `vitest run` | **2875 passed**(152 files,29 s) | 0 |
| 型別 | `tsc -b` | 無輸出 | 0 |
| lint | `eslint src` | 無輸出 | 0 |
| doctor | `react-doctor@latest --scope changed --no-telemetry` | Scanned 3 files,No issues found | 0 |
| 後端 | 未動 → 不跑 | — | — |

## 2. 反向驗證(mutation)

- 第 2 筆:reviewer(Standards sub-agent)移除 `if (b.c <= 0) continue;` → 新案 FAIL(`mainLineXs 3 ≠ 2`),已還原。
- 第 4 筆:拆 commit 的中間態(gate 入口換回 `last === undefined`)= 突變體 → 新案「slice 整段 0 價」FAIL(`Unable to find … 無分時資料`,
  舊入口把 live 點塞進 accum、畫出一張只有一顆孤點的圖);還原後 78 passed。

## 3. 白名單逐條(change-spec §3)

| # | 既有行為 | 證據 |
|---|---|---|
| 1 | 五道 gate 判準逐字不動 | diff 只動尾根定義與入口的「有沒有資料」判準;既有 gate 2–5 十條測試綠 |
| 2 | `anchorDate` 不套同尺 | 第 4 筆 docstring 明寫;`anchorDateOf(last.t)` 零 diff |
| 3 | adapter 對 `h`/`l` ≤ 0 以 `c` 代 不動 | `futures-accum-adapter.ts` 該兩行零 diff;adapter 23 條測試綠 |
| 4 | 門檻 3 不動 | `FUT_LIVE_LAG_MAX` 零 diff;邊界測試(差 4 擋 / 差 3 放)綠 |

## 4. 行為改動(🔴 兩筆)

1. 尾根跳過 0 價 bar(第 2 筆)→ 真缺 N 根照印、不架橋。
2. live 點入口改 `tailIndex === null`(第 4 筆)→ 整段 0 價 slice 不畫孤點(core 印「無分時資料」)。

## 5. 真實環境

純前端判準改動、TC4 0 價 bar 是偶發(08-28 11:25 實抓 TXF allday 4720 根零 0 價),無法即時構造;由單元測試 + mutation 承擔。
prod 重啟後看:期貨 tab 分時圖與改前一致(同日無 0 價 bar 時零差異)。

## 6. 留尾

- F-03:測試期望值由同源常數算回(整檔慣例),要收整檔收 → next-time。
- 中段 0 價斷格架橋(core 單條 polyline)仍未涵蓋(§2.2 SP1 既有留尾)。
