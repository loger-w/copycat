# verification — mod/intraday-fill-marks(2026-08-17)

## 1. 自動化(auto-verify;專案 CLAUDE.md §1 前端 gate)

| step | command(cwd frontend/) | exit | 數字 |
|---|---|---|---|
| baseline(開工) | `npm test -- --run` | 0 | 120 files / 2027 tests |
| 波尾(包 A+B 後,HEAD 22d9420c) | `npm test -- --run` | 0 | 121 files / 2094 tests |
| fix 波 1 後(HEAD 73ca0ab4) | `npm test -- --run` | 0 | 121 files / **2100 tests** |
| 型別 | `npx tsc -b` | 0 | — |
| lint | `npx eslint src` | 0 | — |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | — | 1 warning `only-export-components GroupGridView.tsx:66 gridShape` = **存量**(master 同行已 export),非新增 → 不算 FAIL |
| 後端 | 零改動(`git diff master..HEAD -- copycat tests` 為空)→ pytest/ruff/pyright 不受影響,未重跑 |

## 2. 真實環境(SC-8;側車 fake capital + 種子行情,零 TC4)

環境:`evidence/sidecar_server.py`(R1 樣板 + `/_fake/fill` N+D 回報注入 + 2330 掛 CDF/QFF stkfut catalog、`F:CDF:*` 走 2330 種子價)port 8721 + `npm run dev` 5173;瀏覽 devtools MCP 1500×950 / claude-in-chrome。注入:2330 B 2張@1195 10:05:12、B 1張@1196 10:05:40、S 1張@1192 10:40:00;2317 S 3張@204 11:20:05;CDFH6 B 2口@1190 09:30:00。

| 項 | 結果 | 證據 |
|---|---|---|
| happy:單檔頁 2330 主圖 | `fill-B-605`(▲ bull)/ `fill-S-640`(▼ bear)兩 polygon,同分鐘同向合併(2+1)| `SC-8-page-1500.png`、`SC-8-page-marks-closeup.png` |
| hover 10:05 readout | 「10:05 1195 -0.42% 量 60 外 60 內 0 **成交 買 3@1195.33**」(量加權 (1195×2+1196)/3)| `SC-8-page-hover-1005.png` / `-crop.png` |
| toggle 關 / 開 | 關 → 0 polygon、readout 無成交欄、localStorage `fills:false, v:2`(不 bump);開回 → 2 | JS 讀值(progress.md 記錄) |
| 圖牆(現股) | 2330 卡 2 個、2317 卡 1 個(`fill-S-680`)、2454/2308 0;牆頂「成交點」關 → 全牆 0、開 → 3;卡內零 button | `SC-8-grid-1500.png` / `-crop.png` |
| 個股期(CDF 202608) | `fill-B-570` ▲ @1190;hover 09:30 readout「成交 買 2@1190」;現貨態的 2330 委託不出現在合約圖(鍵分離) | `SC-8-stkfut-hover-0930.png` / `-crop.png` |
| edge:域外價 | 首次注入 1050/1052/1060(遠低於 1170–1215 域)→ 0 polygon(域外不畫,edge 11)— 側車重啟前實測 | progress.md |
| edge:零股 | 注入 qty=200 現股 → store 折成 filled 0 張 → 不畫(`filled_qty>0` 閘) | orders dump |
| fix 波後複核 | reload 後 page 兩點 + readout 同上、`fills-layer` `pointer-events="none"` | JS 讀值 |
| 抽 2 個未改功能 | 高低點標記 / VWAP+CDP/MA 疊線 / 量分佈 VP 照畫;三梯委託列表「已成交」徽章與清單照常(截圖右欄) | 同上截圖 |

**未在 fake 環境驗到 = 留 user 過目層**:盤中真成交(群益回報真時間)後 ≤1s 出現標記;真實價線下 ▲/▼ 的可見度(fake 種子價每 30s 上下抖 1 tick 造成鋸齒,▼ 綠色壓在綠色線段上不易辨識 — 真盤走勢平滑會好些;若仍不夠顯眼,加大 `FILL_MARK` 或改 halo 色是一行改動)。

## 3. 白名單逐條(spec §3)

W-1 後端零 diff ✓ / W-2 `ymdWindow` 輸出不變(ladder-lots 18 案 + 三梯測試綠)✓ / W-3 TOGGLES_VERSION=2 不變、既有 toggle 值不動 ✓ / W-4 ChartStatic memo:SC-9 計次案 + M15 mutation 證非 vacuous ✓ / W-5 GroupCard memo:memo.test 既有 2 案 + 有成交卡新案 ✓、card 零 button ✓ / W-6 page 六欄不動、card 恆四欄 ✓ / W-7 core 零 capital/TQ import,既有 StockIntradayChart.test stub 不改路由全綠 ✓ / W-8 stkfut 反灰三顆不動,fills 恆可用 ✓ / W-9 useCapitalOrders 未動 ✓。

## 4. 成功條件逐條

SC-1 fill-marks 42+ 案綠 ✓ / SC-2 toggles 14 案綠(舊存檔補鍵、不 bump)✓ / SC-3 polygon testid/class/座標/窗外/域外/順序 ✓ + 真實環境 ✓ / SC-4 readout page 單側 bull·bear、雙側、無成交、toggle 關、域外(cr1 A-2)✓ + 真實環境 ✓ / SC-5 五鈕、關閉、圖牆同步 ✓ + 真實環境 ✓ / SC-6 圖牆 per-card 計數 + memo ✓ + 真實環境 ✓ / SC-7 現貨/合約/零股/非法 ym 四案 ✓ + 真實環境合約 ✓ / SC-8 截圖 8 張 ✓(user 過目層待盤中)/ SC-9 memo 閘 ✓。

migration:無(toggles 加鍵可逆:刪鍵即回舊 schema,`{...DEFAULTS,...saved}` 容忍多鍵)。
