# verification — watchlist-dialog-swallowed-callback

## Gate 指令(2026-08-11,全部單獨跑、exit code 逐一確認)

| step | command | exit | 結果 |
|---|---|---|---|
| 全量測試 | `npm test`(frontend/) | 0 | 110 檔 / **1726 passed**(baseline 1722 + 新增 4) |
| 型別 | `npx tsc -b` | 0 | 無錯誤 |
| Lint | `npx eslint src` | 0 | 無錯誤 |
| React 掃描 | `npx react-doctor@latest --scope changed --no-telemetry` | — | **No issues found**(4 檔;中途 1 新增 finding `rerender-lazy-ref-init` 已修掉) |

## /bug 專屬 gate

- **紅測試轉綠**:
  - 主 bug 兩條(d318650f 紅 → 8b71ab8d 綠):stale 基底還原 / onGroupDeleted 吞沒。
  - review 失敗短路一條(c0ddfb32 紅 → 56ed6c18 綠):錯誤文案可見 + 已排隊動作作廢。
- **反向驗證**:`git revert --no-commit aa1156d2 8b71ab8d` → 主 bug 兩條紅回來(2 failed)
  → `git reset --hard HEAD` 還原 → 綠。
- **mutation 抽驗(W-5 lock)**:dedup `isSameWatchlist` 改 identity 比對 → 連點去重 lock
  紅 → Edit 還原 → 綠(Edit 成對操作,grep MUTANT 無殘留)。
- **重走重現步驟**:真實重現路徑即紅測試場景(jsdom 連刪兩組 + gate 在途窗);修後
  第二發 PUT body `groups: []`、兩發 onGroupDeleted 依序執行 — 由測試斷言即時驗證。

## 白名單逐條(repro.md「不能破壞的既有行為白名單」)

- [x] W-9 零 PUT 早退(深度比對)— 測試「右欄搜尋加入該組 → PUT 恰一筆」等綠;dedup
  改對 base 比對,佇列下語意更嚴。
- [x] F1 pending 停用建議列 — 測試「PUT pending 期間重複加入 → 仍只送一筆」綠。
- [x] W-3 PUT 失敗路徑 — 測試「刪除群組失敗 → 錯誤文案、無第二次 PUT、不呼叫
  onGroupDeleted」綠(文案來源改 localError,同一份 errText 文字)。
- [x] 單發刪組三性質 / BAD_GROUP 前端擋 / 開關重置 / derived selected / m-auto 與
  display class 契約 — 同檔既有 32 條全綠。
- [x] 側欄 dropCollapsed(W-20)契約 — WatchlistSidebar.dropcollapsed.test.tsx 綠
  (stub 契約保留,理由註解已同步)。
- [x] useSaveWatchlist 其他 caller(WatchlistSidebar / StockPage)零改動(hook 本體未動,
  git diff 可證)。

## 回頭核 goal(/auto 退出條件)

- [x] frontend `npm test` 全綠(1726/1726)
- [x] `npx tsc -b` 過(exit 0)
- [x] `npx eslint src` 過(exit 0)
- [x] 白名單行為保留(上節逐條)
- [x] /bug Done:紅測試綠 + 既有測試綠 + regression(全量即抽樣的超集)綠 + 反向驗證
  通過 + repro.md 三段(重現 / root cause / 修法+blast radius)齊全
