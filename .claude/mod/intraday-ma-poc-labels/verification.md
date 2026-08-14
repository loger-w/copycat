# Verification:mod/intraday-ma-poc-labels(2026-08-14)

## 自動化驗證(全綠)

| # | 指令 | cwd | 結果 |
|---|---|---|---|
| 1 | `.venv\Scripts\python -m pytest -q` | root | **2662 passed**(exit 0) |
| 2 | `.venv\Scripts\python -m ruff check copycat tests` | root | All checks passed(exit 0) |
| 3 | `.venv\Scripts\python -m pyright` | root | 0 errors / 0 warnings(exit 0) |
| 4 | `copycat replay four/five + copycat validate` | root | 全列 PASS(exit 0) |
| 5 | `npm test`(vitest) | frontend | **1851 passed**(baseline 1809;+42;exit 0) |
| 6 | `npx tsc -b` | frontend | exit 0 |
| 7 | `npx eslint src` | frontend | exit 0 |
| 8 | `npx react-doctor@latest --scope changed --no-telemetry` | frontend | 僅存量 `no-giant-component`(StockIntradayChart,memory 已列 6 檔之一);**無新增 finding** → PASS |

TDD 機驗:三包紅→綠 + fix 波(A-1 red 3aacc269 → green 9cf2d84c;lock 1ce90864
mutation-verified ×2:obstacle 判準改壞 → B-6 紅、疊印去除改壞 → B-5 紅,均還原後綠)。

## 真實環境驗證(web shape:AI 截圖對照 + user 過目雙層)

環境:prod server 8721(git_sha 3aacc269,08:00 啟動,TC4 連線)+ vite dev 5173
(本分支前端 code;盤中驗前端改動只起 vite dev,不起第二台 TC4 server — ops-discipline)。
驗證窗口:盤中(09:00 後累積數分鐘成交才有 VP/POC/VWAP 可看)→ 截圖 dispatch 排在
09:08 後執行。

逐 SC 判定(2026-08-14 09:10–09:12 盤中實測,取樣 2330 / 6182 / 2408;
截圖 `evidence/`,檔名含 SC-N):

- **SC-1 PASS**:2330 黃 `2400`(MA5)+ 紫 `2355`(MA20)在繪圖區內側右緣,名稱照舊;
  6182 / 2408 各只出域內那顆(域外不出,沿既有語意)。
- **SC-2 PASS**:三檔 VWAP 標籤與說明列同值(2434.71/116.69/534.96);關均價 toggle
  線與數字同滅。
- **SC-3 PASS**:兩顆 MA 數字垂直分離(y≈331/363),不壓左緣刻度與右緣帶名稱。
- **SC-4 PASS**:最長量條變 accent 色 + 更不透明,尖端同色價位數字(6182 最清晰)。
- Console:零 error / 零 warning。
- 殘留確認項:D5「POC 標籤與走勢線交會仍可辨識」情境開盤初期未觸發(線未鋪到中段);
  間接佐證 = VWAP 白字壓在 POC 條上 halo 有效。併入 user 盤中過目。
- 附帶觀察(不計本輪):CDP 五個右緣帶標籤自身互疊(既有擁擠,out of scope 已列)。

Regression 抽 2 個未改功能(截圖旁證):CDP 疊線 `價位*` 照常、內外盤說明列照常;
既有測試層再抽:hover 十字線 / 期貨態測試全綠(1851 內)。

## Phase 7:SC 逐條對照(重讀 spec 後核)

| SC | 實作 | 自動化證據 | real-env |
|---|---|---|---|
| SC-1 MA 價位標籤 | StockIntradayChart.tsx maLabels 分支(fmtTickPrice、無 *、LEVEL_FILL 色、名稱照舊) | 「MA 開 →」「fmtTickPrice 口徑」「名稱照舊」「toggle 關」4 tests pass(1851 全綠內) | 截圖 SC-1 + user 過目 |
| SC-2 VWAP 標籤 | vwapLabel 分支(值 = accum.vwap 同源,A-1;null 不畫;stkfut 也出) | 「值 = accum.vwap + figcaption 同值」「null → 不畫」「toggle 關」「貼右界內縮」「期貨態仍出」5 tests pass | 截圖 SC-2 + user 過目 |
| SC-3 避讓 | edgePriceLabels(obstacle 中心正規化 + 圓心、退化 bounds、疊印去除) | lib 16 tests + 元件 obstacle 讓位/對照組 2 tests pass;mutation-verified ×2 | 截圖 SC-3(目視不重疊) |
| SC-4 POC | buildVpBars.poc + highlight + 尖端標籤 | lib poc 6 tests + 元件 5 tests pass(:1030 事前標記該變已紅→綠) | 截圖 SC-4 + user 過目 |

Edge cases 1-7:全部有對應測試(1 同價避讓 / 2 v=0 分鐘 B-7 / 3 全 0 無 POC / 4 tie 高價 /
5 clamp 近頂近底 / 6 flat 域 B-7 / 7 域外沿 overlayLines 既有測試)。
Migration:無(純前端渲染,無資料格式改動)→ 可逆性 N/A。

## 白名單逐條(自動化層)

1-8, 9-11:見 code-review-round-1.json `whitelist_check`(10 pass / 1 fail→A-2 已修,
修後全套測試綠 = 全 pass)。既有測試除 spec 事前標記一條(:1030)外零改動零紅。
