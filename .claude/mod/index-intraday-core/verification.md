# verification — mod/index-intraday-core(R4)

HEAD 驗證版本:`c326dee0`(base `c958b141`)。

## 1. 自動化 gate(auto-verify;evidence/frontend-gate-final.txt / backend-gate.txt)

| 步驟 | 指令 | 結果 |
|---|---|---|
| frontend vitest | `npm test -- --run` | **126 files / 2195 tests passed**(baseline 123 / 2152) |
| tsc | `npx tsc -b` | exit 0 |
| eslint | `npx eslint src` | exit 0(零 unused:自繪版符號全清) |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | Scanned 18 files,No issues found |
| backend(未動 .py,完成前 gate 照跑) | `pytest -q` / `ruff check` / `pyright` | 2650 passed / All checks passed / 0 errors |
| build css(pkg D) | `npm run build` + grep dist css | 4 個 `--idx-*` setter 在 `@container(min-width:1050px)` 內、4 個 reader 皆產出 |

## 2. 真實環境(側車 fake server,零 TC4/ZMQ;evidence/fake_server.py,port 8721 + vite 5173)

工具:claude-in-chrome;視窗為 2560×1440 最大化且 `resize_window` 無效 → 以同源 iframe host
(`__viewport_host.html?w=&h=`,臨時放 frontend/public,收尾已刪)控制 viewport;截圖動作
才逼出 RO 一幀(hidden tab 陷阱,ops-discipline)。**注意 `computer.zoom` 會把 tab 的 device
metrics 覆寫成 zoom 區域尺寸且不還原**(本輪真踩:量到 662×588),close-up 一律 PIL crop。

| SC | 結果 | 證據 |
|---|---|---|
| SC-1 hover(加權) | PASS:`crosshair-v/h` 出現、左緣價標 `24285`(不 snap、整數點)、底部 `11:36 / 24400.94`、readout hovering `11:36 24400.94 +0.42%` | SC-1-twse-hover-crop.png / SC-1-4-dom.json |
| SC-2 均價 / 昨收 / CDP+MA 同款 | PASS:均價線 stroke-ink + 末點標 `24361.09`;昨收虛線 + 中格刻度 24300;域內 CDP `24550* 24450* 24250* 24150*` + MA5 `24242`;域外掛牌 `AL 23950↓` / `MA20 24023↓`(依價位由上而下) | SC-2-3-twse-crop.png / SC-1-4-dom.json |
| SC-3 高低點 / 現價圈 | PASS:day-high 24415.28 / day-low 24283.54 空心環 + 文字、現價實心圈(marks 6 = 兩 pane × 3) | 同上 |
| SC-4 櫃買 | PASS:同款圖 + hover(價標 `240.32` 保留小數、readout `11:00 242.64 +1.10%`);CDP / MA disabled title「櫃買無日 K 資料源」;均價 title「分鐘收盤均價(指數無成交量)」 | SC-4-otc-hover-crop.png / SC-1-4-dom.json |
| SC-5 個股 / 群組零變化 | PASS(測試層):StockIntradayChart.test / .variant / GroupGridView* / stock-intraday-svg.test / StockChart.test 一字未改全綠;W-1 lock 三案 + mutation(index 閘反轉 → 15/17 紅,還原綠)。**截圖前後對照未做**:側車 FakeStockSource 無個股資料(個股頁 = 尚無成交),真 TC4 層待 prod 重啟過目 | pkg A 回報 |
| SC-6 佈局(6:5) | 1920×1080:主 grid 1002/1002 無捲軸、騰落線 wrapper 281 / figure 431 = **0.653**、分時 svg 1:1 `0 0 432 297`;1536×864:786/786 無捲軸、183/287 = **0.638**、svg 121 / 156 ≥ 96;1366×768(單欄):`--idx-*` 未套用、grid flex `1 1 0%`、section `0 0 auto`、wrapper 96px / min-height auto(= 改動前) | SC-6-layout-{1080p,864p,768p}.json + .jpg |
| SC-7 1:1 | PASS:viewBox 寬 = 量到 px 寬(432 / 316),高 = 量到高 − 28 | SC-6 json svgs |
| SC-8 三類 commit | 見 §4 git log | |

原案 3:2 實測:1080p ratio 0.474、864p grid 804 > 786(溢出 18px 出捲軸)→ 依 spec §3.4 調變數為 6:5(689c0a6a)。

### 白名單逐條

- W-1:測試層 PASS(見 SC-5);真 TC4 個股頁 / 群組圖牆待 prod 重啟過目。
- W-2:OverlayCard 與 K 線態未動(MarketPane.size TD-7 兩案 + 字級補償 overlay 案綠);MarketPane.test 30 案(1 行 test-infra 收斂 selector)綠。
- W-3:`useIndexOverlay` gate 未動;`/api/index/overlay` 側車實打(overlay fixture 落到畫面)。
- W-4:1050px 斷點 / 單欄退化:768p 實測逐值同改前;可縮鏈節點未動(pane root min-h-0 / figure min-h-48 案綠)。
- W-5/W-6/W-7/W-8:diff 未觸及對應面(review test-coverage lens 逐條核)。

### 未在本輪驗到 / 待 user

- 真 TC4 指數推播下的圖(側車為 fake 序列;域為對稱 autofit ±1% 地板,平靜日線振幅視覺變小 — spec §5)。
- 個股頁 / 群組圖牆真資料前後對照(SC-5 截圖層)。
- 更矮兩欄視窗(KR-3)。

## 3. Migration

無;可逆 = revert 🔴 [green] ×2 + 🟢 [green](§6)。

## 4. 三類 commit(`git log --oneline c958b141..HEAD`)

見收尾回報;🟢 [red]/[green] core mode → 🔴 [red]/[green] 換元件 → 🔴 [red]/[green] 佈局 → 🔴 fix 6:5(real-env)→ 🟢 fix ×3(review C-1/C-2/T-1、adapter 0 值、fmtIndexPts)。
