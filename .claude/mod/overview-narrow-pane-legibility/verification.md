# verification:mod/overview-narrow-pane-legibility(2026-08-21)

## 1. 自動化(auto-verify;frontend 形狀)

| step | command(在 frontend/) | exit | 結果 |
|---|---|---|---|
| vitest | `npm test -- --run` | 0 | 134 files / **2358 passed**(baseline 2346;+12) |
| tsc | `npx tsc -b` | 0 | — |
| eslint | `npx eslint src` | 0 | — |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 0 | 5 warnings,全部落在未改動行(LimitListSection:473 tr onClick / MarketPane:305 / CandleChart:194,316,372 index key)= 存量,**無新增** → PASS |
| build(implementer 波內) | `npm run build` | 0 | CSS 產出 `@container not (min-width:41rem)` / `not (min-width:26.5rem)` 兩區塊,四 utility 皆在 |

mutation(fix 波 `7288f742`,Edit 改壞 → 紅 → Edit 還原):`CANDLE_CHROME_Y` 100→84 紅 3、`CANDLE_INSET_X` 34→30 紅 3、`Math.round`→`floor` 紅 1。

## 2. 真實環境(vite dev 5173 → prod 8721 真資料;headless Chrome + 同源 iframe host;root font 16px 三檔皆同)

量測 JSON:`evidence/SC-1536-measure.json` / `SC-1920-measure.json` / `SC-2560-measure.json` / `A1-1200-measure.json` / `SC-4-stock-measure.json` / `SC-4-m5-measure.json`。

| SC | 1536×864 | 1920×1080 | 2560×1440 | 1200×800(單欄) | 判定 |
|---|---|---|---|---|---|
| SC-1 K 線 1:1 | viewBox `0 0 282 96` = clientW 282;y 刻度 computed **10px**(改前 3.0px);svg clientH 81 < 96(地板,實縮 0.84,edge 13);rect 相疊 1.1px(字形分離,見 crop3x) | `0 0 398 226` = 398×226,不疊 | `0 0 590 451` = 590×451,不疊 | `0 0 353 96` = 353×96 | **PASS**(864 高地板案如實記 edge 13) |
| SC-2 漲跌停不捲 | scrollW **431 ≤ 431**(真資料 48 列含 8 字股名);金額/量比 th `display:none`;td padL 4px | 585 ≤ 585;七欄;padL 4px | 841 ≤ 841;**九欄**;padL 8px | 820 ≤ 820;九欄 | **PASS**(D2 FAIL 階梯未啟用) |
| SC-3 週期列 ≤ 2 行 | **46px**(改前 74);btn padL 4px;gap 2px | 48px;padL 8px(不 compact,pane 466) | 48px;padL 8px | 46px(pane 421,compact) | **PASS** |
| SC-4 回歸 | pane 5分 240 根 barW 0.8 未成實心(`SC-4-pane-m5-1536-crop3x.png`) | — | 個股頁 6415 日K viewBox **`0 0 1400 766`**、1710×936 正常渲染(`SC-4-stock-candle-2560.png`);隱藏 pane 走 `1400×578` fallback(W-3 實證) | — | **PASS** |
| SC-5 gate | 見 §1 | | | | **PASS** |

截圖:`evidence/SC-1-3-1536-day.png`(整頁 + 量測 pre)、`SC-1-3-1920-day.png`、`SC-1-3-2560-day.png`、`SC-1-1536-candle-crop3x.png`、`SC-2-1536-limitlist-crop.png`、`SC-3-1536-periodrow-crop2x.png`、`SC-4-*`、`A1-1200-single-col.png`。

## 3. 白名單逐條(對照 change-spec §2)

- W-1 ✓ 個股頁 CandleChart viewBox 1400(真環境 + `CandleChart.test` lock + StockChart/FuturesChart 測試綠;whitelist lens 逐處核 dimW 讀者 7 處)。
- W-2 ✓ 重疊態 frame / unitScale 算式未動(lens 核);分時態 `paneIntraday` 與 `paneCandle` 互斥(新測試鎖)。
- W-3 ✓ 量不到 → 1400×578(測試 + 真環境隱藏 pane 實證)。
- W-4 ✓ CANDLE_CHROME_Y 100 / INSET 34 同值;字面量 lock(mutation-verified)。
- W-5 ✓ 九欄 DOM / testid / sticky / nowrap 全保留(44 既有測試綠);≥ 41rem 九欄(2560 / 1200 實證)。
- W-6 ✓ 17 鈕 / disabled / 重疊鈕條件未動;寬 pane computed padL 8px、gap 4px(1920 / 2560 實證)。
- W-7 ✓ IndexPage 未動;pane 無條件 min-h-0 / figure min-h-48 保留。
- W-8 ✓ 120 根 barW 1.4px @282(改前 ≈ 1.65 估;同級);240 根 0.8px 未成實心。

## 4. 收尾檢查

- 臨時 host `frontend/public/__viewport_host.html` 已刪、`frontend/public/` 目錄移除;`git status --short` 僅剩 `?? .claude/mod/overview-narrow-pane-legibility/`(artifact,隨後 commit)。
- vite dev(5173)收尾前以 port → PID 關閉;prod 8721 全程未動。
- migration:無(純前端、無 schema)。

## 5. 留尾(next-time 候選,不在本案 scope)

- 1536×864 K 線態吃地板 96 → svg 被壓 81px:根因 K 線態雙層 figure chrome 100(分時只 26)+ Quote figcaption 折三行;候選 = K 線態 chrome 瘦身或 figcaption 單行化(動 CandleChart 共用 figure,需另案)。
- CandleChart figcaption(`120 根 / 高 / 低 / 期間`)在 < 320px 寬折兩行溢出 `h-4`(既有)。
- frontend-conventions skill「全站字級縮放 = root font-size media query」為 neigui 來源,copycat 未實作 → 8.5 GC。
