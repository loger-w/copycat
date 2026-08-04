# test-inventory — refactor/frontend-dedupe-format(2026-08-04)

Baseline:`npm test` 72 files / **987 passed**(refactor 前全綠)。

## 逐站點覆蓋盤點

| 改動站點 | 既有覆蓋 | 判定 |
|---|---|---|
| `hooks/useSeries.ts:5-12` local `parseError` | `lib/api-error.test.ts` 3 cases(HTTP_500 非 JSON / NOT_READY / detail 缺 → HTTP_404);與 lib 版**逐字相同**(Read 比對) | 夠 — identity swap,tsc + 既有測試護 |
| `hooks/useCapital.ts:88-104` `parseCapitalError` | `useCapital.test.tsx:87-113` 4 cases(裸碼 / ORDER_BLOCKED:reason / 非 JSON → HTTP_500 / BROKER_REJECTED:err_code) | 夠 |
| `components/IndexBar.tsx:9-12,26`(chgPct / 行內 pct) | `IndexBar.test.tsx` 斷言 "-3.65%"、"-4.84%"(負號路徑 + 計算式) | **正號分支(`+` 前綴)未覆蓋 → 補 characterization** |
| `components/index/IndexPage.tsx:175,186`(Quote 行內) | `IndexPage.test.tsx` 無任何 pct 字串斷言 | **補 characterization(「±pts (±pct%)」整串)** |
| `components/futures/FuturesPage.tsx:60`(行內) | `FuturesPage.test.tsx:116` "+0.88%" | 夠 |
| `components/corr/RiverCards.tsx:19-21` local fmtPct | `RiverPanel.test.tsx:59,66` "+1.00%" bull / "-1.00%" bear(並排卡 = RiverCards) | 夠 |
| `components/corr/RiverOverlay.tsx:23-25` local fmtPct | RiverPanel.test 的重疊模式測試**不斷言任何 pct**(:75-98 只驗 mode/checkbox/腿名) | **補 characterization(重疊模式 pct 軸標籤)** |
| `lib/signal-model.ts:78` | `signal-model.test.ts:59-60,86,90` "+5.23%" / "-5.40%" / null 路徑 | 夠 |

## 明確不動(行為差異,非本輪)

- `CapitalPositionsList.tsx:79` 用 `>= 0` 判 `+` 號(其餘各處 `> 0`;且格式化的是整數損益額非 pct)— 行為微調待 user 拍板,記 `docs/next-time.md`。
- `CandleChart` 「期間漲跌」「跨日漲跌」= 語意變體,不併。
- `IndexBar.tsx:4-7` local `fmt`(millipts)與 `lib/format.fmt` **實作不同**(`Math.round(v*100)/100` vs `toFixed(2).replace`),不在本輪 scope,不動。
