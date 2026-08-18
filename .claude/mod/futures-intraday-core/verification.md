# verification — mod/futures-intraday-core(2026-08-18)

## 1. 自動化 gate(post code-review fix,HEAD 902bea69 + artifact)

| step | command | exit | 結果 |
|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | 0 | 2756 passed(後端未動,回歸抽樣) |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | 0 | All checks passed |
| pyright | `.venv\Scripts\python -m pyright` | 0 | 0 errors |
| validate | `.venv\Scripts\python -m copycat validate` | 0 | 42/42 PASS |
| vitest | `npm test -- --run`(frontend/) | 0 | **129 files / 2275 tests passed**(baseline 2221;+54 新案) |
| tsc | `npx tsc -b` | 0 | OK |
| eslint | `npx eslint src` | 0 | OK |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 0 | Scanned 10 files,No issues found(零新增) |

TDD tag 實查(`git log`):🟢 b7695d5c/8433a5fd [red] → fbb446d5 [green];🔴 28b826fe [red] → 05d59757 [green];
🔴 2d05bb96 [red] → 4ab97cef [green];cr1:b3b7d1ae [red] → 0ccbd1a8 [green];641f25e3 [lock] mutation-verified;
🔵 34b9681e / 902bea69 [refactor]。三類不混。

## 2. 真實環境(vite dev 5174 → prod 8721,TC4 真資料;2026-08-18 18:30 TMF 夜盤)

證據 `evidence/`:
- `SC-1-3-4-5-fut-intraday.jpg`:期貨頁分時 = core 語彙 —— readout 六欄 `18:32 44836 -0.56% 量 7 外 5 內 2`、
  昨收 45088 虛線 + 上紅下綠填色、均價線白 + 末點 `45368.23`、日高 45972 / 日低 44756 空心環 + 文字、現價實心圈、
  左緣三格 46060/45088/44116(紅/白/綠)、VP 長條(179 根)、OI 撐線 `撐 45000`(hlines,`<title>` = 「撐 45000・OI 2707口・2026-08-18」)、
  成交量副圖 + 說明列 `外盤 97517 · 內盤 113930 · 未分類 0 · 外盤比 46.1% (判定率 100%) / VWAP 45368.23`、
  時間標籤 09:00 11:00 13:00 15:00 18:00 21:00 00:00 03:00 05:00(13:00 與 15:00 相鄰 = 死區不佔 x)。
- `SC-1-fut-hover.jpg`:hover 12:12 → 虛線十字 + 左緣價標 `45426`(整數點)+ 底部 `12:12 / 45287` + readout
  `12:12 45287 +0.44% 量 280 外 155 內 125`。
- `SC-4-7-dom-probe.json`:toggles 均價 on / CDP off / MA off / 量分佈 on / 成交點 off(title「期貨分時本輪不提供 CDP/MA/成交點」);
  分時 viewBox `0 0 800 258` / 副圖 `0 0 800 76`(量測後 258:76 ≈ 260:70,svg 706px 高吃滿剩餘空間);
  `document.scrollHeight === clientHeight`(1271)、期貨頁無捲軸;`localStorage fut-chart-mode = m7`。
- `SC-8-fut-m7.jpg`:模式列 15 顆(分時 / 1–10 分 / 15 / 30 / 60 分 / 日K),「7分」aria-pressed + 7 分桶 K 線 + `撐 45000` hline 照畫(W-2 K 線態不動)。
- `SC-9-stock-after.jpg`:個股頁(1101 台泥)分時圖同款無變化(CDP 五線 / 副圖 / 說明列 / 六欄 readout);
  before = 機械閘(`StockIntradayChart*` / `GroupGridView*` / `MarketChart` / `MarketPane*` / `stock-intraday-svg` 測試不改一字全綠)。
- `regression-index-page.jpg`:台股綜合頁(加權 1 分 K / 櫃買分時 core mode=index)未改功能抽樣正常。

白名單逐條:W-1(SC-9 機械閘 + 截圖)✓ / W-2(7 分 K 截圖 hlines 照畫、K 線 diff 零)✓ / W-3(OI 撐線 title 同語意)✓ /
W-4(live 四案 + gate 4 獨立案綠;真環境 18:32 live 分鐘落序列尾)✓ / W-5(unavailable / 載入中 文案 diff 未動;測試綠)✓ /
W-6(既有七檔值序保留,15 顆截圖)✓ / W-7(FuturesPage 未動,App.test 綠)✓ / W-8(useChartToggles 未動;冷開多一觸發入口 → §8 記)✓ /
W-9(allday.test 既有案未動)✓ / W-10(core 無 capital/TQ hook 新增)✓。

edge 抽驗:hover 死區(13:46–15:00 空段)只剩水平線 + 價標(edge 3/11,目視 PASS);週末 / 盤後未驗(窗口外,語意由 live 四案測試承擔)。
KR-4:hover 拖曳目視無掉幀(TMF 夜盤 tick 頻率下)。

migration:無;可逆 = revert 三個 [green] + cr1 兩顆(spec §6)。

## 3. 未完成 / 待 user
- 真 TXF 日盤(08:45–13:45)高頻 tick 下 hover 順暢度 + 對稱域 ±1% 地板觀感 → user 過目(next-time 08-18 節)。
- 群組圖牆 SC-9 截圖前後未拍(圖牆需 stock watchlist 群組;機械閘 `GroupGridView*.test` 綠)。
