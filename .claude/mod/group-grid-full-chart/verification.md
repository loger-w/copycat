# verification — mod/group-grid-full-chart(R4)

日期 2026-08-17;環境:fake-source server(`evidence/fake_server.py`,port 8721,20 檔 / 四檔·六檔·十六檔·十七檔群組,合成日 bar → overlay 可算,全日回補,realtime 每 2s ±1 tick 抖動)+ vite dev 5173;瀏覽器 = user 既有 Chrome(2560×1271 主畫面;截圖工具下採 1568 寬縮圖)。**非交易日、TC4 未起,零 ZMQ**(ops-discipline)。真 TC4 層待 prod 重啟後盤中 user 過目。

## 1. 自動化 gate(波尾,HEAD d4991b3e;fix 波後重跑見 §5)

| gate | 指令 | 結果 | 證據 |
|---|---|---|---|
| pytest 全套 | `.venv\Scripts\python -m pytest -q` | 2637 passed(157.8s) | evidence/gate-pytest.txt |
| ruff | `ruff check copycat tests` | All checks passed | evidence/gate-ruff.txt |
| pyright | `python -m pyright` | 0 errors | evidence/gate-pyright.txt |
| vitest 全套 | `npx vitest run` | 117 files / 1907 passed | evidence/gate-vitest.txt |
| tsc | `npx tsc -b` | exit 0 | evidence/gate-tsc.txt |
| eslint | `npx eslint src` | exit 0 | evidence/gate-eslint.txt |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 3 findings:`only-export-components` GroupGridView:63(存量 gridShape export)、`no-giant-component` StockIntradayChart(存量)、**`prefer-tag-over-role` GroupGridView:147(新增)** | evidence/gate-doctor.txt |
| copycat validate | 需 replay 產物 `out/`;本輪未動 replay/engine 任一檔(diff 全在 frontend/ + live/stock_state + server/app,stock_engine + market.py) | 見 §5 | — |

**react-doctor 新增 finding triage**:`prefer-tag-over-role`(GroupCard 外層 `div role="button"`)= 刻意(change-spec R11:`<button>` 內容模型為 phrasing content,卡片內含 chart 的 `<div>`/`<svg>` 區塊;`role="button" + tabIndex + Enter/Space onKeyDown + aria-pressed` 為完整 a11y 語意)。判為本例誤報,**不關規則**(全站僅此一處、規則本身有效);記錄於此與 next-time,不改 doctor.config。

## 2. SC 逐條(對照 change-spec §1)

| SC | 結果 | 證據 |
|---|---|---|
| SC-1 卡片同款(刻度+亮燈 / CDP `*` / MA 名+價位 / VWAP 線+標 / VP+POC / 高低圈+價位 / 現價圈 / 時間標 / 量能副圖 / hover readout) | PASS(目視 + DOM 查:`dashed 3 2` 線 7 = 5 CDP + 2 MA、`edge-price-ma*` 2、`edge-price-vwap`、`vp-bar` 365/16 卡、`day-high`) | evidence/SC-1-2x2.jpg、SC-1-2x2-zoom-2330.png(2×2 最好格,元素全可讀)、SC-1-4x4.jpg + SC-1-4x4-zoom-3231-actual-px.png(user 實機 4×4 卡 430×262 px:刻度/CDP/MA/VP/高低全可讀,右緣 CDP+MA 標籤密集處略疊,與單檔頁同行為)、**SC-1-4x4-1080p.jpg + zoom(1904×895 視窗,卡 266×182:左緣 11 條刻度互疊成團、右緣標籤疊;時間標可讀)→ 依 spec R2-1 決議:記 next-time「卡片變體刻度減量」,回報 user,不擋出貨** |
| SC-2 圖牆頂 toggle 四鈕同步 | PASS:按「量分佈」→ 16 卡 `vp-bar` 365 → 0,`aria-pressed=false`,localStorage `copycat-chart-toggles.vp=false`(同單檔 key) | evidence/SC-2-toggle-vp-off-16cards.jpg |
| SC-3 點卡片不跳單檔 + 選中框 + 右欄換標的 | PASS:點 2603 → `aria-pressed=true` 僅該卡、`copycat-stock-main-code=2603`、view 仍 group、`選擇群組` 列在、無 `stock-lower-row`;右欄閃電梯標題「2603 長榮」、梯 205 附近 | evidence/SC-3-card-selected-ladder-2603.jpg |
| SC-4 單檔頁不變 | PASS:before/after 截圖同 chrome(readout 六欄 / toggle 四鈕 / 說明列 / CDP-MA-VP-高低-現價圈);`StockIntradayChart*.test.tsx` 110 條未改 assertion 全綠 | evidence/SC-4-single-before.jpg / SC-4-single-after.jpg |
| SC-5 group-state 四鍵 + parity | PASS:curl 回應鍵 `[backfilling, high, low, meta, minutes, no_data, vp, vwap]`,`vp` `{price:[t,o,i]}`;pytest parity(`tests/fixtures/vp_parity.json`)+ vitest `vp-parity.test.ts` 綠 | gate 檔;curl 見 §3 |
| SC-6 量化 | 見 §3 | — |
| SC-7 矩陣不變 + >16 不溢軌 | PASS:四檔 2×2 / 十六檔 4×4 佔滿中區無捲軸;十七檔 4 欄 `h-56` 卡片,grid scrollHeight 1152 > clientHeight 1065 → 外層捲軸,卡片不溢軌 | evidence/SC-1-4x4.jpg;十七檔 DOM 量測(cards 17 / cardH 224 / class 含 h-56) |

## 3. SC-6 量測

| 項 | 量法 | 數字 | 判定 |
|---|---|---|---|
| (a) payload | `curl -s -o NUL -w '%{size_download}' 'localhost:8721/api/stock/group-state?codes=<17 codes>'` | **319,513 B**(17 檔,每檔 273 分鐘 + vp 8~47 檔位)→ 每檔 ≈ 18.8 KB → 50 檔換算 ≈ **940 KB** < 1.5 MB | PASS(fake vp 檔位密度低於真實;真實 vp ≤ ~200 檔位 × ~26 B ≈ +5 KB/檔 → 50 檔 ≈ 1.2 MB 仍在界內) |
| (b) overlay 請求數 | performance resource entries 計數 | 十六檔:16 = 卡數;切 單檔 → 群組(<5 min)後仍 16(0 新請求) | PASS |
| (c) 冷 cache overlay 總耗時 | resource entries 首發 startTime → 末回 responseEnd | 25 ms(fake source 即時回;Semaphore(4)下 16 發) | 量到但**不代表 TC4**;真 TC4 冷 cache 需盤中實機(next-time) |
| (d) hover 不重算幾何 | vitest `GroupGridView.geometry.test.tsx`(spy buildIntradayGeometry) | 綠 | PASS |
| (e) 每秒 liveP 路徑 | 16 卡、realtime 每 2s ±1 tick(2330 quote 30s 內 3 個 distinct 價位)、PerformanceObserver longtask 30s;再切 十七檔 → 十六檔(全卡 remount) | **longtask(>50ms)= 0 / 0** | PASS(caveat:截圖工具驅動下 tab `visibilityState=hidden`,量到的是 JS render/commit,不含 paint;真機盤中再看) |

## 4. 白名單逐條(change-spec §2)

W-1 單檔頁:SC-4 PASS。W-2 矩陣/pill/STOCK_GROUP_KEY:SC-7 PASS + `GroupGridView.test` gridShape/pill 測試未改。W-3 群組檢視不渲染五檔/明細/header:`StockPage.test:662-671` 綠 + SC-3 DOM(無 stock-lower-row)。W-4 onSelect 換訂閱:App.test 全鏈 fetch `/api/stock/state/2317` + 主檔 localStorage。W-5 memo/pickRef/60s/盤外停/三態:`GroupGridView.memo.test` 綠(報價沒變零重畫);盤外實測 refetchInterval false(60s 不打)。W-6 extendMinutes 三道限制:測試逐字搬家綠。W-7 useChartToggles key/schema:未動,localStorage 值形同前。W-8 group-state 既有四鍵/no_data/不 set_main/guard:`{**light,...}` 只加鍵;curl 既有鍵值形同前;`tests/server` group-state 既有測試(擴鍵後)綠。W-9 `/api/stock/state` 不變:diff 未動 `snapshot()`。W-10 IndexPage/MarketPane:未動。

## 5. fix 波後(code review round 1,0e0e036b..dc70b1d9)
main 重跑全 gate(HEAD dc70b1d9):pytest **2638 passed**(gate2-pytest.txt)/ ruff PASS / pyright 0 errors / vitest **117 files 1910 passed** / tsc 0 / eslint 0 / react-doctor 同 §1 三條(無新增)/ `copycat validate` **42/42 PASS**(four/five replay 產物既存)/ `check_feat_tags.py` PASS(37 commits)。
瀏覽器複核 A-1:server 重啟後首輪 group-state `backfilling=True` + 只有窗外分鐘(probe 實測 minute key `'81'`)—— 修前卡片顯「尚無成交」,修後三態同一把尺 → 「回補中…」(vitest 246e7369 紅→綠鎖)。

## 6. 真實環境限制與留尾
- 真 TC4 / 盤中層(CDP 冷 cache 真耗時、50 檔真 payload、盤中 liveP 每秒真機 paint 成本)待 prod 重啟 + 盤中 user 過目。
- 1080p 4×4 可讀性:見 SC-1 → next-time。
- 盤外(refetchInterval false)server 重啟後首次進圖牆:第一輪 snapshot 若 backfilling(A-1 修正後顯「回補中…」)會停在該態直到交易時段輪詢或重整 —— 既有 60s 盤外停輪詢設計(W-5),非本輪回歸。
