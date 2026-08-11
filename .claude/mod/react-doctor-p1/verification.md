# verification — mod/react-doctor-p1(2026-08-11)

## 自動化 gate(主 session 波尾親跑,frontend/;2026-08-11 13:14-13:20)

| Gate | 指令 | 結果 |
|---|---|---|
| 測試 | `npm test`(vitest run) | **110 files / 1707 tests passed**(baseline 108/1698;+2 檔 +9 tests 皆本批新增)exit 0 |
| 型別 | `npx tsc -b` | exit 0,無輸出 |
| Lint | `npx eslint src` | exit 0,無輸出(useLayoutEffect / render 期間 setState 未觸發 you-might-not-need-an-effect 同族新條目 → SC-7 fallback 未動用) |

Python gates(pytest / ruff / pyright / validate)**不適用**:`git diff 7fa18d46..HEAD --stat`
全部落在 frontend/src 與 docs/.claude,零 `.py` 檔觸碰。

## SC-7 doctor 重掃對照(`npx react-doctor@latest --verbose --no-telemetry`,輸出存 `doctor-rescan.txt`)

首掃 85 issues → 重掃 **69 issues(−16)**,算術與逐條清單精確吻合:

| 目標條目 | 重掃狀態 |
|---|---|
| useRiver.ts:115 impure updater(error)+ 連帶 94/95/100 三 warning | **全部消失**(4) |
| WatchlistSidebar.tsx:115 impure updater(error)+ :51/:117 warning | **全部消失**(3) |
| TickTape.tsx:57 index-as-key | **消失**(no-array-index-as-key 5→4,餘 4 條為 SVG 幾何 FP) |
| StockChart.tsx:78 adjust-state-on-prop-change | **消失**(餘 1 條 LadderView:126 為 pre-existing,非本批檔) |
| no-ref-current-in-render(error 類):useFuturesStream:61 / useStockStream:136 / useBreadth:61 / useIndexStream:71-73 / useSignalAlerts:82 | **7 條全消**,10→3;餘 3 條恰為 out-of-scope 的 useStockStream:126/128/135(needs-human 刻意時序,原樣保留) |

分類帳:Bugs errors 21→12(−9 = impure updater ×2 + ref-in-render ×7)、Bugs warnings
22→15(−7 = useRiver ×3 + WatchlistSidebar ×2 + TickTape + StockChart);Perf 13→13、
Maint 20→20、A11y 9→9(批外分類零變動)→ **批內檔案零新增 finding**。批內檔案殘餘條目
(useRiver:88 / useBreadth:86 / useIndexStream:109 / useFuturesStream:90 / useStockStream:243
/254/415 等)全屬 triage §三判 disable 的 FP rule 家族(effect-needs-cleanup 9/9 FP、
no-fetch-in-effect 6/6 FP)與 WatchlistSidebar a11y(/chore 批)、giant-component
(needs-human),皆 pre-existing。

## 白名單逐條核(change-spec :62-83;lens 2 逐條 verdict + 主 session 波尾全套綠)

1. useRiver 盤別變更 / seq / union / 重啟 / 503 / 非 river 型別 / wsStatus — ✅ preserved(既有 8 條 + 新增 4 條綠)
2. WatchlistSidebar 折疊持久化 / W-20 / W-22 — ✅ preserved(56+ 條綠;`commit()` 一字未動)
3. TickTape 最新在上 / 上色 / 分頁 / 空態 / h-full — ✅ preserved(9+1 條綠)
4. StockChart 期貨態 D10 四條 / 還原 A6 四條 / 不寫回 localStorage / bars 一發不打 — ✅ preserved
5. useStockStream F-1 handler 本體比較 / :126/128/135 不動 — ✅ preserved(該檔 diff 僅 1 deletion)
6. useSignalAlerts 訂閱恰一次 / TTL / dismiss / market 免疫 — ✅ preserved(drop deps 恆 `[]`;deps 失穩時「5 秒自動消失」測試會紅 = 機械保護)
7. 三 WS hook 換日 / seq 跳號 / reconnect / 退避 — ✅ preserved(零邏輯改動)

## 紅測試 red→green 證據(commit f83a97fe → 24208c3f)

1. useRiver StrictMode 換場單發:紅 `expected 4 to be 3` → 綠(含 night snapshot 併入驗證)
2. WatchlistSidebar StrictMode setItem 恰一次:紅 `length of 1 but got 2` → 綠
3. TickTape DOM node 恆等:紅 `Object.is equality`(重掛新 node)→ 綠
4. StockChart futconverge 無 stkfut=false 中間 commit:紅 `+ false` → 綠

Lock 測試(0b196814,mutation-verified):換場判定移到 seq 守衛前 → 紅;拿掉 sessionRef
null 守衛 → 紅;toggleUngroupedCollapsed 改回 updater 內寫 → 紅;各還原後綠,MUTANT 殘留 0。
dropCollapsed 同 tick 兩回呼 lock:closure 版 mutant 得 `['觀察']` ≠ `[]` → 紅,ref 版綠。

## 已知取捨 / 記帳(詳 docs/next-time.md 2026-08-11 節)

- TickTape 滿 200 筆 key 仍位移(未惡化;真解穩定序號)。
- WatchlistManagerDialog 單 mutation observer 吞第一發 onSuccess(pre-existing 真 bug,
  本批發現、刻意不修)。
- useBreadth / useIndexStream layout-effect 鏡射與 imperative 配對不同級(自癒型,註解已標)。
- StockChart spotMode prod 路徑無讀者(A6 由 localStorage 兌現)。
- toggleUngroupedCollapsed 依賴「呼叫者是事件路徑」前提(註解已載)。

## 真實環境節

本批為 hook 內部時序 / DOM 重掛 / dev-StrictMode 行為修復,無新 UI 元素、無 API 變更、
無畫面可指認差異(StockChart 消閃格為單 frame 級,截圖不可捕捉)——真實環境驗證以
jsdom commit 級測試(futconverge props 紀錄)+ doctor 靜態對照為證據面;盤中 UI 抽查
(TickTape 滾動、側欄折疊、合約切換)併入下次 prod 重啟後的例行過目,無獨立驗證窗口需求。
