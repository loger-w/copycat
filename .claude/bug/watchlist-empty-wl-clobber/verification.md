# verification:watchlist-empty-wl-clobber(2026-08-04)

## 自動化驗證(harness.json 三條 + 動到 frontend/ 加三條)

| Gate | 指令 | 工作目錄 | 結果 | Exit |
|---|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | repo root | 1633 passed | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | repo root | All checks passed | 0 |
| pyright | `.venv\Scripts\python -m pyright` | repo root | 0 errors 0 warnings | 0 |
| vitest | `npm test` | frontend/ | 987 passed(72 files) | 0 |
| tsc | `npx tsc -b` | frontend/ | 無輸出 | 0 |
| eslint | `npx eslint src` | frontend/ | 無輸出 | 0 |

(後端零改動,pytest/ruff/pyright 為 regression 保險;`copycat validate` 不在
harness.json verify 陣列且本輪未動 replay/engine,未跑。)

## 真實環境驗證(web shape,UI 畫面驗證節;subagent 截圖 + user 過目待收尾回報)

- 方法:臨時 `vite.verify.config.ts`(proxy → 死 port 59997)起 :5197 重現「自選 GET 500」
  真實條件;happy path 用 user 既有 :5173 dev server(proxy → 真 server :8721,只讀)。
  未起第二台後端、未動跑著的 :8721(§8 紀律)。驗畢已停 :5197 並刪臨時 config。
- SC-A(重現條件下修後行為):**PASS** — 側欄顯示「自選清單載入失敗」,整個側欄無
  「管理」鈕;搜尋框照常。console 除死 backend 預期錯誤外零 React error。
  截圖 `evidence/SC-A_load-fail_no-manage-button.png`。
- SC-B(happy path regression):**PASS** — 自選正常載入(未分組 0 / 玻璃 2),
  「管理」鈕存在、Dialog 開合正常;網路面板全程零 PUT/POST(未寫入真實資料)。
  截圖 `evidence/SC-B_loaded_manage-dialog-opens.png`。

## 反向驗證(Phase 8)

- 暫時停用修復(gate 條件改 `false`,等價還原)→ `npx vitest run …WatchlistSidebar.test.tsx`
  → **恰好 2 條新測試紅**(載入失敗 / pending 兩態的「管理鈕不渲染」),其餘 53 綠,exit 1。
- 還原修復 → 55 passed,exit 0。測試確實抓得住 bug。

## 動機核對

Bug = 載入失敗態可經 Dialog 以 EMPTY_WL 整份 PUT 清空自選。修後該入口在危險窗
(從未成功載入)不存在,真實環境重走重現步驟已無法走到 Dialog;成功載入後功能不變。
