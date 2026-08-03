# 實測證據(2026-07-30,stock-ui-round4)

## Baseline gate(改動前,worktree `mod/stock-ui-round4` @ base cb9b43b)

| Gate | 指令(cwd) | 輸出 |
|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q`(repo root) | `1267 passed, 1 skipped, 1 warning in 35.26s` |
| ruff | `python -m ruff check copycat tests`(repo root) | `All checks passed!` exit 0 |
| pyright | `python -m pyright`(repo root) | `0 errors, 0 warnings, 0 informations` |
| 前端測試 | `npm test`(frontend/) | `Test Files 56 passed (56)` / `Tests 533 passed (533)` |
| tsc | `npx tsc -b`(frontend/) | exit 0 |
| eslint | `npx eslint src`(frontend/) | exit 0 |

**踩過的坑(記錄以免誤判)**:
1. worktree 缺 git-ignored 的 `spikes/TCPY/` → `test_tc4.py::…dead_port…` 與
   `test_tc4_trade.py::…gc…` 兩支以 `ModuleNotFoundError: No module named 'tcoreapi_mq'` 紅。
   `cp -r` 主 repo 的該目錄進 worktree 即恢復,**不是 code regression**。
2. `ruff check copycat tests` 若 cwd 停在 `frontend/` 會回 `E902 系統找不到指定的檔案`(exit 2),
   看起來像 lint 紅。gate 指令務必確認 cwd。

## ISIN 名稱表解析規則實測(change-spec 🟢-6 前置驗證)

probe:`<scratchpad>/isin_parse_probe.py`(實作 spec 描述的規則後對真實 HTML 跑)。

| 來源 | 收錄 | 逐段筆數 | 剔除 |
|---|---|---|---|
| `strMode=2` 上市 | **1,378** | 股票 1054 / 特別股 28 / 創新板 29 / ETF 236 / ETN 15 / 臺灣存託憑證(TDR) 10 / 受益證券-不動產投資信託 6 | 權證段 30,561 |
| `strMode=4` 上櫃 | **1,023** | ETF 118 / ETN 6 / 股票 890 / 特別股 1 / 受益證券-資產基礎證券 8 | 權證段 9,438 |
| 合併 | **2,401** | — | 跨市場重複 **0** |

**規則全部成立,零意外剔除**:`bad_code` / `no_fullwidth_space` / `empty_name` / `dup`
四個剔除計數**全為 0** → 全形空格切 code/name、`validate_code` 過濾在真實資料上零損耗。

抽驗:`2330 台積電`、`5483 中美晶`、`3231 緯創`、`6547 高端疫苗`(上櫃)、
`00679B 元大美債20年`(字母尾碼 ETF)、`8069 元太`(上櫃)全部命中。
最長名稱 `00890B → "凱基ESG BBB 債 15+"`(15 字,含半形空格)。

### 解碼:`big5` 會靜默毀字,必須用 `cp950`(review R12,2026-07-30)

上面那次 probe 用 `big5` + `errors="replace"`。review 質疑後實測**同一份上市 HTML**:

```
big5 U+FFFD 次數: 447 | cp950 U+FFFD 次數: 0 | 兩者相同: False
```

→ 改 `cp950`(Big5 超集)重跑,結果如下(**這組才是最終基準**):

| 項目 | 值 |
|---|---|
| 上市收錄 | 1,378(段:股票 1054 / 特別股 28 / 創新板 29 / ETF 236 / ETN 15 / TDR 10 / 受益證券 6) |
| 上櫃收錄 | 1,023(段:ETF 118 / ETN 6 / 股票 890 / 特別股 1 / 受益證券 8) |
| **合併總數** | **2,401**(跨市場重複 0) |
| 名稱含 U+FFFD | **0** |
| 其他剔除(bad_code / no_sep / empty_name) | **全 0** |
| 權證剔除列 | 39,999 |

### JSON 大小的三個數字(review R24:別再混用)

| 數字 | 出處 |
|---|---|
| 57,363 bytes | 第一次 probe(**big5**,`json.dumps(indent=1, sort_keys=True)`) |
| 57,322 bytes | cp950 重跑 probe(同 dumps 參數) |
| **59,727 bytes** | **實際落檔的 `copycat/stock_names.json`**(`write_names` 的 `indent=1` + `sort_keys=True` + trailing newline 差異)—— **前端載入成本的真正基準** |

change-spec 的 auto-default 原估「~3.4k 筆 / ~110 KB」**偏大約 1.4 倍**(把上市 31,732 rows
扣權證時算錯);實際 2,401 筆 / 58 KB,「整包給前端過濾」的判斷因此更站得住(不是更弱)。

### `refresh` 守門(review R7/R21 後定案)

單側下界擋不到最危險的漂移方向:段標題偵測(靠「單一 `<td>` 的列」)一旦失效,39,999 筆權證
全收 → 總數 ~42,000 **遠大於**任何下界。故改雙側 + 語意檢查,三條全過才寫檔:

| 守門 | 門檻 | 實測值 |
|---|---|---|
| 總筆數區間 | [1800, 6000] | 2,401 |
| 段名含「權證」者剔除列數合計 | > 5,000 | 39,999 |
| 段名含「股票」者收錄筆數合計 | > 500 | 1,944(1,054 + 890) |

### CLI 實跑(SC-10)

```
$ .venv\Scripts\python -m copycat refresh-stock-names
INFO copycat.stock_names: ISIN …strMode=2:收 1378 筆,逐段 {'股票': 1054, …},權證剔除 30561 列,其他剔除 {}
INFO copycat.stock_names: ISIN …strMode=4:收 1023 筆,逐段 {'ETF': 118, …},權證剔除 9438 列,其他剔除 {}
INFO copycat.stock_names: 股票名稱表更新完成:2401 檔(權證剔除 39999 列)
股票名稱表更新完成:2401 檔
exit=0   →  copycat/stock_names.json  59,727 bytes
```

## Phase 7 真實環境驗證(2026-07-30 11:53 盤中)

### SC-10 端到端 PASS(CLI → 版控 JSON → endpoint)

```
$ curl http://127.0.0.1:8731/api/stock/names
HTTP 200 | count = 2401 | names len = 2401
   2330 -> 台積電      5483 -> 中美晶     6547 -> 高端疫苗
   00679B -> 元大美債20年   8069 -> 元太    3231 -> 緯創
```

`/api/stock/watchlist` 200(engine 就緒);`/api/index/state` 與 `/api/futures/state` 都有真實推播
(加權 40,506,990 毫點、TXF 五檔俱全)→ 達錢 4 當時開著且盤中。

### ⚠ 操作失誤(記錄下來,不重犯)

為驗 endpoint 起了**第二台後端**(port 8731),它照常訂了 `IX0001` 與 `TXF/MXF/TMF`。
user 自己的 server 同時在 8721 跑著 —— 依 CLAUDE.md §8「TC4 同 symbol 跨 session 只推一邊」,
那約 90 秒內可能搶走 user 的推播。**盤中不該起第二台後端**。

關閉後複查 user 的 8721:`seq=239228` 持續遞增、TXF 時間戳 `11:54:23` 為當下、
`/api/index/state` 正常 → 未留下影響。

### 零干擾的替代路徑(之後照這條走)

只起**前端 dev server**(`npm run dev -- --port 5183`),`vite.config.ts` 的 proxy 本來就指
`127.0.0.1:8721` → 完全不新增 TC4 訂閱。實測 `http://localhost:5183` HTTP 200
(⚠ Vite 綁 `localhost`,Windows 下 `127.0.0.1` 拿不到 → curl 要用 `localhost`)。

`/api/stock/names` 經 proxy 回 **404** —— user 的 8721 跑的是 master 版後端還沒有這個 endpoint。
這正好實地驗到**降級路徑**:提示列不出現,但「直接打完整股號 → Enter / 新增」照樣可用(白名單 W-4)。
SC-1a / SC-1b(名稱提示列)要看到,必須把後端從本分支重啟 —— 那是 user 的 live session,不自行動。

### 待 user 對照過目(UI 類,/mod Phase 8:browser AI E2E 已移除)

user 自選當時為空 → 一進畫面就會落在 SC-2b 的零群組 fallback,動線:
零群組加 2330 → 建第二組 → 拖曳換組 / 拖到側欄外 / Esc → 折疊 + 重載 → 江波圖 → 日K。

| SC | 狀態 |
|---|---|
| SC-1a / SC-1b(名稱與代碼提示列) | **待後端重啟後過目** |
| SC-1c(無命中原樣加入) | 可在現況(表 404)直接驗 |
| SC-2 / SC-2b / SC-3 / SC-4a-c / SC-5 / SC-6 / SC-7 / SC-8 | **待 user 過目**(現況後端即可) |
| SC-9 | 自動化 gate,已全綠(見下) |
| SC-10 | **PASS**(上方 curl 輸出) |

## 端點連通性實測(選資料源時的對照,見 current-state.md)

| 端點 | 結果 |
|---|---|
| `isin.twse.com.tw/isin/C_public.jsp?strMode=2` / `=4` | OK(Big5,7.5 MB / 2.5 MB) |
| `openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | OK 1,373 rows(JSON,**僅上市**) |
| `www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes` | **FAIL** `SSL: CERTIFICATE_VERIFY_FAILED (Missing Subject Key Identifier)` |

## Phase 8 回頭核:目標行為證據(檔案:行號)

| 項 | 需求 | 落點證據 |
|---|---|---|
| 1 | 名稱或代碼皆可搜、兩者都有提示列 | `copycat/stock_names.py`(ISIN → 2,401 檔版控表)、`copycat/server/app.py:/api/stock/names`、`frontend/src/lib/stock-search.ts:searchStocks`(代碼前綴優先於名稱片段)、`WatchlistSidebar.tsx:searchBox()` 的 `stock-suggest` 清單 |
| 2 | 群組全列出、可折疊、可拖曳改組 | `WatchlistSidebar.tsx`:每組 `<section data-testid="wl-group-*">`、`toggleCollapsed` + `copycat-stock-wl-collapsed`、`onHandleDown` → `zonesNow()` → `dropTargetFromPointer` → `moveCode`;tab 列(`role="tablist"`)已不存在 |
| 3 | 江波圖左緣價位不覆蓋線 | `stock-intraday-svg.ts:Y_AXIS_W=46` / `plotWidth` / `minuteToX` / `minuteOf`;元件側 refY 線、疊線、crosshair-h、EnergySub 中線的 `x1` 全改 `Y_AXIS_W` |
| 4 | 左緣價位有對應水平線 | `StockIntradayChart.tsx` yTicks map 內新增 `data-testid="y-grid"`(`stroke-line` / `2 3` / 0.5,對齊 K 線圖) |
| 5 | 交易量刻度移到右邊 | `EnergySub` 兩個 `<text>` 改 `x={w-2}` + `textAnchor="end"` + `paintOrder="stroke"` 描邊 |
| 6 | K 線圖都要顯示布林通道 + 5MA + 20MA | `useChartToggles.ts:DEFAULTS.bb = true` + `TOGGLES_VERSION=2` 一次性升級並落檔;MA5/MA20 本來就恆顯示(`CandleChart.tsx:180-198`,未改) |

## 白名單逐條打勾(Phase 5 lens 全數 preserved,細節見 code-review-round-1.json)

W-1 ✓ / W-2 ✓(`stock_watchlist.py` 零改動) / W-3 ✓(`onSuccess` 才收斂) / W-4 ✓(Enter + 「新增」兩條路徑都有測試) /
W-5 ✓(握把 / ⊞ / × 皆 `stopPropagation`;折疊鈕與提示列不在 onSelect 子樹) / W-6 ✓ / W-7 ✓ / W-8 ✓(含退化寬度) /
W-9 ✓ / W-10 ✓ / W-11 ✓ / W-12 ✓ / W-13 ✓、W-15 ✓(`CandleChart.tsx` / `StockChart.tsx` 零改動) / W-14 ✓ / W-16 ✓(新增)

## Migration 可逆性

| 面 | 可逆性 |
|---|---|
| `copycat/stock_names.json` | 純新增版控檔;revert commit 即消失,無其他模組依賴它存在(`load_names` 檔不存在回 `{}`) |
| `GET /api/stock/names` | 純新增 endpoint,零既有 caller |
| localStorage `copycat-chart-toggles` 的 `v` 欄位 | 舊版 code 讀到 `v` 會被 `{...DEFAULTS, ...saved}` 當普通欄位吸收(不影響四個 boolean),**向下相容** |
| localStorage `copycat-stock-wl-collapsed` | 新 key;舊版 code 不讀它,revert 後只是留一個沒人看的 key |
| localStorage `stock-wl-group`(舊 activeGroup) | 未刪除,revert 回舊版即恢復作用 |
| 自選 JSON / API 契約 | 零改動 → 前後端可獨立 revert |
