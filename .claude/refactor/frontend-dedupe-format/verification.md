# verification — refactor/frontend-dedupe-format(2026-08-04)

## 自動化(Phase 6)

| gate | 結果 |
|---|---|
| `npm test`(frontend/) | **991 passed / 72 files**(baseline 987 + 4 characterization) |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | exit 0 |
| `check_feat_tags.py` | PASS(flow=refactor,commits=3:🟢×1 + 🔵×2) |

backend 未動(diff 僅 frontend/ + docs/ + .claude/);後端 gate 於第 1 輪同日已全綠。

## 真實環境(Phase 7,2026-08-04 22:2x 夜盤)

vite dev(proxy → 跑著的 prod backend :8721,零新增訂閱,盤中紀律合規)+ DevTools MCP:

- **IndexBar**(行內 fmtPct + chgPct 委派):櫃買 `375.03 +3.35%` ✅(加權夜盤無資料顯示 `-`,與 refactor 前語意一致)
- **IndexPage Quote**(:186 pct 段 → fmtPct):台指期 `44077 +733.00 (+1.69%)` ✅(pts 段無 %、pct 段有 %,格式與舊行內完全同形)
- **FuturesPage**(:60 → fmtPct):微台 header `+757 +1.75%` ✅
- **RiverCards**(local fmtPct 刪除 → lib):六腿並排卡 `+1.52% / +1.73% / +0.96% / +0.66% / +1.52% / +5.06%` 全部帶正號兩位小數 ✅(截圖 `evidence/river-cards-fmtpct.png`)
- **RiverOverlay**(重疊模式):載入正常(pct 軸標籤在 SVG 內,由 characterization 測試釘死 `+1.05% / -1.05% / 0%`)
- console 僅 React StrictMode 首掛 WS abort 的既知 warning,**零 error**

## 行為零改變核對(Phase 8)

- 動機(6+ 檔重複)已解:`function fmtPct` / `async function parseError` 全 repo 各僅存 lib 一份;`chgPct` 除 IndexBar 委派 wrapper(簽名吃 IndexSeries,null gate 保留)外全走 lib。
- 未動:CapitalPositionsList `>= 0`(記 next-time)、CandleChart 語意變體、IndexBar local `fmt`(實作不同)、RiverCards `fmtPrice`。
