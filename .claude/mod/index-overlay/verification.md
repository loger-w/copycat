# verification — mod/index-overlay(2026-08-14)

## 自動化驗證(auto-verify;指令來源 = .claude/harness.json + 專案 CLAUDE.md frontend 節)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | **2680 passed**(baseline 2673 + 新 7) | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| tsc | `npx tsc -b`(frontend/) | 無輸出 | 0 |
| vitest | `npx vitest run`(frontend/) | **114 檔 1894 passed**(baseline 1868 + 新 26) | 0 |
| eslint | `npx eslint src`(frontend/) | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | No issues found(零新增) | 0 |

全綠 → 進真實環境節。

## 真實環境驗證(shape = web;盤後、prod server 未跑)

通道:側車 server(`evidence/fake_server.py`,fake index/OTC source、neutralize、
隔離 watchlist、port 8721 — prod 未跑故 vite proxy 免改;零 TC4/ZMQ,ops-discipline)。
真 TC4 層驗證延至 prod 重啟 + 次一交易日盤中 user 過目(慣例;TC4 取數路徑與
market bars 日 K 完全共用,已由該路徑的 prod 實績 + 單元測試覆蓋)。

### API 層(curl,側車)

- **happy(SC-5)**:`GET /api/index/overlay` →
  `{"cdp":{"cdp":24250000,"ah":24550000,"nh":24450000,"nl":24150000,"al":23950000},"ma5":24241666,"ma20":24022916,"date":"2026-08-13"}`
  — cdp 五值與治具昨日 H/L/C(24350/24050/24300)手算逐值相符。證據 `evidence/SC-5_api-overlay.txt`。
- **edge:今日 partial 剔除**:治具含今日怪值 bar(c=99500)→ 回應 date=2026-08-13、
  值不受汙染(同上證據)。
- **edge:engine 缺席 503 / TC4 down 全 null**:單元測試覆蓋(test_index_routes ×7,
  含 503 與全 null),側車不重複模擬。
- **regression ×2(未改功能)**:`/api/index/state` → trade_date/ref/270 分鐘正常;
  `/api/market/bars/TWSE?tf=D` → source=tc4_dk、26 bars(同槽共用,先打 overlay 後
  bars 正常)。證據 `evidence/SC-5_regression-state-marketbars.txt`。

### UI 層(截圖 dispatch,SC-1/2/3/4/6)— 5/5 PASS,console 零新增 error

- SC-1 PASS:加權分時白色均價線;toggle 反證(關→消失、開→重現)。`evidence/SC-1_twse-avgline.png`
- SC-2 PASS:櫃買分時同均價線。`evidence/SC-2_otc-avgline.png`
- SC-3 PASS:域內 3 條虛線(nh 24450 / cdp 24250 / ma5 24241.67,dash "3 2")+ 右緣
  `24450*`/`24250*`/`MA5 24241.67`;掛牌 `AH 24550↑`/`NL 24150↓`/`AL 23950↓`/
  `MA20 24022.92↓` 全到位,與 fake 治具逐值吻合。`evidence/SC-3_twse-overlay.png` + `-detail.png`
- SC-4 PASS:櫃買 CDP/MA disabled、opacity 0.4、title="櫃買無日 K 資料源";均價可按。
  `evidence/SC-4_otc-disabled.png`
- SC-6 PASS:昨收虛線右端「昨收 24300」灰字。`evidence/SC-6_ref-label.png`
- console:僅 vite/DevTools 既有噪音,零新增 error。

## §7 回頭核 goal(逐 SC + 白名單;migration N/A — 本輪無資料格式變更)

| SC | 實作 | 測試 | real-env 證據 |
|---|---|---|---|
| SC-1 | index-chart-svg.ts avgLine + MarketChart 均價 polyline | index-chart-svg.test(avgLine 逐點)綠 | SC-1 截圖 + toggle 反證 |
| SC-2 | 同上(市場無關) | 同上 | SC-2 截圖 |
| SC-3 | MarketChart toggle 列 + overlayLines 重用 + rightEdgeLabels | MarketChart.test 域內/域外 fixture 綠 | SC-3 截圖(域內線+掛牌逐值吻合) |
| SC-4 | available 閘 + title | MarketChart.test disabled+title 綠 | SC-4 截圖 + DOM title 實查 |
| SC-5 | app.py index_overlay(build_period IX0001\|L) | test_index_routes ×7 綠 | curl happy/partial 剔除/regression ×2 |
| SC-6 | rightEdgeLabels fixed 昨收項 | MarketChart.test 昨收/ref-null 綠 | SC-6 截圖 |
| SC-7 | 域外掛牌不擴域 | 幾何域外分類 + 元件 toggle 開關 yTicks/refY 不變 綠 | SC-3 截圖(掛牌在、y 域未擴) |

白名單 W-1~W-14:自評 whitelist lens 逐條 PASS(code-review-round-1.json);機驗 =
全量 pytest 2680 / vitest 1894(含 MarketPane 30、StockIntradayChart 110、test_bars)
全綠。regression 抽樣:/api/index/state、/api/market/bars/TWSE?tf=D(未改功能)側車實測正常。
UI SC 的 user 過目層:待收尾回報(側車 + vite 保持運行供目視)。
