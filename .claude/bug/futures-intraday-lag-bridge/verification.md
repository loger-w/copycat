# bug/futures-intraday-lag-bridge — verification

分支 `fix/futures-intraday-lag-bridge`(自 `a26b0410` master 切出)。只動 `frontend/src/components/futures/FuturesChart.tsx` + 其測試。

## 1. commits

| sha | 類 | 內容 |
|---|---|---|
| `e6fbcd5c` | 🟢 red | gate 5 紅測試 + 兩個對照組(TMF 空檔 / 常態落後) |
| `1903eae2` | 🔴 fix | `FUT_LIVE_LAG_MAX` / `tradeSlotOf` / gate 5 / 回補提示一行 |
| `7e8ac3a5` | 🔴 fix | review 收修:SP2 同錨定日守門 / SP4 整分邊界 + 門檻 5 / ST1 邊界案 / ST4 提示併模式列 / 文案「根」 |
| `db804b87` | 🔵 refactor | `hhmmOf` 共用(ST3) |

## 2. 紅 → 綠 → 反向驗證

- 紅態(`e6fbcd5c`):`npx vitest run src/components/futures/FuturesChart.test.tsx -t "gate 5"` → `1 failed`(`expected 3 to be 2`:主線多出 live 點 = 架橋)。
- 綠態(`1903eae2`):同指令 `1 passed`;全檔 40 passed。收修後(`db804b87`)全檔 **42 passed**(含 ST1 邊界案、SP2 前一場次案)。
- **反向驗證**:`git stash push -- FuturesChart.tsx` → 同指令 **1 failed** → `git stash pop` → **1 passed**。

## 3. 完成前 gate(全綠)

| 指令 | 結果 |
|---|---|
| `npx tsc -b`(frontend/) | PASS(exit 0) |
| `npx vitest run`(frontend/,最終樹 `db804b87`) | **141 files / 2679 tests passed** |
| `npx eslint src`(frontend/,改動兩檔) | PASS |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found |
| 後端 | 零改動(未跑 pytest;`docs/next-time.md` 純文件) |

## 4. 真實環境(/bug 特有 = 重走原始重現步驟)

原始步驟不可控(TC4 間歇忙碌),以兩層取證代替:
- **prod 資料面**(舊碼 8f8ce439,bars 路徑同):08-24 log TXF 69 次 1K timeout 全為週日歷史段探測、當日段 timeout 0 次;
  01:46 當下序列尾根 = 牆鐘、5 日零缺格;背景輪詢 `bars_lag_poll.py`(唯讀 GET / 20 s)守夜,截至 01:52 `lag_min ≤ 1.1`、`gaps=0`
  (證據:scratchpad `bars_lag.log`;若抓到 lag 事件會記在本檔 §6)。
- **畫面面**:fake clock + 真元件的 loop 即是重現(資料落後成交 90 分 → 舊碼架橋、新碼止於資料尾 + 提示「分時資料落後 90 分(TC4 回補中)」)。
  prod 重啟 + `npm run build` 後由 user 過目:下次遇到分時圖停住時,圖上方模式列下應出現該提示而不是一條直線。

## 5. 白名單(既有行為)

| # | 既有行為 | 核對 | 結果 |
|---|---|---|---|
| W1 | 四道 live gate 判準逐字不動(死區 / 錨定日 / 時鐘落後資料 / 索引覆寫) | 既有五案未改 | PASS |
| W2 | 常態落後(≤ 2 格)照追加 live 點、無提示 | 新對照組 | PASS |
| W3 | 無成交空檔(`state.t` 沒前進)照追加 live 點 | 新對照組(TMF 夜盤) | PASS |
| W4 | `state.t` / `state.date` null / 壞格式 / 死區 / **前一場次時戳** → gate 5 不參與 | `tradeSlotOf` null 分支 + 同錨定日守門(新案) | PASS |
| W5 | K 線模式不受影響(不讀 live 點) | 既有 K 線案未改 | PASS |

## 6. 留尾

- 中段缺格(非尾端;含 review SP1 的 0 價 bar 被 adapter 丟掉)仍由 core 單條 polyline 架橋;後端歷史段永久 memo 的截斷風險 → `docs/next-time.md` 2026-08-25 節。
- 資料側根因(H1 分頁尾巴未長齊 vs H2 首頁 timeout)未證實;背景輪詢守夜(截至收尾零事件)。
- 期貨 K 線三態 status 通道(後端 timeout 被吞、route 丟 status)→ next-time 既有條(2026-08-21 R8 P1-6)。
