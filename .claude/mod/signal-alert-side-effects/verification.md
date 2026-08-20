# Verification(mod/signal-alert-side-effects,2026-08-20)

## 自動化 gate(全 PASS,exit 0)

| Gate | 指令(工作目錄) | 結果 |
|---|---|---|
| Frontend 測試 | `npm test`(frontend/) | 131 files / **2323 passed**(baseline 2314 → +9 新測試) |
| 型別 | `npx tsc -b`(frontend/) | PASS |
| Lint | `npx eslint src`(frontend/) | PASS |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found(零新增 finding) |
| 後端測試 | `.venv\Scripts\python -m pytest -q` | 2791 passed(零 .py 觸及,保險跑) |
| 後端 lint | `ruff check copycat tests` | PASS |
| 後端型別 | `pyright` | 0 errors / 0 warnings |
| copycat validate | — | N/A:diff 純 frontend(2 檔皆 frontend/src/hooks),replay 產物不受影響 |

## Mutation 抽驗(lock 測試,皆已還原)

1. 移除 `.catch(() => {})` → vitest **Unhandled Rejection、exit 1**(指向 resume 被拒測試)→ 還原綠。
2. `NOTIFY_MIN_INTERVAL_MS` 5000 → 500 → 節流 4999ms 邊界測試**紅**(1 failed)→ 還原綠。

## SC 逐條

| SC | 結果 | 證據 |
|---|---|---|
| SC-1 suspended 不建節點 + resume | PASS | 測試「AudioContext suspended → 跳過該聲不建節點,並嘗試 resume;toast 照出」+ amendment F2(in-flight)/ F4(closed 回收重建)三條測試 |
| SC-2 tag 固定 copycat-signal | PASS | 測試「通知 tag 固定為 copycat-signal(OS 層合併),不用 sig.id」 |
| SC-3 5s leading-edge 節流 | PASS | 測試「連發訊號 5 秒窗內只發第一則(含 4999ms 邊界),窗滿放行」+「背景爆量 20 則」+「permission 擋掉不消耗窗口」 |
| SC-4 既有測試不紅 | PASS | 2323/2323(既有 2314 條全數保留且綠) |

## 白名單逐條(correctness lens 機核 + 全量綠雙層)

1. toast 佇列(VISIBLE/TTL/dismiss/key/文案)— PASS(diff 零觸碰,5 條測試未改)
2. 靜音 → Notification 照發(MFS-1)— PASS(notifyDesktop 呼叫仍在 getSoundOn 判斷之外)
3. 可見不發 / permission 非 granted 不發 — PASS
4. AudioContext 缺席靜默略過 — PASS
5. running 嗶聲參數與單例 — PASS(880Hz/0.12s/0.04 逐行未動;恢復測試斷言 contexts 不增)
6. unmount 退訂 — PASS

## 真實環境層

背景分頁 / OS 通知 / AudioContext 生命週期屬瀏覽器層行為,jsdom 鎖行為合約;
真環境驗證窗口 = 交易日盤中有訊號時,由 user 過目「背景通知合併為單則、不再疊排」。
migration:無(不碰持久化資料)→ 可逆性 N/A。
