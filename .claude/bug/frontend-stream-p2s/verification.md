# verification — frontend-stream-p2s(F-1~F-5 批次)

分支:`fix/frontend-stream-p2s`(16 commits on f6a60675)

## Phase 6|自動化 gate(主 session 親跑)

| gate | 結果 | exit |
|---|---|---|
| npx vitest run | 108 files / **1678 passed** | 0 |
| npx tsc -b | 無輸出 | 0 |
| npx eslint src | 無輸出 | 0 |
| 後端 pytest -q(sanity,零後端 diff) | 2548 passed, 1 skipped | 0 |

## Phase 7|真實環境驗證

前端 stream/幾何邏輯修復,deterministic 重現只在受控時序(vitest fake WS /
fake timers)。畫面層變化(user 過目項,dev vite 對 prod 8721 即可看):
- 切合約 / 換月後成交明細展開筆數歸零(F-4)
- VP 量條在 10/50/100/500/1000 元邊界檔位不再與鄰檔重疊變深(F-5)
- 後端短暫 502/503 後主圖 1–8s 內自癒不再釘「載入中…」(F-3)
截圖層:`browser_unavailable: 批次修無 UI SC 新增,以測試 + user 過目為證`。

## Phase 8|反向驗證(主 session 親跑,fix 輪前)

revert 6 個 fix commit → 3 測試檔 **9 failed**(F-4×1、F-5 邊界×4、F-1×1、
F-2×1、F-3×2),樣態 = 原 bug;restore 後 1672 全綠。
fix 輪(A-2)另有 red→green 對 + 8 個 mutant 自證(見 round JSON);
M9(backoff 遞增拿掉)存活由主 session 獨立重驗後才進 fix 輪。

## Phase 9|留尾巴

- A-4:首次掛載的第一發 refetch 失敗時 wsOpen 尚 false → 不排重試,自癒退到
  WS onopen(次級延遲非死路)。候選解 = 第三道檢查放寬成「WS open 或從未 open」。
- M3a(mounted 檢查)與 wsOpen 防線在 unmount 路徑完全重疊,無法單獨歸因
  (已註記於 scheduleRetry;行為本身有測試鎖住)。
