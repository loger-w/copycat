# verification — mod/ladder-order-status(2026-08-13)

## 自動化(全套,main session 親跑 + fix 波後 implementer 複跑)

| 指令 | exit | 結果 |
|---|---|---|
| `.venv\Scripts\python -m pytest -q` | 0 | 2631 passed(baseline 2622 → +9 新測試) |
| `.venv\Scripts\python -m ruff check copycat tests` | 0 | All checks passed |
| `.venv\Scripts\python -m pyright` | 0 | 0 errors, 0 warnings |
| `.venv\Scripts\python -m copycat replay ×2 + validate` | 0 | 42/42 PASS |
| `npm test`(frontend/) | 0 | 112 files / 1778 passed(baseline 1741 → +37) |
| `npx tsc -b` | 0 | — |
| `npx eslint src` | 0 | — |
| `npx react-doctor@latest --scope changed --no-telemetry` | 0 | 3 warnings 全存量,零新增 finding |

紅先行證據:包 B 紅 commit 4 failed(全新案);包 F 紅 commit 26 failed(全在 spec 預告
範圍);fix 波兩對紅綠(255f7552 1 failed / 9f997844 2 failed)。
Mutation 驗證 9 件(包 B 2 件 + fix 波 5 件 + 包 F 內含),證據在各 [lock] commit body
與 progress.md。

## 真實環境節

- **SC-1~SC-4(UI 掛單顯示)**:AI 層 = 元件測試以畫面可指認 DOM 斷言驗證(aria-label
  「刪 {價} 買單/賣單」textContent `"4(1)"` 型、`ladder-filled-lot` 徽章 `(2)`、點刪
  bodies、全撤 disabled、pointer-events-none)。**AI 截圖層降級**:閃電梯掛單態需群益
  真實委託(盤中 + 真下單),spec R11 拍板實作者不代下單 → `browser_unavailable:
  需真錢委託資料,mock harness 不存在(--verify 模式無 capital 資料)` + user 過目
  (過目清單見收尾回報)。
- **SC-5/SC-7(後端 debounce + 守門)**:pytest 全鏈案(FakeCom)+ 白箱狀態斷言;
  真實環境層 = 盤中成交後庫存 ~0.5-1s 內刷新,user 過目。
- **SC-6(即時鏈)**:既有 useCapital 測試不紅(invalidate 鏈零改動)+ 盤中 user 過目。
- **未改功能抽驗**:白名單 lens 逐行驗證 10 條全 PRESERVED(武裝/部位條/市價列/
  他契約過濾/送單路徑);全套測試綠 = 迴歸抽驗涵蓋。

## 白名單逐條(§7 對照)

1. 點紅方格逐 seq 直刪 — PASS(三處 cancel 路徑逐字未動 + bodies 斷言綠)
2. 他契約/他檔過濾 — PASS(比對鍵零改動;零股閘為 spec 明文改寫)
3. 市價單不上梯(含已成交)— PASS(price null 早退在 filled 之前 + 測試)
4. 武裝/點價/防抖/idle/Esc/佈局 — PASS(diff 未觸及;點價鈕變窄 = R8 承認偏差)
5. 部位條/標記/市價列/跟隨置中 — PASS(diff 未觸及)
6. 串行鏈非重疊(守門維持)+ 合併語意 + 60s stale + degraded — PASS(lock 測試 +
   守門四路徑案)
7. 200ms invalidate 不動 + 送單路徑零觸碰 — PASS(useCapital.ts / safety / close 不在 diff)
8. /api/capital/orders 契約零改動 — PASS(models/reply/capital_api 不在 diff;
   unit 字面值升格為前端過濾鍵已登記 CLAUDE.md §4 + test_store lock)

## Migration 可逆

無 migration(純 UI + 內部 debounce 預設值);前後端兩個 🔴 可獨立 revert(R10)。
