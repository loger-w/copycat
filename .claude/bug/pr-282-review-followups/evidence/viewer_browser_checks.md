# 回看頁真環境驗證(Chrome + claude-in-chrome,2026-09-19)

頁面走本機 http server(`file://` 進不去 MCP):
`cd ~/Documents/copycat-trading-review && python -m http.server 8799 --bind 127.0.0.1`,
斷言以 `javascript_tool` 讀 DOM(不是看圖猜字),截圖另存 `pr282-01-*.jpg` / `pr282-07-*.jpg`。
`document.visibilityState` 實測為 `hidden`(MCP 分頁常態),所以走 requestAnimationFrame 的重畫
(拖時間軸)不會動 —— 逐則步進改用 ← → 鍵,那條路徑是同步 `rpGo → rpDraw`。

## #1 面板文案(暫用頁 `viewer-cdp-pr282-d3max.html`:bookdays 砍掉最後一天 09-18)

| 選的日期 | 期待 | 實測 |
|---|---|---|
| 2026-09-15(界前) | 「沒有五檔簿 —— **不是故障**」 | 「2026-09-15 沒有五檔簿 —— 不是故障。…」**PASS** |
| 2026-09-16(有簿) | 照常開播 | 「第 1 / 100,355 則(成交 13,544)…」**PASS** |
| 2026-09-17(有簿) | 照常開播 | 「第 1 / 185,875 則(成交 21,280)…」**PASS** |
| **2026-09-18(界後)** | **不得再說「落在有簿的區間內」** | 「2026-09-18 應該有五檔簿,但這一頁沒掃到 —— **它不早於最早有簿的一天(2026-09-16;目前有簿 2 天,最後一天 2026-09-17)**。」**PASS**(修前會說「落在有簿的區間內(2026-09-16–2026-09-17)」,而 09-18 不在裡面) |

分頁鈕 tooltip 同時核:「2026-09-18 應該有五檔簿,但這一頁沒掃到(那天漏跑 book-replay?),重播分頁不能用」——
tooltip 本來就不印區間,維持原樣 **PASS**。

## #1 回歸(上一批的暫用頁 `viewer-cdp-pr281-d3.html`:砍掉**中間**那天 09-17)

| 選的日期 | 實測 |
|---|---|
| 2026-09-17(界內缺一天) | 「…它不早於最早有簿的一天(2026-09-16;目前有簿 2 天,最後一天 2026-09-18)」**PASS**(新句在這一格也為真) |
| 2026-09-18(有簿) | 「第 1 / 162,643 則(成交 16,980)…」**PASS** |

## #7 左右鍵(正式頁 `viewer-cdp.html`)

先以解 payload 對照外掛檔目錄實算,確認「頁面有資料、外掛檔目錄裡沒有」的組合共 **6 組**:
`3630` / `4977` × 09-16 / 09-17 / 09-18(每天 page−file = 這兩檔)。

| 狀態 | 操作 | 期待 | 實測 |
|---|---|---|---|
| **有簿日 + 沒這一檔**(3630 / 09-16) | → 然後 ← | 換日(修前永久零回饋) | 09-16 →(→)09-17 →(←)09-16,兩次都換成功、訊息跟著換 **PASS** |
| 有簿日 + 有外掛檔(1303 / 09-16) | → × 2 | 日期不動、逐則步進 | 日期 09-16 不動,則號 1 → 3 **PASS**(D4 回歸) |
| 無簿日(09-15) | ← | 換到前一交易日 | 09-15 → 09-14,`rpMounted=false` **PASS**(D4 回歸) |
| **載入中**(2489 / 09-17,先切到逐筆分頁再換檔避免預載;同一個 JS task 內點重播分頁 + 送鍵,script 是 async 載入不可能在同 task 內完成) | → | **不換日**(D4 原意) | 送鍵當下畫面 = 「載入簿重播中…」、日期 09-17 不動;3 秒後載完 idx 仍為 1(鍵被正確吞掉,既沒換日也沒步進)**PASS** |

## #8 註解裡那個事實主張(1303 / 09-16,走到第 1 則 = 集合競價段內)

| 主張 | 實測 |
|---|---|
| `getComputedStyle(el, "::after").content` 讀得到 | 回傳 `"集合競價"` **成立**(所以原註解「JS 讀不到」為假) |
| `innerHTML` / `textContent` 快照讀不到 | 該列 `innerHTML.includes("集合競價")` = `false`、`textContent` 同 **成立** |
| 頁頭 chip 與色帶 title 共用 `rpTrialName` | 頁頭 chip 實測「集合競價(盤中暫緩撮合 / 處置股分盤) 第 1 / 1 則」,原始碼 `:703` 的 band `title` 與 `:947` 的 chip 同呼叫 `rpTrialName` **成立** |
| 原註解漏掉的兩處 | `rpChangeLines`(集合競價撮合)、`rp-note`(集合競價段)**成立**;另 `rpBuild` 的格式錯誤訊息也會顯示這個詞,一併寫進新註解 |

附:原註解「全檔這個詞共 20 行命中」與實測不符 —— `grep -c` 實為 **28 行 / 39 次**。
新註解因此**不寫死總數**,改叫人 `grep` 一次(數字會長,寫死必漂)。

## 重建與資料層不動

`build_viewer_cdp.py` 重跑:`codes 91 extras 36 code-days 3113 orders 287 orders-clamped 9 raw MB 29.95 gz MB 6.21 html MB 8.4`
(與上一批紀錄逐字相同)。與重建前的 `viewer-cdp.html.bak-20260919-pre282` 比對:
**解壓後 payload 逐位元組相同(29,950,529 bytes)**,只有 gzip 檔頭的 mtime 欄不同(`b17dad6a` → `db17ae6a`),
HTML 全檔 +412 字元 = 模板那三處改動。資料層零改動。

---

# 第二輪:two-axis review 收修後重驗(同日,`rpInFlight()` 版)

Standards 軸 Std-1 / Std-2 把 `rpKey` 裡的 `rpWait.has(state.code+"|"+state.date)` 收成 loader 旁邊的
述詞 `rpInFlight(code, date)`,判斷式改成 `!rpHasBook() || !rpInFlight(state.code, state.date)` ——
**判斷路徑變了,所以四格全部重跑**(頁面已用改後模板重建):

| 狀態 | 操作 | 實測 |
|---|---|---|
| 有簿日 + 沒這一檔(3630 / 09-16) | → 然後 ← | 09-16 → 09-17 → 09-16 **PASS** |
| 有簿日 + 有外掛檔(1303 / 09-16) | → × 2 | 日期不動、則號 1 → 3 **PASS** |
| 無簿日(09-15) | ← | 09-15 → 09-14、`rpMounted=false` **PASS** |
| 載入中(2489 / 09-17,同一 JS task 內點分頁 + 送鍵) | → | 送鍵當下 = 「載入簿重播中…」、日期不動;載完 idx 仍 1 **PASS** |

#1 四格(界前 / 09-16 / 09-17 / 界後)在重產的 `viewer-cdp-pr282-d3max.html` 上重跑,結果與第一輪逐字相同
(界後仍印「它不早於最早有簿的一天(2026-09-16;目前有簿 2 天,最後一天 2026-09-17)」)**PASS**;
分頁鈕 tooltip 不變 **PASS**。截圖 `pr282-01-d3-after-max.jpg` 換成這一輪(= shipped 狀態)。

#8 的 `getComputedStyle(el,"::after").content` = `"集合競價"`、同節點 `innerHTML` / `textContent` 皆 `false`,
與第一輪相同 **PASS**。

`build_viewer_cdp.py` 重建輸出與第一輪逐字相同
(`codes 91 extras 36 code-days 3113 orders 287 orders-clamped 9 raw MB 29.95 gz MB 6.21 html MB 8.4`)。
